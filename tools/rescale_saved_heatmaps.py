"""Render saved auxiliary error/width arrays on the demo's fixed 0–1 scale.

No models run. Brightness and dropout-sweep metrics are checked against their
saved float arrays and remain unchanged. Only map PNGs and scale metadata change.
"""

import argparse
import json
from pathlib import Path

from matplotlib import colormaps
from matplotlib import pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
COLORS = np.array(
    [[8, 13, 36], [48, 54, 154], [188, 69, 146], [250, 159, 105], [255, 243, 188]],
    dtype=float,
)


def save_map(path, values, palette):
    values = np.clip(values, 0, 1)
    if palette == "legacy":
        levels = np.linspace(0, 1, len(COLORS))
        rgb = np.stack(
            [np.interp(values, levels, COLORS[:, c]) for c in range(3)], -1
        ).astype(np.uint8)
    else:
        rgb = np.round(colormaps[palette](values)[..., :3] * 255).astype(np.uint8)
    Image.fromarray(rgb).save(path)


def rebuild(brightness, dropout):
    for camera in ("rml", "diffuser"):
        folder = ROOT / "test-image-intensified-1/data/paired-v2" / camera
        report = json.loads((folder / "report.json").read_text())
        arrays = np.load(brightness / camera / "float_outputs.npz")
        original_target = arrays["ground_truth"]
        for i, row in enumerate(report["rows"]):
            target = np.clip(original_target * row["gain"], 0, 1)
            for method in report["methods"]:
                pred = arrays[f"{method}_{i}_prediction"][0]
                raw_lower = arrays[f"{method}_{i}_lower_raw"][0]
                raw_upper = arrays[f"{method}_{i}_upper_raw"][0]
                scales = report["factors"][method]
                lower = np.clip(
                    pred - scales["lower"] * np.maximum(pred - raw_lower, 1e-6), 0, 1
                )
                upper = np.clip(
                    pred + scales["upper"] * np.maximum(raw_upper - pred, 1e-6), 0, 1
                )
                prediction = np.clip(pred, 0, 1)
                maps = dict(
                    error=np.abs(prediction - target).mean(0),
                    width=(upper - lower).mean(0),
                )
                assert (
                    abs(float(maps["error"].mean()) - row["models"][method]["mae"])
                    < 2e-6
                )
                assert (
                    abs(float(maps["width"].mean()) - row["models"][method]["width"])
                    < 2e-6
                )
                for kind, values in maps.items():
                    save_map(folder / f"{method}-{i}-{kind}.png", values, "legacy")
        report["heatmap_max"] = 1.0
        report["notes"] = report["notes"].replace(
            "All maps share one camera-specific scale across methods and gains; top 0.5% may saturate.",
            "All maps share the fixed 0–1 normalized-intensity scale across the demo.",
        )
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    folder = ROOT / "corrected-epoch50/dropout-study"
    report = json.loads((folder / "data.json").read_text())
    for camera, study in report["cameras"].items():
        for method in ("mc_005", "mc_010"):
            arrays = np.load(dropout / camera / method / "examples.npz")
            for i, example in enumerate(study["examples"]):
                model = example["models"][method]
                maps = dict(
                    error=np.abs(arrays["prediction"][i] - arrays["target"][i]).mean(0),
                    width=(arrays["upper"][i] - arrays["lower"][i]).mean(0),
                )
                assert abs(float(maps["error"].mean()) - model["metrics"]["mae"]) < 2e-6
                assert (
                    abs(float(maps["width"].mean()) - model["metrics"]["width"]) < 2e-6
                )
                for kind, values in maps.items():
                    save_map(folder / model[kind], values, "magma")
        study["map_max"] = 1.0
    (folder / "data.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        "Rebuilt brightness and dropout example heatmaps at 0–1; saved metrics verified"
    )


def rebuild_analysis_maps(baseline, qutcc):
    """Refresh the expandable map figures; metric curves and reports stay intact."""
    methods = [
        ("im2im", "Im2im"),
        ("ensemble5", "Ensemble · 5"),
        ("mc_005", "MC dropout"),
        ("qutcc", "QUTCC"),
    ]
    output = ROOT / "corrected-epoch50/analysis"
    for camera in ("rml", "diffuser"):
        arrays = {}
        for method, _ in methods:
            folder = qutcc / camera if method == "qutcc" else baseline / camera / method
            with np.load(folder / "examples.npz") as saved:
                arrays[method] = {
                    k: saved[k][0].copy()
                    for k in ("prediction", "target", "measurement", "lower", "upper")
                }
        truth = arrays["im2im"]["target"]
        maps = {}
        for method, values in arrays.items():
            assert np.array_equal(values["target"], truth)
            error = np.abs(np.clip(values["prediction"], 0, 1) - truth).mean(0)
            width = (
                np.clip(values["upper"], 0, 1) - np.clip(values["lower"], 0, 1)
            ).mean(0)
            maps[method] = (error, width)
        fig, axes = plt.subplots(5, 3, figsize=(12, 16), layout="constrained")
        for ax, value, title in zip(
            axes[0],
            [arrays["im2im"]["measurement"], truth, None],
            ["Measurement", "Ground truth", ""],
        ):
            ax.axis("off")
            if value is not None:
                ax.imshow(np.clip(value.transpose(1, 2, 0), 0, 1))
                ax.set_title(title)
        axes[0, 2].text(
            0,
            0.6,
            "Error: mean RGB |prediction − GT|\nWidth: mean RGB (UB − LB)\nFixed map scale: 0–1\nReference calibration",
            fontsize=11,
        )
        for row, (method, label) in enumerate(methods, 1):
            axes[row, 0].imshow(
                np.clip(arrays[method]["prediction"].transpose(1, 2, 0), 0, 1)
            )
            axes[row, 0].set_title(label)
            axes[row, 0].axis("off")
            for ax, value, title in zip(
                axes[row, 1:], maps[method], ["Absolute error", "Interval width"]
            ):
                image = ax.imshow(value, cmap="inferno", vmin=0, vmax=1)
                ax.set_title(title)
                ax.axis("off")
                fig.colorbar(image, ax=ax, fraction=0.04)
        fig.suptitle(f"{camera} · first saved test image · fixed 0–1 display scale")
        fig.savefig(output / f"{camera}_example_01_scale01.png", dpi=140)
        plt.close(fig)
        fig, axes = plt.subplots(4, 4, figsize=(13, 13), layout="constrained")
        for row, (method, label) in enumerate(methods):
            error, width = maps[method]
            for ax, value, title in zip(
                axes[row],
                [error, width, gaussian_filter(error, 1), gaussian_filter(width, 1)],
                ["Error", "Width", "Error, Gaussian σ=1", "Width, Gaussian σ=1"],
            ):
                image = ax.imshow(value, cmap="inferno", vmin=0, vmax=1)
                ax.set_title(title)
                ax.set_xticks([])
                ax.set_yticks([])
            axes[row, 0].set_ylabel(label)
        fig.colorbar(
            image,
            ax=axes.ravel().tolist(),
            shrink=0.6,
            label="Normalized intensity · 0–1",
        )
        fig.suptitle(f"{camera} · raw and smoothed maps · fixed 0–1 display scale")
        fig.savefig(output / f"{camera}_raw_vs_smoothed_scale01.png", dpi=150)
        plt.close(fig)
    print("Rebuilt expandable analysis map figures at 0–1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brightness", type=Path, required=True)
    parser.add_argument("--dropout", type=Path, required=True)
    parser.add_argument("--analysis-baseline", type=Path)
    parser.add_argument("--analysis-qutcc", type=Path)
    args = parser.parse_args()
    rebuild(args.brightness, args.dropout)
    if args.analysis_baseline and args.analysis_qutcc:
        rebuild_analysis_maps(args.analysis_baseline, args.analysis_qutcc)
