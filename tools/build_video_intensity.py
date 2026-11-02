"""Verify completed frame correlations, then export demo data, CSV and figures."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

REPO = Path(__file__).resolve().parents[1]
METHODS = ("qutcc", "im2im")
COLORS = dict(qutcc="#178a79", im2im="#c7732c")
LABELS = dict(qutcc="QUTCC", im2im="Im2im")
SCHEMA = "video_intensity_correlation_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(source, reference):
    data_path = source / "data.json"
    ready = json.loads((source / "READY.json").read_text())
    if (
        ready.get("passed") is not True
        or ready["schema"] != SCHEMA
        or ready["data_sha256"] != sha(data_path)
    ):
        raise ValueError("Incomplete or changed analysis export")
    data = json.loads(data_path.read_text())
    if data["schema"] != SCHEMA or data["request"]["reference_sha256"] != sha(
        reference
    ):
        raise ValueError("Video reference changed")
    if data["request"]["analyzer_sha256"] != sha(
        REPO / "tools/analyze_video_intensity.py"
    ):
        raise ValueError("Analysis source differs from the reviewed implementation")
    original = json.loads(reference.read_text())
    if set(data["videos"]) != {v["id"] for v in original["videos"]}:
        raise ValueError("Incomplete video set")
    count = 0
    for video in original["videos"]:
        exported = data["videos"][video["id"]]
        if exported["frames"] != video["frames"]:
            raise ValueError("Wrong frame count")
        count += exported["frames"]
        for method in METHODS:
            meta = data["models"][method]
            if (
                meta["checkpoint_sha256"]
                != video["models"][method]["checkpoint_sha256"]
                or meta["calibration"] != video["models"][method]["calibration"]
            ):
                raise ValueError("Different model/calibration")
            rows = exported["models"][method]["rows"]
            if len(rows) != video["frames"]:
                raise ValueError("Missing frames")
            for index, row in enumerate(rows):
                if (
                    row["frame"] != index + 1
                    or row["filename"]
                    != video["models"][method]["per_frame"][index]["filename"]
                ):
                    raise ValueError("Frame correspondence changed")
                if not 0 <= row["valid_pixels"] <= row["total_pixels"] == 270 * 480:
                    raise ValueError("Invalid pixel count")
                if (
                    row["mean_width_replay_difference"] > 2e-5
                    or row["mean_intensity_replay_difference"] > 5e-5
                ):
                    raise ValueError("Numerical replay failed")
                for key in ("pearson", "spearman"):
                    value = row[key]
                    if value is not None and not (
                        np.isfinite(value) and -1.000000001 <= value <= 1.000000001
                    ):
                        raise ValueError("Invalid coefficient")
        if any(
            q["valid_pixels"] != i["valid_pixels"]
            for q, i in zip(
                exported["models"]["qutcc"]["rows"], exported["models"]["im2im"]["rows"]
            )
        ):
            raise ValueError("Models used different spatial pixels")
    if count != ready["frame_count"] or count != 1580:
        raise ValueError("Expected all 1,580 source frames")
    return data


def draw(axis, video, metric):
    for method in METHODS:
        rows = video["models"][method]["rows"]
        values = [row[metric] if row[metric] is not None else np.nan for row in rows]
        axis.plot(
            np.arange(1, len(rows) + 1),
            values,
            color=COLORS[method],
            lw=1.0,
            label=LABELS[method],
        )
    axis.set_ylim(-1, 1)
    axis.set_xlim(1, video["frames"])
    axis.set_yticks([-1, -0.5, 0, 0.5, 1])
    axis.axhline(0, color="#88939a", lw=0.65, ls="--")
    axis.grid(alpha=0.18)
    axis.set_xlabel("Frame")
    axis.set_ylabel("Spearman ρ" if metric == "spearman" else "Pearson r")
    axis.xaxis.set_major_locator(MaxNLocator(6, integer=True))
    axis.set_title(video["label"], loc="left", fontsize=11)


def main(args):
    data = verify(args.source, args.reference)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "data.json").write_text(
        json.dumps(data, indent=2, allow_nan=False) + "\n"
    )
    ordered = list(data["videos"].items())
    overview, axes = plt.subplots(
        len(ordered),
        2,
        figsize=(12, 2.4 * len(ordered)),
        squeeze=False,
        layout="constrained",
    )
    overview.suptitle(
        "Pixel brightness vs uncertainty, frame by frame\nSpearman rank correlation (left) · Pearson linear correlation (right)",
        fontsize=14,
    )
    for row, (name, video) in enumerate(ordered):
        for col, metric in enumerate(("spearman", "pearson")):
            draw(axes[row, col], video, metric)
        if row == 0:
            axes[row, 0].legend(loc="lower right", ncols=2, fontsize=9)
        figure, panels = plt.subplots(2, 1, figsize=(10, 6.2), layout="constrained")
        figure.suptitle(
            video["label"] + " · reconstructed brightness vs interval width"
        )
        for panel, metric in zip(panels, ("spearman", "pearson")):
            draw(panel, video, metric)
            panel.legend(loc="lower right", ncols=2, fontsize=9)
        for extension in ("png", "pdf"):
            figure.savefig(args.output / (name + "." + extension), dpi=180)
        plt.close(figure)
        fields = ["frame"] + [
            method + "_" + key
            for method in METHODS
            for key in ("spearman", "pearson", "valid_pixels", "total_pixels")
        ]
        with (args.output / (name + ".csv")).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for index in range(video["frames"]):
                result = dict(frame=index + 1)
                for method in METHODS:
                    value = video["models"][method]["rows"][index]
                    result.update(
                        {
                            method + "_" + key: value[key]
                            for key in (
                                "spearman",
                                "pearson",
                                "valid_pixels",
                                "total_pixels",
                            )
                        }
                    )
                writer.writerow(result)
    for extension in ("png", "pdf"):
        overview.savefig(args.output / ("overview." + extension), dpi=180)
    plt.close(overview)
    print(
        "VERIFIED: 5 videos, 1,580 frames, 2 models; original input order, calibration, and numerical replay match."
    )
    for name, video in ordered:
        print(
            name,
            {
                m: round(
                    float(
                        np.nanmean(
                            [
                                r["spearman"] if r["spearman"] is not None else np.nan
                                for r in video["models"][m]["rows"]
                            ]
                        )
                    ),
                    4,
                )
                for m in METHODS
            },
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--reference", type=Path, default=REPO / "videos-plot/data.json"
    )
    parser.add_argument("--output", type=Path, default=REPO / "videos-plot/intensity")
    main(parser.parse_args())
