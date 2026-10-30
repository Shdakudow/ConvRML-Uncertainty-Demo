"""Collect completed video inference into a public demo and a standalone local report."""

import argparse
import csv
import json
from pathlib import Path
import shutil

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
from PIL import Image, ImageDraw
from heatmap_colors import CSS_GRADIENT

REPO = Path(__file__).resolve().parents[1]
METHODS = {"qutcc": "QUTCC", "im2im": "Im2im"}
COLORS = {"qutcc": "#197a70", "im2im": "#bd6220"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--local", type=Path, required=True)
    parser.add_argument(
        "--plot-max",
        type=float,
        default=0.25,
        help="Width-plot limit, independent of the video heatmap range",
    )
    args = parser.parse_args()
    assert args.plot_max > 0
    destination = REPO / "videos-plot"
    args.local.mkdir(parents=True, exist_ok=True)
    videos = []
    overall = []
    with PdfPages(args.local / "video_interval_width_report.pdf") as pdf:
        for name in ["video1", "video4", "video6", "video7", "video10"]:
            models = {}
            combined = []
            figure, axes = plt.subplots(
                2, 1, figsize=(11, 7), sharex=True, constrained_layout=True
            )
            for method, label in METHODS.items():
                source = args.source / name / method
                report = json.loads((source / "report.json").read_text())
                assert (
                    report["video"] == name
                    and report["method"] == method
                    and report["epoch"] == 50
                )
                assert not report["calibration_refitted"]
                assert (
                    report.get("heatmap_palette") == "raw DiffuserCam blue-to-red"
                ), "Rebuild video colors from float widths before changing their legend"
                assert (
                    report["heatmap_range"][0] == 0
                    and 0 < report["heatmap_range"][1] <= 1
                )
                maximum = report["heatmap_range"][1]
                rows = report["per_frame"]
                values = np.array([row["mean_interval_width"] for row in rows])
                cumulative = np.cumsum(values) / np.arange(1, len(values) + 1)
                display_rows = [
                    dict(row, cumulative_mean_interval_width=float(value))
                    for row, value in zip(rows, cumulative)
                ]
                assert abs(values.mean() - report["mean_interval_width"]) < 1e-12
                for path in source.iterdir():
                    if path.suffix not in (".mp4", ".png", ".json", ".csv"):
                        continue
                    # The web viewer needs the stacked MP4; retain separate exports locally.
                    if (
                        path.suffix != ".mp4"
                        or path.name == "reconstruction_uncertainty.mp4"
                    ):
                        target = destination / "assets" / name / method / path.name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if path.suffix == ".csv":
                            target.write_text(path.read_text())
                        else:
                            shutil.copyfile(path, target)
                    local = args.local / name / method / path.name
                    local.parent.mkdir(parents=True, exist_ok=True)
                    if path.suffix == ".csv":
                        local.write_text(path.read_text())
                    else:
                        shutil.copyfile(path, local)
                poster = Image.new("RGB", (480, 588), "#101722")
                poster.paste(Image.open(source / "poster.png"), (0, 24))
                poster.paste(Image.open(source / "uncertainty_poster.png"), (0, 318))
                draw = ImageDraw.Draw(poster)
                draw.text((10, 6), f"{label} reconstruction | frame 1", fill="white")
                draw.text(
                    (10, 300),
                    f"Uncertainty = upper - lower | fixed scale 0 - {maximum:g}",
                    fill="white",
                )
                poster.save(
                    destination / "assets" / name / method / "stacked_poster.png"
                )
                poster.save(args.local / name / method / "stacked_poster.png")
                models[method] = dict(
                    report,
                    per_frame=display_rows,
                    video=f"assets/{name}/{method}/reconstruction_uncertainty.mp4?v=20261030bluered",
                    poster=f"assets/{name}/{method}/stacked_poster.png?v=20261030bluered",
                )
                combined.extend(dict(model=label, **row) for row in display_rows)
                overall.append(
                    dict(
                        video=name,
                        model=label,
                        **{
                            key: report[key]
                            for key in [
                                "frames",
                                "mean_interval_width",
                                "std_interval_width",
                                "coefficient_of_variation",
                                "minimum",
                                "maximum",
                                "p05",
                                "p95",
                            ]
                        },
                    )
                )
                for axis in axes:
                    axis.plot(
                        np.arange(1, len(values) + 1),
                        values,
                        color=COLORS[method],
                        label=label,
                        linewidth=1.4,
                        alpha=0.4,
                    )
                    axis.plot(
                        np.arange(1, len(values) + 1),
                        cumulative,
                        color=COLORS[method],
                        linewidth=2.5,
                        label=f"{label} cumulative average",
                    )
                    axis.set_ylabel("Mean interval width")
                    axis.grid(alpha=0.2)
            assert len({report["frames"] for report in models.values()}) == 1
            frames, fps = report["frames"], report["fps"]
            assert (
                len({tuple(model["heatmap_range"]) for model in models.values()}) == 1
            )
            axes[0].set_ylim(0, args.plot_max)
            axes[0].set_title(f"{name} - fixed 0-{args.plot_max:g} plot scale")
            axes[1].set_title("Detail: width variation over time")
            axes[1].set_xlabel("Frame (source order)")
            axes[0].legend(fontsize=8, loc="upper right")
            axes[1].legend(fontsize=8, loc="upper right")
            figure.suptitle(
                f"DiffuserCam {name}: calibrated intervals, epoch 50\nThin = frame mean; thick = cumulative average. No paired ground truth."
            )
            plot = destination / "assets" / name / "width_plot.png"
            figure.savefig(plot, dpi=160)
            figure.savefig(args.local / name / "width_plot.png", dpi=160)
            pdf.savefig(figure)
            plt.close(figure)
            csv_path = destination / "assets" / name / "frame_metrics.csv"
            with csv_path.open("w", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=list(combined[0]), lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(combined)
            shutil.copyfile(csv_path, args.local / name / "frame_metrics.csv")
            videos.append(
                dict(
                    id=name,
                    label=name.replace("video", "Video "),
                    frames=frames,
                    fps=fps,
                    models=models,
                    csv=f"assets/{name}/frame_metrics.csv?v=20261030bluered",
                    plot=str(plot.relative_to(destination)) + "?v=20261030bluered",
                )
            )
    manifest = json.loads((args.source.parent / "drive_manifest.json").read_text())
    data = dict(
        videos=videos,
        source=manifest["drive_folder"],
        ground_truth_available=False,
        heatmap_range=report["heatmap_range"],
        width_plot_range=[0, args.plot_max],
        display_rotation_degrees=report.get("display_rotation_degrees", 0),
        heatmap_gradient=CSS_GRADIENT,
        notes=[
            "External DiffuserCam videos 1, 4, 6, 7, and 10. All 1,580 TIFF frames are used in original numerical order; the supplied reconstruction GIFs are references, not ground truth.",
            "Video TIFFs are uint8: fixed division by 255, 4x4 area downsample to RGB 270x480, then rounding to the training loader’s uint8-equivalent inputs. No per-frame stretching, automatic exposure normalization, input rotation, or background subtraction.",
            "The source README’s /4095 background-corrected recipe applies to the original pretrained reconstruction pipeline. It is not silently applied to these uint8 TIFFs or substituted for the current model’s preprocessing.",
            "Clean raw DiffuserCam QUTCC and Im2im epoch-50 checkpoints are frozen. QUTCC uses its saved calibrated quantiles; Im2im uses its saved separate lower/upper calibration scales. There is no fitting or training on the videos.",
            "Each frame is reconstructed independently. Prediction and bounds are clipped to [0,1]. Mean width is calculated from float endpoints before MP4 encoding; the heatmap averages width over RGB. Magenta identifies crossed bounds.",
            f"Reconstruction and uncertainty panels are rotated {report.get('display_rotation_degrees', 0)} degrees after inference. Labels remain upright; the reconstruction stays above the uncertainty map.",
            f"The shared uncertainty heatmap color range is 0–{maximum:g}. The default mean-width plot axis is independently set to 0–{args.plot_max:g}. Neither display range changes numerical width measurements.",
            f"Playback is presented at {fps:g} fps; the acquisition frame rate is unverified. Every source frame is retained, with no temporal interpolation. Plots use frame numbers. Spatial uncertainty maps can change even if their image-average width stays constant.",
            "No paired ground truth is supplied, so actual coverage, PSNR, SSIM, LPIPS, and uncertainty-error correlation cannot be measured on these videos. Calibration on the training-camera distribution does not certify 90% coverage here.",
        ],
    )
    (destination / "data.json").write_text(
        json.dumps(data, indent=2, allow_nan=False) + "\n"
    )
    (args.local / "summary.json").write_text(
        json.dumps(data, indent=2, allow_nan=False) + "\n"
    )
    with (args.local / "summary_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(overall[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(overall)
    (args.local / "README.txt").write_text(
        "DiffuserCam video reconstruction and uncertainty\n\n"
        + "\n\n".join(data["notes"])
        + "\n\nOpen each reconstruction_uncertainty.mp4 for reconstruction above and uncertainty below. The CSVs preserve per-frame numerical metrics.\n"
    )
    print(json.dumps(overall, indent=2))


if __name__ == "__main__":
    main()
