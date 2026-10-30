"""Inference-only replay of fixed raw-demo checkpoints and calibration parameters."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
from scipy import stats
import torch
from torch.utils.data import DataLoader
from torchmetrics.functional.image import structural_similarity_index_measure as ssim
from torchmetrics.image.lpip import LearnedPerceptualImagePatchSimilarity


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def run(task, out):
    os.environ["CONVRML_PROJECT"] = "/home/jy2228/ConvRML"
    os.chdir("/home/jy2228/ConvRML")
    sys.path.insert(0, task["source_folder"])
    from model import Model
    from data import Pairs, identity
    from train import PROTOCOL

    torch.set_num_threads(4)
    torch.manual_seed(20261030)
    checkpoint = (
        Path(task["source_folder"])
        / "results/raw"
        / task["method"]
        / "checkpoints"
        / f"epoch_{task['epoch']:03d}.pt"
    )
    ck = torch.load(checkpoint, map_location="cpu", weights_only=False)
    config = ck["config"]
    assert (
        ck["epoch"] == task["epoch"]
        and config["method"] == task["method"]
        and config["camera"] == "raw"
    )
    assert config["protocol"] == PROTOCOL and config["dataset_identity"] == identity(
        "raw"
    )
    model = Model(task["method"])
    model.load_state_dict(ck["model"], strict=True)
    model = model.cuda().eval().requires_grad_(False)
    provenance = dict(
        checkpoint=str(checkpoint),
        epoch=ck["epoch"],
        protocol=PROTOCOL,
        source_sha256=config["source_sha256"],
        dataset_identity=config["dataset_identity"],
    )
    del ck
    metric = (
        LearnedPerceptualImagePatchSimilarity(
            net_type="alex", normalize=True, reduction="none"
        )
        .cuda()
        .eval()
        .requires_grad_(False)
    )
    test = Pairs("raw", "test")
    assert len(test) == 2000
    ids = [str(row["id"]) for row in test.rows]
    assert ids[:50] == task["expected_ids"]
    rows = {mode: [] for mode in task["modes"]}
    started = time.monotonic()
    with torch.inference_mode():
        for index, batch in enumerate(
            DataLoader(test, batch_size=1, num_workers=2, pin_memory=True)
        ):
            y, x = batch[:, 0].cuda(non_blocking=True), batch[:, 1].cuda(
                non_blocking=True
            )
            z = model(y)
            pred = z if task["method"] == "qutcc" else z[:, 1]
            prediction = pred.float().clamp(0, 1)
            perceptual = float(metric(prediction, x).item())
            metric.reset()
            for mode, spec in task["modes"].items():
                fitted = spec["calibration"]
                if task["method"] == "qutcc":
                    lower = model(y, y.new_full((len(y),), fitted["lower_q"]))
                    upper = model(y, y.new_full((len(y),), fitted["upper_q"]))
                else:
                    lower = pred - fitted["scales"]["lower"] * (
                        pred - z[:, 0]
                    ).clamp_min(1e-6)
                    upper = pred + fitted["scales"]["upper"] * (
                        z[:, 2] - pred
                    ).clamp_min(1e-6)
                lower, upper = lower.float().clamp(0, 1), upper.float().clamp(0, 1)
                assert all(torch.isfinite(v).all() for v in (prediction, lower, upper))
                error = (prediction - x).abs()
                values = dict(
                    psnr=float(
                        -10 * (prediction - x).square().mean().clamp_min(1e-12).log10()
                    ),
                    ssim=float(ssim(prediction, x, data_range=1.0)),
                    mae=float(error.mean()),
                    coverage=float(((x >= lower) & (x <= upper)).float().mean()),
                    width=float((upper - lower).mean()),
                    lpips=perceptual,
                )
                # Match the visible RGB-average maps and browser double precision.
                p = prediction[0].double().cpu().numpy()
                target = x[0].cpu().numpy()
                # ImagePairs normalization originates from uint8 prepared PNGs.
                target = np.rint(target.astype(np.float64) * 255) / 255
                u = (
                    (upper[0].double().cpu().numpy() - lower[0].double().cpu().numpy())
                    .mean(axis=0)
                    .ravel()
                )
                e = np.abs(p - target).mean(axis=0).ravel()
                if np.ptp(u) == 0 or np.ptp(e) == 0:
                    values.update(pearson=None, spearman=None)
                else:
                    values.update(
                        pearson=float(stats.pearsonr(u, e).statistic),
                        spearman=float(stats.spearmanr(u, e).statistic),
                    )
                if index < 50:
                    expected = spec["expected_first"][index]
                    for key, tolerance in [
                        ("psnr", 0.001),
                        ("ssim", 0.00005),
                        ("mae", 0.00002),
                        ("width", 0.00005),
                        ("coverage", 0.0002),
                    ]:
                        assert abs(values[key] - expected[key]) < tolerance, (
                            index,
                            mode,
                            key,
                            values[key],
                            expected[key],
                        )
                rows[mode].append(dict(index=index, id=ids[index], **values))
            if (index + 1) % 100 == 0:
                print(
                    json.dumps(
                        dict(
                            images=index + 1,
                            total=len(test),
                            seconds=time.monotonic() - started,
                        )
                    ),
                    flush=True,
                )
                write(
                    out.with_suffix(".progress.json"),
                    dict(
                        images=index + 1,
                        total=len(test),
                        seconds=time.monotonic() - started,
                    ),
                )
    reports = {}
    for mode, values in rows.items():
        averages = {}
        valid = {}
        for key in (
            "psnr",
            "ssim",
            "mae",
            "coverage",
            "width",
            "lpips",
            "pearson",
            "spearman",
        ):
            finite = [
                row[key]
                for row in values
                if row[key] is not None and np.isfinite(row[key])
            ]
            averages[key] = float(np.mean(finite)) if finite else None
            valid[key] = len(finite)
        reports[mode] = dict(
            study=task["study"],
            method=task["method"],
            epoch=task["epoch"],
            base=task["modes"][mode]["base"],
            count=len(values),
            metrics=averages,
            n_valid=valid,
            per_image=values,
            provenance=provenance,
            calibration=task["modes"][mode]["calibration"],
            calibration_refitted=False,
            training_performed=False,
            first_50_reproduced=True,
            seconds=time.monotonic() - started,
            gpu=torch.cuda.get_device_name(),
        )
    write(out, dict(passed=True, task=task["key"], reports=reports))
    print("COMPLETE", str(out), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--task", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task = json.loads(args.tasks.read_text())[args.task]
    run(task, args.output / (task["key"] + ".json"))
