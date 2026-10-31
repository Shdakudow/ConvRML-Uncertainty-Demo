"""Publish only Sensor12 / Exp3 saved reconstructions, without rerunning models."""

import argparse
import csv
import json
from pathlib import Path
import shutil

import matplotlib

matplotlib.use("Agg")
import numpy as np
from PIL import Image
from heatmap_colors import colorize, CSS_GRADIENT
from pixel_maps import save_pixel_map

REPO = Path(__file__).resolve().parents[1]
MODELS = {"qutcc": "exp3_qutcc", "im2im": "exp3_im2im"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Local downloaded-TIFF reconstruction report folder"
    )
    parser.add_argument(
        "--pixel-dir", type=Path, help="Export float32 width sidecars here"
    )
    args = parser.parse_args()
    destination = REPO / "named-captures"
    manifest = json.loads((args.source / "inputs/manifest.json").read_text())
    ids = [row["id"] for row in manifest["images"]]
    assert len(ids) == 10 and len(set(ids)) == 10
    predictions = {
        key: np.load(args.source / "results" / name / "sensor12.npz")
        for key, name in MODELS.items()
    }
    reports = {
        key: json.loads((args.source / "results" / name / "report.json").read_text())
        for key, name in MODELS.items()
    }
    widths = {
        key: (
            np.clip(values["upper_raw"], 0, 1) - np.clip(values["lower_raw"], 0, 1)
        ).mean(axis=1)
        for key, values in predictions.items()
    }
    maximum = 1.0
    examples = []
    csv_rows = []
    for index, image in enumerate(manifest["images"]):
        identifier = image["id"]
        folder = destination / "assets" / identifier
        folder.mkdir(parents=True, exist_ok=True)
        png_source = args.source / "images/sensor12" / identifier
        shutil.copyfile(
            png_source / "measurement_full_field.png", folder / "measurement.png"
        )
        example = dict(
            id=identifier,
            name=image["filename"],
            measurement=f"assets/{identifier}/measurement.png",
            models={},
        )
        for key, name in MODELS.items():
            row = next(
                r
                for r in reports[key]["rows"]
                if r["id"] == identifier and r["scaling"] == "sensor12"
            )
            assert row["model"] == name and row["epoch"] == 50
            images = {}
            for kind in ["reconstruction", "lower_bound", "upper_bound"]:
                target = folder / f"{key}_{kind}.png"
                shutil.copyfile(png_source / name / f"{kind}.png", target)
                images[kind] = str(target.relative_to(destination))
            data = predictions[key]
            crossing = np.any(
                np.clip(data["lower_raw"][index], 0, 1)
                > np.clip(data["upper_raw"][index], 0, 1),
                axis=0,
            )
            heatmap = folder / f"{key}_uncertainty.png"
            Image.fromarray(colorize(widths[key][index] / maximum, crossing)).save(
                heatmap
            )
            images["uncertainty"] = str(heatmap.relative_to(destination))
            metrics = {
                k: row[k]
                for k in ["width_clipped", "width_raw", "crossing_clipped", "seconds"]
            }
            # Calculate from calibrated float32 endpoints before PNG conversion.
            lower = np.clip(data["lower_raw"][index], 0, 1).astype(np.float64)
            upper = np.clip(data["upper_raw"][index], 0, 1).astype(np.float64)
            metrics["mean_interval_width"] = float((upper - lower).mean())
            if args.pixel_dir:
                save_pixel_map(
                    args.pixel_dir / identifier / f"{key}.bin.gz",
                    (upper - lower).mean(axis=0),
                    crossing,
                )
            assert (
                abs(float(widths[key][index].mean()) - metrics["width_clipped"]) < 1e-6
            )
            example["models"][key] = dict(images=images, metrics=metrics)
            csv_rows.append(
                dict(
                    image=image["filename"],
                    model=key,
                    epoch=50,
                    scaling="uint16 TIFF / 4095",
                    **metrics,
                    psnr=None,
                    ssim=None,
                    actual_coverage=None,
                )
            )
        examples.append(example)
    data = dict(
        title="Named captures · Sensor12",
        count=len(examples),
        experiment=3,
        epoch=50,
        native_shape=[270, 480, 3],
        preprocessing="TIFF / 4095; 4×4 area downsample; round to 8-bit-equivalent values; no per-image contrast stretching or rotation",
        sensor_range_status="12-bit acquisition is an assumption, not confirmed by the 16-bit TIFF container",
        ground_truth_available=False,
        clipping="Reconstruction and calibrated bounds clipped to [0,1]",
        heatmap=dict(
            min=0,
            max=maximum,
            units="normalized intensity",
            definition="Mean over RGB of clipped upper − lower",
            saturation="fixed 0–1 scale shared across the demo",
            crossing_color="#e320c9",
            gradient=CSS_GRADIENT,
        ),
        models={
            key: dict(
                label="QUTCC" if key == "qutcc" else "Im2im",
                epoch=50,
                checkpoint_sha256=report["checkpoint_sha256"],
                calibration=report["calibration"],
                calibration_kind=report["calibration_kind"],
                inference_device=report["device"],
                precision=report["precision"],
            )
            for key, report in reports.items()
        },
        examples=examples,
        mean_interval_width={
            key: float(
                np.mean(
                    [
                        example["models"][key]["metrics"]["mean_interval_width"]
                        for example in examples
                    ]
                )
            )
            for key in MODELS
        },
    )
    (destination / "data.json").write_text(json.dumps(data, indent=2) + "\n")
    with (destination / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(csv_rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(csv_rows)
    print("Prepared", len(examples), "Sensor12 captures, Exp3 models only")


if __name__ == "__main__":
    main()
