"""Compare two frozen uncertainty maps without ground truth or model inference.

Each image/frame yields one Pearson and one Spearman coefficient for the model
pair. RGB averaging was performed before saving the float32 width sidecars.
Crossed intervals and nonfinite values in either model are excluded jointly.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import stats

from pixel_maps import load_pixel_map

REPO = Path(__file__).resolve().parents[1]


def compare(task):
    qutcc, crossed_q = load_pixel_map(task["qutcc"])
    im2im, crossed_i = load_pixel_map(task["im2im"])
    assert qutcc.shape == im2im.shape == (270, 480)
    valid = np.isfinite(qutcc) & np.isfinite(im2im) & ~crossed_q & ~crossed_i
    q, i = qutcc[valid].astype(np.float64), im2im[valid].astype(np.float64)
    pearson = spearman = None
    rank_gap = np.full(qutcc.shape, np.nan)
    if len(q) >= 2 and np.ptp(q) > 0 and np.ptp(i) > 0:
        pearson = float(stats.pearsonr(q, i).statistic)
        ranks_q, ranks_i = stats.rankdata(q), stats.rankdata(i)
        spearman = float(stats.pearsonr(ranks_q, ranks_i).statistic)
        rank_gap[valid] = np.abs(ranks_q - ranks_i) / (len(q) - 1)
    regions = []
    for y in range(0, 270, 30):
        for x in range(0, 480, 30):
            patch = rank_gap[y : y + 30, x : x + 30]
            if np.isfinite(patch).sum() >= 450:
                regions.append(
                    dict(
                        x=x,
                        y=y,
                        width=30,
                        height=30,
                        mean_rank_gap=float(np.nanmean(patch)),
                    )
                )
    region = max(regions, key=lambda item: item["mean_rank_gap"]) if regions else None
    return dict(
        id=task["id"],
        frame=task.get("frame"),
        pearson=pearson,
        spearman=spearman,
        valid_pixels=int(valid.sum()),
        total_pixels=int(valid.size),
        mean_width_qutcc=float(np.mean(q)) if len(q) else None,
        mean_width_im2im=float(np.mean(i)) if len(i) else None,
        mean_absolute_width_gap=float(np.mean(np.abs(q - i))) if len(q) else None,
        mean_rank_gap=float(np.nanmean(rank_gap)) if regions else None,
        region=region,
    )


def choose_frames(rows, separation=20, limit=5):
    selected = []
    for row in sorted(
        (r for r in rows if r["spearman"] is not None), key=lambda r: r["spearman"]
    ):
        if all(abs(row["frame"] - frame) >= separation for frame in selected):
            selected.append(row["frame"])
        if len(selected) == limit:
            break
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "assets", type=Path, help="Local checkout of the pixel-map asset branch"
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    manifest = json.loads((args.assets / "manifest.json").read_text())
    known_hashes = {r["path"]: r["sha256"] for r in manifest["files"]}
    tasks = []
    capture_data = json.loads((REPO / "named-captures/data.json").read_text())
    video_data = json.loads((REPO / "videos-plot/data.json").read_text())
    for capture in capture_data["examples"]:
        tasks.append(
            dict(
                group="captures",
                id=capture["id"],
                qutcc=str(args.assets / "captures" / capture["id"] / "qutcc.bin.gz"),
                im2im=str(args.assets / "captures" / capture["id"] / "im2im.bin.gz"),
            )
        )
    for video in video_data["videos"]:
        for frame in range(1, video["frames"] + 1):
            tasks.append(
                dict(
                    group=video["id"],
                    id=video["id"],
                    frame=frame,
                    **{
                        m: str(
                            args.assets
                            / "videos"
                            / video["id"]
                            / m
                            / f"frame_{frame:04d}.bin.gz"
                        )
                        for m in ["qutcc", "im2im"]
                    },
                )
            )
    # Reject a changed numerical export before associating it with existing videos.
    for task in tasks:
        for method in ["qutcc", "im2im"]:
            path = Path(task[method])
            assert (
                hashlib.sha256(path.read_bytes()).hexdigest()
                == known_hashes[str(path.relative_to(args.assets))]
            )
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(compare, tasks, chunksize=8))
    captures = {
        r["id"]: r for task, r in zip(tasks, rows) if task["group"] == "captures"
    }
    videos = {}
    for video in video_data["videos"]:
        frames = [r for task, r in zip(tasks, rows) if task["group"] == video["id"]]
        assert len(frames) == video["frames"]
        videos[video["id"]] = dict(
            rows=frames,
            low_agreement_frames=choose_frames(frames),
            mean_pearson=float(
                np.mean([r["pearson"] for r in frames if r["pearson"] is not None])
            ),
            mean_spearman=float(
                np.mean([r["spearman"] for r in frames if r["spearman"] is not None])
            ),
        )
    result = dict(
        protocol="intermodel_rgb_width_agreement_v1",
        pixel_asset_base=json.loads((REPO / "pixel_maps.json").read_text())["base"],
        pixel_manifest_sha256=hashlib.sha256(
            (args.assets / "manifest.json").read_bytes()
        ).hexdigest(),
        definition="Within-image Pearson/Spearman between the two unsmoothed RGB-mean calibrated width maps. Both models must have finite widths and no crossed RGB bounds at that pixel. Coefficients describe model agreement, not reconstruction accuracy or coverage.",
        rank_gap_definition="Absolute difference of average-tie percentile ranks over the jointly valid pixels, in [0,1].",
        region_definition="30x30 pixel grid patch with largest mean rank gap; at least half the patch must be valid. Coordinates follow the displayed images.",
        frame_selection="Five lowest-Spearman frames per video, separated by at least 20 display frames; not a quality ranking.",
        ground_truth_used=False,
        training_performed=False,
        inference_performed=False,
        captures=captures,
        videos=videos,
    )
    (REPO / "uncertainty_agreement.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    output = REPO / "videos-plot/agreement"
    output.mkdir(exist_ok=True)
    fields = [
        "id",
        "frame",
        "pearson",
        "spearman",
        "mean_absolute_width_gap",
        "mean_rank_gap",
        "valid_pixels",
    ]
    for name, entries in [("named_captures", list(captures.values()))] + [
        (v, r["rows"]) for v, r in videos.items()
    ]:
        with (output / (name + ".csv")).open("w", newline="") as stream:
            writer = csv.DictWriter(
                stream, fields, extrasaction="ignore", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(entries)
    for name, info in videos.items():
        print(
            name,
            "mean Pearson",
            round(info["mean_pearson"], 5),
            "mean Spearman",
            round(info["mean_spearman"], 5),
            "inspect frames",
            info["low_agreement_frames"],
            flush=True,
        )
    print(
        "Compared", len(rows), "image/frame pairs from existing maps only", flush=True
    )


if __name__ == "__main__":
    main()
