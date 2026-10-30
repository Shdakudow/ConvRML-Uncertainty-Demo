"""Replay frozen raw-DiffuserCam models on ordered external frames; export H.264 and widths.

No model training, calibration fitting, temporal smoothing, or per-frame normalization.
Run in the original Unicorn source environment with --source pointing at the paper-style model.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw
import torch
from heatmap_colors import colorize


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VideoWriter:
    """Stream RGB frames to a browser-compatible H.264 encoder without buffering the video."""

    def __init__(self, path, width, height, fps):
        self.process = subprocess.Popen(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-v",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{width}x{height}",
                "-r",
                str(fps),
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-threads",
                "2",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(path),
            ],
            stdin=subprocess.PIPE,
        )

    def write(self, frame):
        self.process.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())

    def close(self):
        self.process.stdin.close()
        assert self.process.wait() == 0, "Video encoding failed"


def stacked_frame(prediction, uncertainty, method, index, heatmap_max=1):
    image = Image.new("RGB", (480, 588), "#101722")
    image.paste(Image.fromarray(prediction), (0, 24))
    image.paste(Image.fromarray(uncertainty), (0, 318))
    draw = ImageDraw.Draw(image)
    draw.text((10, 6), f"{method} reconstruction | frame {index}", fill="white")
    draw.text(
        (10, 300),
        f"Uncertainty = upper - lower | fixed scale 0 - {heatmap_max:g}",
        fill="white",
    )
    return np.asarray(image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--method", choices=["qutcc", "im2im"], required=True)
    parser.add_argument(
        "--video",
        choices=["video1", "video4", "video6", "video7", "video10"],
        required=True,
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=10,
        help="Presentation fps, explicitly recorded; not a verified sensor frame rate",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--output-dir", type=Path, help="Separate presentation export directory"
    )
    parser.add_argument("--rotation", type=int, choices=[0, 180], default=0)
    parser.add_argument("--heatmap-max", type=float, default=1)
    parser.add_argument(
        "--reference",
        type=Path,
        help="Original reports: verify replay and retain their numerical metrics",
    )
    args = parser.parse_args()
    assert args.fps > 0 and 0 < args.heatmap_max <= 1
    sys.path.insert(0, str(args.source))
    from model import Model

    torch.set_num_threads(2)
    torch.manual_seed(20261030)
    checkpoint = args.source / "results/raw" / args.method / "checkpoints/epoch_050.pt"
    calibration_path = (
        args.source / "results/raw" / args.method / "evaluation/epoch_050/report.json"
    )
    calibration = json.loads(calibration_path.read_text())["calibration"]
    saved = torch.load(checkpoint, map_location="cpu", weights_only=False)
    assert saved["epoch"] == 50 and saved["config"]["method"] == args.method
    model = Model(args.method)
    model.load_state_dict(saved["model"], strict=True)
    del saved
    model = model.to(args.device).eval().requires_grad_(False)
    paths = sorted(
        (args.workdir / "inputs" / args.video).glob("*.png"),
        key=lambda p: int(re.search(r"(\d{4})$", p.stem).group()),
    )
    expected = {
        "video1": 226,
        "video4": 280,
        "video6": 339,
        "video7": 397,
        "video10": 338,
    }
    numbers = [int(re.search(r"(\d{4})$", p.stem).group()) for p in paths]
    assert len(paths) == expected[args.video]
    first_source_frame = 0 if args.video == "video10" else 1
    assert numbers == list(
        range(first_source_frame, first_source_frame + len(paths))
    ), numbers
    out = (args.output_dir or args.workdir / "outputs") / args.video / args.method
    out.mkdir(parents=True, exist_ok=True)
    reference = None
    maximum_width_difference = 0.0
    if args.reference:
        reference = json.loads(
            (args.reference / args.video / args.method / "report.json").read_text()
        )
        assert reference["checkpoint_sha256"] == sha256(checkpoint)
        assert reference["calibration"] == calibration and reference["frames"] == len(
            paths
        )
    writers = {
        "reconstruction": VideoWriter(out / "reconstruction.mp4", 480, 270, args.fps),
        "uncertainty": VideoWriter(out / "uncertainty.mp4", 480, 270, args.fps),
        "stacked": VideoWriter(
            out / "reconstruction_uncertainty.mp4", 480, 588, args.fps
        ),
    }
    rows = []
    previous_prediction = None
    previous_width = None
    started = time.monotonic()
    try:
        with torch.inference_mode():
            for index, path in enumerate(paths, 1):
                pixels = np.asarray(Image.open(path).convert("RGB")).copy()
                assert pixels.shape == (270, 480, 3)
                y = (
                    torch.from_numpy(pixels)
                    .permute(2, 0, 1)[None]
                    .float()
                    .to(args.device)
                    / 255
                )
                if args.method == "qutcc":
                    prediction = model(y)
                    lower = model(y, y.new_full((1,), calibration["lower_q"]))
                    upper = model(y, y.new_full((1,), calibration["upper_q"]))
                else:
                    result = model(y)
                    prediction = result[:, 1]
                    lower = prediction - calibration["scales"]["lower"] * (
                        prediction - result[:, 0]
                    ).clamp_min(1e-6)
                    upper = prediction + calibration["scales"]["upper"] * (
                        result[:, 2] - prediction
                    ).clamp_min(1e-6)
                assert all(torch.isfinite(v).all() for v in (prediction, lower, upper))
                raw_width = float((upper - lower).mean())
                lower, upper, prediction = [
                    v[0].float().clamp(0, 1).cpu().numpy()
                    for v in (lower, upper, prediction)
                ]
                width = upper.astype(np.float64) - lower.astype(np.float64)
                width_map = width.mean(axis=0)
                crossing = np.any(lower > upper, axis=0)
                heatmap = colorize(width_map / args.heatmap_max, crossing)
                rgb = (
                    np.rint(prediction.transpose(1, 2, 0) * 255)
                    .clip(0, 255)
                    .astype(np.uint8)
                )
                # Rotate the exported images only; the model receives the original input.
                if args.rotation == 180:
                    rgb, heatmap = np.rot90(rgb, 2), np.rot90(heatmap, 2)
                writers["reconstruction"].write(rgb)
                writers["uncertainty"].write(heatmap)
                writers["stacked"].write(
                    stacked_frame(
                        rgb, heatmap, args.method.upper(), index, args.heatmap_max
                    )
                )
                if index == 1:
                    Image.fromarray(rgb).save(out / "poster.png")
                    Image.fromarray(heatmap).save(out / "uncertainty_poster.png")
                    Image.fromarray(
                        np.rot90(pixels, 2) if args.rotation else pixels
                    ).save(out / "measurement_poster.png")
                rows.append(
                    dict(
                        frame=index,
                        filename=path.stem,
                        seconds=(index - 1) / args.fps,
                        mean_interval_width=float(width.mean()),
                        width_raw=raw_width,
                        crossing_fraction=float(np.mean(lower > upper)),
                        mean_prediction=float(prediction.mean()),
                        mean_measurement=float(pixels.mean() / 255),
                        prediction_frame_change=(
                            None
                            if previous_prediction is None
                            else float(np.abs(prediction - previous_prediction).mean())
                        ),
                        width_frame_change=(
                            None
                            if previous_width is None
                            else float(np.abs(width_map - previous_width).mean())
                        ),
                    )
                )
                if reference is not None:
                    original = reference["per_frame"][index - 1]
                    assert original["filename"] == path.stem
                    difference = abs(
                        rows[-1]["mean_interval_width"]
                        - original["mean_interval_width"]
                    )
                    maximum_width_difference = max(maximum_width_difference, difference)
                    assert difference < 0.00002, (index, difference)
                    assert (
                        abs(rows[-1]["mean_prediction"] - original["mean_prediction"])
                        < 0.00005
                    )
                    # Presentation changes do not replace the original scientific measurements.
                    rows[-1] = dict(original, seconds=(index - 1) / args.fps)
                previous_prediction, previous_width = prediction, width_map
                if index % 50 == 0:
                    print(
                        args.video,
                        args.method,
                        index,
                        "/",
                        len(paths),
                        "frames",
                        flush=True,
                    )
    finally:
        for writer in writers.values():
            writer.close()
    values = np.array([r["mean_interval_width"] for r in rows])
    mean = float(values.mean())
    summary = dict(
        video=args.video,
        method=args.method,
        epoch=50,
        frames=len(rows),
        fps=args.fps,
        fps_status="Presentation rate; acquisition frame rate unverified",
        mean_interval_width=mean,
        std_interval_width=float(values.std()),
        coefficient_of_variation=float(values.std() / mean) if mean != 0 else None,
        minimum=float(values.min()),
        maximum=float(values.max()),
        p05=float(np.quantile(values, 0.05)),
        p95=float(np.quantile(values, 0.95)),
        linear_slope_per_frame=float(np.polyfit(np.arange(len(values)), values, 1)[0]),
        ground_truth_available=False,
        actual_coverage=None,
        checkpoint=str(checkpoint),
        checkpoint_sha256=sha256(checkpoint),
        calibration=calibration,
        calibration_refitted=False,
        device=torch.cuda.get_device_name() if args.device == "cuda" else args.device,
        precision="float32",
        seconds=time.monotonic() - started,
        heatmap_range=[0, args.heatmap_max],
        heatmap_palette="raw DiffuserCam blue-to-red",
        display_rotation_degrees=args.rotation,
        reference_metrics=str(args.reference) if args.reference else None,
        original_metric_values_retained=reference is not None,
        replay_max_width_difference=maximum_width_difference if reference else None,
        interval_definition="RGB pixel mean of clip(upper,0,1) - clip(lower,0,1)",
        per_frame=rows,
    )
    (out / "report.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    with (out / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print("COMPLETE", args.video, args.method, mean, flush=True)


if __name__ == "__main__":
    main()
