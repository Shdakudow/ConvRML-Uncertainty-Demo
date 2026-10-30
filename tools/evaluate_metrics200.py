"""Frozen-checkpoint LPIPS and uncertainty/error correlations on fixed 200 test IDs.

Uses previously fitted calibration without training or fitting on test images.
The first 200 test IDs in each immutable manifest are used at every milestone.
"""

import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
from scipy import stats
import torch
from torch.utils.data import DataLoader, Subset
from torchmetrics.image.lpip import LearnedPerceptualImagePatchSimilarity
from torchmetrics.functional.image import structural_similarity_index_measure


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


@torch.inference_mode()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--task", type=int, required=True)
    args = parser.parse_args()
    task = json.loads((args.workdir / "tasks.json").read_text())[args.task]
    output = args.workdir / "results" / (task["key"] + ".json")
    if output.exists():
        print("Already complete", task["key"])
        return
    assert task["status"] == "ready"
    source_report = Path(task["calibration_report"])
    assert (
        hashlib.sha256(source_report.read_bytes()).hexdigest()
        == task["calibration_report_sha256"]
    )
    project = Path("/home/jy2228/ConvRML")
    os.environ["CONVRML_PROJECT"] = str(project)
    os.chdir(project)
    sys.path.insert(0, str(project))
    torch.set_num_threads(4)
    family, camera, method, epoch = (
        task[k] for k in ["family", "camera", "method", "epoch"]
    )
    fitted = task["calibration"]
    if family == "paper":
        sys.path.insert(0, task["source_folder"])
        from model import Model
        from data import Pairs, identity

        checkpoint = (
            Path(task["source_folder"])
            / "results"
            / camera
            / method
            / "checkpoints"
            / f"epoch_{epoch:03d}.pt"
        )
        ck = torch.load(checkpoint, map_location="cpu", weights_only=False)
        assert (
            ck["epoch"] == epoch
            and ck["config"]["method"] == method
            and ck["config"]["camera"] == camera
        )
        assert ck["config"]["dataset_identity"] == identity(camera)
        model = Model(method)
        model.load_state_dict(ck["model"], strict=True)
        del ck
        model = model.cuda().eval().requires_grad_(False)
        dataset = Pairs(camera, "test")
        ids = [str(row["id"]) for row in dataset.rows]

        def predict(y):
            if method == "qutcc":
                return (
                    model(y),
                    model(y, y.new_full((len(y),), fitted["lower_q"])),
                    model(y, y.new_full((len(y),), fitted["upper_q"])),
                )
            z = model(y)
            return z[:, 1], z[:, 0], z[:, 2]

        autocast = nullcontext
    else:
        import scripts.corrected_comparison_study as study

        study.ROOT = Path(task["weights_root"])
        from scripts.export_corrected_milestone import predictor
        from scripts.formal_rml_train import Pairs

        predict, _ = predictor(camera, method, epoch)
        folder, _ = study.paths(camera)
        dataset = Pairs("test", folder)
        ids = [
            str(row["id"])
            for row in json.loads((folder / "manifest.json").read_text())["test"]
        ]
        autocast = lambda: torch.autocast("cuda", dtype=torch.bfloat16)
    assert len(dataset) == (2000 if camera == "raw" else 5000)
    torch.manual_seed(20261030)
    perceptual = (
        LearnedPerceptualImagePatchSimilarity(
            net_type="alex", normalize=True, reduction="none"
        )
        .cuda()
        .eval()
        .requires_grad_(False)
    )
    rows = []
    started = time.monotonic()
    for batch in DataLoader(
        Subset(dataset, range(200)), batch_size=4, num_workers=2, pin_memory=True
    ):
        y, x = batch[:, 0].cuda(), batch[:, 1].cuda()
        with autocast():
            pred, lower, upper = predict(y)
        pred, lower, upper = [v.float() for v in [pred, lower, upper]]
        if method != "qutcc":
            lower = pred - fitted["scales"]["lower"] * (pred - lower).clamp_min(1e-6)
            upper = pred + fitted["scales"]["upper"] * (upper - pred).clamp_min(1e-6)
        pred, lower, upper = [v.clamp(0, 1) for v in [pred, lower, upper]]
        assert all(torch.isfinite(v).all() for v in [pred, lower, upper])
        perceptual.reset()
        scores = perceptual(pred, x).cpu().numpy().reshape(-1)
        ssims = (
            structural_similarity_index_measure(
                pred, x, data_range=1.0, reduction="none"
            )
            .cpu()
            .numpy()
            .reshape(-1)
        )
        pp, xx, ll, uu = [v.double().cpu().numpy() for v in [pred, x, lower, upper]]
        xx = np.rint(xx * 255) / 255
        for j in range(len(pp)):
            index = len(rows)
            error = np.abs(pp[j] - xx[j]).mean(0).ravel()
            width = (uu[j] - ll[j]).mean(0).ravel()
            pearson = spearman = None
            if np.ptp(width) > 0 and np.ptp(error) > 0:
                pearson = float(stats.pearsonr(width, error).statistic)
                spearman = float(stats.spearmanr(width, error).statistic)
            rows.append(
                dict(
                    id=ids[index],
                    index=index,
                    lpips=float(scores[j]),
                    pearson=pearson,
                    spearman=spearman,
                    psnr=float(
                        -10 * np.log10(max(np.mean((pp[j] - xx[j]) ** 2), 1e-12))
                    ),
                    ssim=float(ssims[j]),
                    coverage=float(np.mean((xx[j] >= ll[j]) & (xx[j] <= uu[j]))),
                    width=float(width.mean()),
                )
            )
        if len(rows) % 40 == 0:
            print(task["key"], len(rows), "/ 200", flush=True)
            write(
                output.with_suffix(".progress.json"),
                dict(count=len(rows), total=200, seconds=time.monotonic() - started),
            )
    metrics = {}
    valid = {}
    for key in ["lpips", "pearson", "spearman", "psnr", "ssim", "coverage", "width"]:
        values = [
            row[key] for row in rows if row[key] is not None and np.isfinite(row[key])
        ]
        metrics[key] = float(np.mean(values)) if values else None
        valid[key] = len(values)
    write(
        output,
        dict(
            key=task["key"],
            group=task["group"],
            method=method,
            epoch=epoch,
            count=200,
            test_ids_sha256=hashlib.sha256("\n".join(ids[:200]).encode()).hexdigest(),
            metrics=metrics,
            n_valid=valid,
            per_image=rows,
            calibration=fitted,
            calibration_report_sha256=task["calibration_report_sha256"],
            protocol="fixed200_near90_clipped_rgb_unsmoothed_v1",
            training_performed=False,
            calibration_refitted=False,
            mc_passes=30 if method == "mc_005" else None,
            seed=20261030,
            gpu=torch.cuda.get_device_name(),
            seconds=time.monotonic() - started,
        ),
    )
    print("COMPLETE", task["key"], flush=True)


if __name__ == "__main__":
    main()
