"""Measure within-frame brightness/interval-width association in frozen videos.

Intensity is each model's clipped reconstruction averaged over RGB, not measured
illumination or sensor intensity. Width is the RGB mean of clipped UB minus LB.
Both models use the same finite, uncrossed pixel mask in each frame. Correlations
are descriptive: spatially adjacent pixels are not independent replicates.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import numpy as np
from PIL import Image
from scipy import stats

METHODS = ("qutcc", "im2im")
SCHEMA = "video_intensity_correlation_v1"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def frame_correlations(intensities, widths, crossed):
    """Use matching spatial pixels, average tied ranks, and mark constants null."""
    shapes = {
        np.asarray(v).shape
        for group in (intensities, widths, crossed)
        for v in group.values()
    }
    if len(shapes) != 1 or len(next(iter(shapes))) != 2:
        raise ValueError("Expected matching H×W maps for both models")
    if any(set(group) != set(METHODS) for group in (intensities, widths, crossed)):
        raise ValueError("Both model maps are required")
    valid = np.ones(next(iter(shapes)), dtype=bool)
    for method in METHODS:
        valid &= (
            np.isfinite(intensities[method])
            & np.isfinite(widths[method])
            & ~crossed[method]
        )
    rows = {}
    for method in METHODS:
        intensity = np.asarray(intensities[method], dtype=np.float64)[valid]
        width = np.asarray(widths[method], dtype=np.float64)[valid]
        pearson = spearman = None
        if len(intensity) >= 2 and np.ptp(intensity) > 0 and np.ptp(width) > 0:
            pearson = float(stats.pearsonr(intensity, width).statistic)
            spearman = float(stats.spearmanr(intensity, width).statistic)
        rows[method] = dict(
            pearson=pearson,
            spearman=spearman,
            valid_pixels=int(valid.sum()),
            total_pixels=int(valid.size),
            valid_mean_intensity=float(intensity.mean()) if len(intensity) else None,
            valid_mean_width=float(width.mean()) if len(width) else None,
        )
    return rows


def ordered_inputs(folder, count, video):
    paths = sorted(
        folder.glob("*.png"), key=lambda p: int(re.search(r"(\d{4})$", p.stem).group(1))
    )
    start = 0 if video == "video10" else 1
    if len(paths) != count or [
        int(re.search(r"(\d{4})$", p.stem).group(1)) for p in paths
    ] != list(range(start, start + count)):
        raise ValueError("Missing or unordered source frames")
    return paths


def main(args):
    import torch

    sys.path.insert(0, str(args.source))
    from model import Model

    torch.set_num_threads(2)
    torch.manual_seed(20261030)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    reference = json.loads(args.reference.read_text())
    models, provenance = {}, {}
    for method in METHODS:
        records = [v["models"][method] for v in reference["videos"]]
        expected = records[0]
        if any(
            (r["checkpoint_sha256"], r["calibration"], r["epoch"])
            != (expected["checkpoint_sha256"], expected["calibration"], 50)
            for r in records
        ):
            raise ValueError("Video models/calibration differ between sequences")
        path = args.source / "results/raw" / method / "checkpoints/epoch_050.pt"
        if sha(path) != expected["checkpoint_sha256"]:
            raise ValueError("Checkpoint differs from the published video")
        saved = torch.load(path, map_location="cpu", weights_only=False)
        if (
            saved["epoch"] != 50
            or saved["config"]["method"] != method
            or saved["config"]["camera"] != "raw"
        ):
            raise ValueError("Wrong frozen model identity")
        model = Model(method)
        model.load_state_dict(saved["model"], strict=True)
        models[method] = model.to(args.device).eval().requires_grad_(False)
        provenance[method] = dict(
            epoch=50,
            checkpoint_sha256=expected["checkpoint_sha256"],
            calibration=expected["calibration"],
        )
        del saved
    args.output.mkdir(parents=True, exist_ok=True)
    request = dict(
        schema=SCHEMA,
        reference_sha256=sha(args.reference),
        analyzer_sha256=sha(Path(__file__)),
        original_model_source_sha256=sha(args.source / "model.py"),
        models=provenance,
        torch=torch.__version__,
        cuda=torch.version.cuda,
    )
    request_path = args.output / "request.json"
    if request_path.exists() and json.loads(request_path.read_text()) != request:
        raise ValueError("Refusing to mix different analysis requests")
    write(request_path, request)
    started = time.monotonic()
    videos = {}
    with torch.inference_mode():
        for video in reference["videos"]:
            name = video["id"]
            destination = args.output / (name + ".json")
            if destination.exists():
                videos[name] = json.loads(destination.read_text())
                continue
            paths = ordered_inputs(args.inputs / name, video["frames"], name)
            rows = {method: [] for method in METHODS}
            for frame, path in enumerate(paths, 1):
                receipt = json.loads(path.with_suffix(".json").read_text())
                digest = sha(path)
                if digest != receipt["prepared_sha256"]:
                    raise ValueError(
                        "Prepared input hash differs from its original receipt"
                    )
                pixels = np.array(Image.open(path).convert("RGB"), copy=True)
                if pixels.shape != (270, 480, 3):
                    raise ValueError("Wrong video input dimensions")
                y = (
                    torch.from_numpy(pixels)
                    .permute(2, 0, 1)[None]
                    .float()
                    .to(args.device)
                    / 255
                )
                intensities, widths, crossed, replay = {}, {}, {}, {}
                for method, model in models.items():
                    calibration = provenance[method]["calibration"]
                    if method == "qutcc":
                        p = model(y)
                        lo = model(y, y.new_full((1,), calibration["lower_q"]))
                        hi = model(y, y.new_full((1,), calibration["upper_q"]))
                    else:
                        heads = model(y)
                        p = heads[:, 1]
                        lo = p - calibration["scales"]["lower"] * (
                            p - heads[:, 0]
                        ).clamp_min(1e-6)
                        hi = p + calibration["scales"]["upper"] * (
                            heads[:, 2] - p
                        ).clamp_min(1e-6)
                    if not all(torch.isfinite(v).all() for v in (p, lo, hi)):
                        raise ValueError("Nonfinite video prediction")
                    p, lo, hi = (
                        v[0].float().clamp(0, 1).cpu().numpy() for v in (p, lo, hi)
                    )
                    intensities[method] = p.astype(np.float64).mean(axis=0)
                    widths[method] = (
                        hi.astype(np.float64) - lo.astype(np.float64)
                    ).mean(axis=0)
                    crossed[method] = np.any(lo > hi, axis=0)
                    original = video["models"][method]["per_frame"][frame - 1]
                    width_gap = abs(
                        float(widths[method].mean()) - original["mean_interval_width"]
                    )
                    intensity_gap = abs(float(p.mean()) - original["mean_prediction"])
                    if (
                        original["filename"] != path.stem
                        or width_gap > 2e-5
                        or intensity_gap > 5e-5
                    ):
                        raise ValueError(
                            f"Replay no longer matches the published frame: {name}/{method}/{frame}"
                        )
                    replay[method] = dict(
                        mean_width_replay_difference=width_gap,
                        mean_intensity_replay_difference=intensity_gap,
                    )
                values = frame_correlations(intensities, widths, crossed)
                for method in METHODS:
                    rows[method].append(
                        dict(
                            frame=frame,
                            filename=path.stem,
                            prepared_input_sha256=digest,
                            **values[method],
                            **replay[method],
                        )
                    )
                if frame % 25 == 0 or frame == len(paths):
                    write(
                        args.output / "progress.json",
                        dict(
                            video=name,
                            frame=frame,
                            frames=len(paths),
                            seconds=time.monotonic() - started,
                        ),
                    )
                    print(name, frame, "/", len(paths), flush=True)
            videos[name] = dict(
                label=video["label"],
                frames=len(paths),
                models={m: dict(rows=rows[m]) for m in METHODS},
            )
            write(destination, videos[name])
    for method in METHODS:
        path = args.source / "results/raw" / method / "checkpoints/epoch_050.pt"
        if sha(path) != provenance[method]["checkpoint_sha256"]:
            raise ValueError("Frozen weights changed during analysis")
    data = dict(
        schema=SCHEMA,
        definition="Per-frame spatial association between each model’s own reconstructed brightness and its interval width; not physical illumination, accuracy, or calibration quality.",
        intensity="RGB mean of clipped full-precision prediction",
        uncertainty="RGB mean of clip(upper,0,1) minus clip(lower,0,1)",
        mask="Finite and uncrossed in both models; identical spatial pixels used for both curves",
        primary="spearman",
        pvalues_reported=False,
        temporal_smoothing=False,
        ground_truth_available=False,
        models=provenance,
        request=request,
        seconds=time.monotonic() - started,
        videos=videos,
    )
    write(args.output / "data.json", data)
    write(
        args.output / "READY.json",
        dict(
            passed=True,
            schema=SCHEMA,
            data_sha256=sha(args.output / "data.json"),
            frame_count=sum(v["frames"] for v in videos.values()),
        ),
    )
    print("READY", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("inputs", "source", "reference", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    main(parser.parse_args())
