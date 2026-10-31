"""Export model-agreement curves and selected disagreement examples from saved data."""

import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess

import imageio_ffmpeg
import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib import patheffects
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image
from scipy import stats

from heatmap_colors import colorize
from pixel_maps import load_pixel_map

REPO = Path(__file__).resolve().parents[1]


def video_image(video, method, frame):
    path = (
        REPO / "videos-plot/assets" / video / method / "reconstruction_uncertainty.mp4"
    )
    result = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"select=eq(n\\,{frame-1})",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return np.asarray(Image.open(BytesIO(result.stdout)).convert("RGB"))[24:294]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("--local", type=Path, required=True)
    args = parser.parse_args()
    args.local.mkdir(parents=True, exist_ok=True)
    destination = REPO / "videos-plot/agreement"
    agreement = json.loads((REPO / "uncertainty_agreement.json").read_text())
    captures = json.loads((REPO / "named-captures/data.json").read_text())
    figure, axes = plt.subplots(3, 2, figsize=(14, 11), constrained_layout=True)
    for axis, (video, report) in zip(axes.ravel(), agreement["videos"].items()):
        rows = report["rows"]
        for key, color in [("pearson", "#2678bb"), ("spearman", "#8c4bb3")]:
            axis.plot(
                [r["frame"] for r in rows],
                [r[key] for r in rows],
                label=key.title(),
                color=color,
                linewidth=1,
            )
        worst = rows[report["low_agreement_frames"][0] - 1]
        axis.scatter(
            [worst["frame"]], [worst["spearman"]], color="#b32424", s=20, zorder=3
        )
        axis.annotate(
            f"Frame {worst['frame']}",
            (worst["frame"], worst["spearman"]),
            xytext=(5, 7),
            textcoords="offset points",
            fontsize=8,
        )
        axis.set(
            title=video.replace("video", "Video ") + f" · {len(rows)} frames",
            xlabel="Frame",
            ylabel="Inter-model correlation",
            ylim=(0, 1),
        )
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8, loc="lower right")
    axis = axes.ravel()[-1]
    named = sorted(agreement["captures"].items(), key=lambda pair: pair[1]["spearman"])
    axis.barh(
        [name for name, _ in named],
        [row["spearman"] for _, row in named],
        color="#8c4bb3",
    )
    axis.set(
        title="Named captures · Spearman agreement",
        xlim=(0, 1),
        xlabel="Inter-model Spearman ρ",
    )
    axis.tick_params(axis="y", labelsize=8)
    axis.grid(axis="x", alpha=0.2)
    figure.suptitle(
        "QUTCC–Im2im uncertainty-map agreement\nSame-pixel RGB-mean widths; no ground truth or reconstruction-error claim",
        fontsize=14,
    )
    figure.savefig(destination / "overview.png", dpi=160)
    figure.savefig(args.local / "overview.png", dpi=160)
    with PdfPages(args.local / "Uncertainty_Agreement.pdf") as pdf:
        pdf.savefig(figure)
        plt.close(figure)
        cases = [
            (video, report["low_agreement_frames"][0])
            for video, report in agreement["videos"].items()
        ]
        cases.sort(
            key=lambda item: agreement["videos"][item[0]]["rows"][item[1] - 1][
                "spearman"
            ]
        )
        cases = cases[:3] + [(named[0][0], None)]
        figure, axes = plt.subplots(
            len(cases), 5, figsize=(17, 11), constrained_layout=True
        )
        findings = []
        for r, (name, frame) in enumerate(cases):
            if frame is not None:
                row = agreement["videos"][name]["rows"][frame - 1]
                prefix = args.assets / "videos" / name
                paths = {
                    m: prefix / m / f"frame_{frame:04d}.bin.gz"
                    for m in ["qutcc", "im2im"]
                }
                images = [video_image(name, m, frame) for m in ["qutcc", "im2im"]]
                title = f"{name} · frame {frame}"
            else:
                row = agreement["captures"][name]
                paths = {
                    m: args.assets / "captures" / name / (m + ".bin.gz")
                    for m in ["qutcc", "im2im"]
                }
                capture = next(c for c in captures["examples"] if c["id"] == name)
                images = [
                    np.asarray(
                        Image.open(
                            REPO
                            / "named-captures"
                            / capture["models"][m]["images"]["reconstruction"]
                        )
                    )
                    for m in ["qutcc", "im2im"]
                ]
                title = name
            q, cq = load_pixel_map(paths["qutcc"])
            i, ci = load_pixel_map(paths["im2im"])
            valid = np.isfinite(q) & np.isfinite(i) & ~cq & ~ci
            rank_q = np.full(q.shape, np.nan)
            rank_i = rank_q.copy()
            rank_q[valid] = (stats.rankdata(q[valid]) - 1) / (valid.sum() - 1)
            rank_i[valid] = (stats.rankdata(i[valid]) - 1) / (valid.sum() - 1)
            rank_gap = np.abs(rank_q - rank_i)
            panels = images + [
                colorize(q, ~valid),
                colorize(i, ~valid),
                colorize(rank_gap, ~valid),
            ]
            region = row["region"]
            for column, (axis, image) in enumerate(zip(axes[r], panels)):
                axis.imshow(image)
                axis.set_xticks([])
                axis.set_yticks([])
                if r == 0:
                    axis.set_title(
                        [
                            "QUTCC reconstruction",
                            "Im2im reconstruction",
                            "QUTCC width · 0–1",
                            "Im2im width · 0–1",
                            "Rank disagreement · 0–1",
                        ][column],
                        fontsize=10,
                    )
                box = Rectangle(
                    (region["x"] - 0.5, region["y"] - 0.5),
                    30,
                    30,
                    fill=False,
                    edgecolor="#fff200",
                    linewidth=1.3,
                )
                box.set_path_effects(
                    [
                        patheffects.Stroke(linewidth=4, foreground="white"),
                        patheffects.Stroke(linewidth=3, foreground="black"),
                        patheffects.Normal(),
                    ]
                )
                axis.add_patch(box)
            axes[r, 0].set_ylabel(
                title + f"\nr={row['pearson']:.3f}; ρ={row['spearman']:.3f}", fontsize=9
            )
            patch = np.s_[
                region["y"] : region["y"] + 30, region["x"] : region["x"] + 30
            ]
            findings.append(
                dict(
                    name=name,
                    frame=frame,
                    pearson=row["pearson"],
                    spearman=row["spearman"],
                    mean_width_qutcc=row["mean_width_qutcc"],
                    mean_width_im2im=row["mean_width_im2im"],
                    region=region,
                    region_qutcc_width=float(np.mean(q[patch][valid[patch]])),
                    region_im2im_width=float(np.mean(i[patch][valid[patch]])),
                    region_qutcc_percentile=float(np.nanmean(rank_q[patch])),
                    region_im2im_percentile=float(np.nanmean(rank_i[patch])),
                )
            )
        figure.suptitle(
            "Lowest-agreement examples: different locations can have wide intervals despite similar image-average widths\nBoxes: 30×30 patches with strongest rank disagreement. Reconstruction panels are display exports; statistics use numerical maps.",
            fontsize=12,
        )
        figure.savefig(destination / "examples.png", dpi=160)
        figure.savefig(args.local / "examples.png", dpi=160)
        pdf.savefig(figure)
        plt.close(figure)
    (args.local / "selected_findings.json").write_text(
        json.dumps(findings, indent=2) + "\n"
    )
    shutil.copyfile(
        REPO / "uncertainty_agreement.json", args.local / "uncertainty_agreement.json"
    )
    for path in destination.glob("*.csv"):
        shutil.copyfile(path, args.local / path.name)
    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
