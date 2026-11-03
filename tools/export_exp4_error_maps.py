"""Replay Exp 4's first 50 fixed test scenes to save exact absolute-error maps."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image
import torch
from torch.utils.data import DataLoader, Subset
from heatmap_colors import colorize

FROZEN = Path(
    "/home/jy2228/ConvRML/experiments/experiment4_generalized_20261101/source"
)
sys.path.insert(0, str(FROZEN))
from experiments.experiment4_demo import evaluate as e


def main(args):
    torch.set_num_threads(2)
    torch.manual_seed(20261101)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    config = SimpleNamespace(
        manifest=Path(
            "/home/jy2228/ConvRML/experiments/dlmd_raw_adaptive_size_20261016/data/split.json"
        ),
        generalized_root=Path(
            "/home/jy2228/ConvRML/experiments/raw_online_scratch_30epochs_20261031_v2"
        ),
        clean_root=Path("/home/jy2228/ConvRML/experiments/qutcc_paper_style_20261018"),
    )
    reference_path = Path(
        "/home/jy2228/ConvRML/experiments/experiment4_generalized_20261101/output/web_data/data.json"
    )
    reference = json.loads(reference_path.read_text())
    e.audit_manifest(config.manifest)
    models, provenance = e.load_arms(config)
    request = dict(
        schema="exp4_error_maps_v1",
        reference_sha256=e.sha(reference_path),
        source_sha256=e.sha(Path(__file__)),
        palette_sha256=e.sha(Path(__file__).with_name("heatmap_colors.py")),
        checkpoints={a: v["checkpoint_sha256"] for a, v in provenance.items()},
    )
    args.output.mkdir(parents=True, exist_ok=True)
    request_path = args.output / "request.json"
    if request_path.exists() and json.loads(request_path.read_text()) != request:
        raise ValueError("Error-map request changed")
    e.write(request_path, request)
    started = time.monotonic()
    reports = {}
    with torch.inference_mode():
        for condition in e.IDS:
            completed = args.output / (condition + ".json")
            if completed.exists():
                reports[condition] = json.loads(completed.read_text())
                continue
            pairs = e.ModifiedPairs(config.manifest, "test", condition)
            if list(pairs.ids[:50]) != reference["ids"]:
                raise ValueError("Example IDs changed")
            maximum = {a: dict(psnr=0.0, ssim=0.0, mae=0.0) for a in models}
            for index, batch in enumerate(
                DataLoader(
                    Subset(pairs, range(50)),
                    batch_size=1,
                    num_workers=2,
                    pin_memory=True,
                )
            ):
                y, x = e.move(batch)
                for arm, model in models.items():
                    prediction = model.center(y).float().clamp(0, 1)
                    e.finite(prediction, x)
                    metrics = e.reconstruction_metrics(prediction, x)
                    original = reference["results"][condition]["arms"][arm]["examples"][
                        index
                    ]
                    for key, tolerance in dict(psnr=0.001, ssim=5e-5, mae=2e-5).items():
                        difference = abs(float(metrics[key][0]) - original[key])
                        maximum[arm][key] = max(maximum[arm][key], difference)
                        if difference > tolerance:
                            raise ValueError(
                                f"Replay mismatch: {condition}/{arm}/{index}/{key}: {difference}"
                            )
                    error = (prediction - x).abs()[0].mean(0).cpu().numpy()
                    if abs(float(error.mean()) - float(metrics["mae"][0])) > 1e-7:
                        raise ValueError("Error-map mean differs from MAE")
                    path = args.output / f"errors/{condition}/{arm}/{index:03d}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(colorize(error, np.zeros(error.shape, bool))).save(
                        path
                    )
                if (index + 1) % 10 == 0:
                    e.write(
                        args.output / "progress.json",
                        dict(
                            condition=condition,
                            processed=index + 1,
                            total=50,
                            seconds=time.monotonic() - started,
                        ),
                    )
                    print(condition, index + 1, "/50", flush=True)
            reports[condition] = dict(count=50, maximum_replay_difference=maximum)
            e.write(completed, reports[condition])
    for arm, row in provenance.items():
        if e.sha(row["checkpoint"]) != row["checkpoint_sha256"]:
            raise ValueError("Checkpoint changed during replay")
    paths = sorted((args.output / "errors").rglob("*.png"))
    if len(paths) != 2200:
        raise ValueError("Expected 2,200 absolute-error maps")
    manifest = {
        str(p.relative_to(args.output)): dict(sha256=e.sha(p), bytes=p.stat().st_size)
        for p in paths
    }
    data = dict(
        schema="exp4_error_maps_v1",
        definition="Mean RGB |clip(reconstruction,0,1) - ground truth|, computed from full-precision model output before display quantization.",
        scale=[0, 1],
        palette="raw DiffuserCam blue-to-red",
        ids=reference["ids"],
        conditions=list(e.IDS),
        arms=list(models),
        reports=reports,
        request=request,
        files=manifest,
    )
    e.write(args.output / "error-maps.json", data)
    e.write(
        args.output / "READY.json",
        dict(
            passed=True,
            maps=len(paths),
            metadata_sha256=e.sha(args.output / "error-maps.json"),
        ),
    )
    print("READY", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    main(p.parse_args())
