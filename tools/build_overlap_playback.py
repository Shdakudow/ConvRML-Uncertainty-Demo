"""Render comparison-only videos from saved width maps; reconstructions stay original.

Overlap is categorical. Spearman mode displays absolute percentile-rank gaps;
its coefficient remains the recorded per-frame statistic. No model inference.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image
from scipy.stats import rankdata

from pixel_maps import load_pixel_map

ROOT = Path(__file__).resolve().parents[1]
COLORS = np.array(
    [[16, 23, 34], [0, 190, 255], [255, 112, 0], [240, 240, 240]], dtype=np.uint8
)
GRADIENT = np.array(
    [[20, 35, 60], [34, 95, 157], [35, 185, 172], [243, 203, 85], [250, 112, 82]],
    dtype=float,
)
METHODS = ("qutcc", "im2im")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def comparison_maps(q, i, crossed_q, crossed_i, row):
    valid = np.isfinite(q) & np.isfinite(i) & ~crossed_q & ~crossed_i
    codes = np.zeros(q.shape, np.uint8)
    if row["top10_iou"] is not None:
        codes[valid & (q.astype(np.float64) >= row["top10_threshold_qutcc"])] |= 1
        codes[valid & (i.astype(np.float64) >= row["top10_threshold_im2im"])] |= 2
    assert int(np.count_nonzero(codes == 3)) == row["top10_intersection"]
    assert int(np.count_nonzero(codes)) == row["top10_union"]
    overlap = COLORS[codes].copy()
    overlap[~valid] = (227, 32, 201)
    first, second = rankdata(q[valid]), rankdata(i[valid])
    coefficient = (
        float(np.corrcoef(first, second)[0, 1])
        if len(first) > 1 and first.std() > 0 and second.std() > 0
        else None
    )
    recorded = row["spearman"]
    if recorded is None:
        assert coefficient is None
    else:
        assert coefficient is not None and abs(coefficient - recorded) < 1e-10, (
            coefficient,
            recorded,
        )
    rank_gap = np.full(q.shape, np.nan, np.float32)
    if row["top10_iou"] is not None:
        denominator = max(1, len(first) - 1)
        rank_gap[valid] = np.abs(
            ((first - 1) / denominator).astype(np.float32)
            - ((second - 1) / denominator).astype(np.float32)
        )
    width_gap = np.abs(q - i)
    return {
        "map": overlap,
        "rank": colorize(rank_gap, valid),
        "width_gap": colorize(width_gap, valid),
    }


def colorize(values, valid):
    positions = np.clip(np.nan_to_num(values, nan=0), 0, 1) * 4
    indices = np.minimum(3, np.floor(positions).astype(int))
    fraction = (positions - indices)[..., None]
    rgb = np.floor(
        GRADIENT[indices] * (1 - fraction) + GRADIENT[indices + 1] * fraction + 0.5
    ).astype(np.uint8)
    rgb[~valid | ~np.isfinite(values)] = (227, 32, 201)
    return rgb


def writer(path, fps):
    stream = imageio_ffmpeg.write_frames(
        str(path),
        (480, 270),
        fps=fps,
        codec="libx264",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        macro_block_size=1,
        ffmpeg_log_level="error",
        output_params=["-threads", "1", "-crf", "18", "-movflags", "+faststart"],
    )
    stream.send(None)
    return stream


def render(task):
    name, report, video, assets, out, known = task
    destination = out / name
    destination.mkdir(parents=True, exist_ok=True)
    writers = {
        kind: writer(destination / (kind + ".partial.mp4"), video["fps"])
        for kind in ("map", "rank", "width_gap")
    }
    try:
        for index, row in enumerate(report["rows"], 1):
            maps = {}
            for method in METHODS:
                relative = f"videos/{name}/{method}/frame_{index:04d}.bin.gz"
                path = assets / relative
                if sha(path) != known[relative]:
                    raise ValueError("Numerical width map changed")
                maps[method] = load_pixel_map(path)
            images = comparison_maps(
                maps["qutcc"][0],
                maps["im2im"][0],
                maps["qutcc"][1],
                maps["im2im"][1],
                row,
            )
            for kind, image in images.items():
                writers[kind].send(np.ascontiguousarray(image))
                if index == 1:
                    Image.fromarray(image).save(destination / (kind + ".png"))
    finally:
        for stream in writers.values():
            stream.close()
    result = dict(frames=len(report["rows"]), fps=video["fps"])
    for kind in writers:
        temporary = destination / (kind + ".partial.mp4")
        count, duration = imageio_ffmpeg.count_frames_and_secs(str(temporary))
        if count != video["frames"] or abs(duration - count / video["fps"]) > 0.02:
            raise ValueError("Comparison video frame count changed")
        path = destination / (kind + ".mp4")
        temporary.replace(path)
        digest = sha(path)
        poster = destination / (kind + ".png")
        result[kind] = dict(
            video=f"overlap-assets/{name}/{kind}.mp4?v={digest[:12]}",
            poster=f"overlap-assets/{name}/{kind}.png?v={sha(poster)[:12]}",
            sha256=digest,
        )
    print(
        name,
        "ready; all",
        len(report["rows"]),
        "Spearman coefficients verified",
        flush=True,
    )
    return name, result


def main(args):
    agreement = json.loads((ROOT / "uncertainty_agreement.json").read_text())
    videos = json.loads((ROOT / "videos-plot/data.json").read_text())
    manifest = json.loads((args.assets / "manifest.json").read_text())
    known = {row["path"]: row["sha256"] for row in manifest["files"]}
    tasks = [
        (v["id"], agreement["videos"][v["id"]], v, args.assets, args.output, known)
        for v in videos["videos"]
    ]
    with ProcessPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(render, tasks))
    payload = dict(
        schema="comparison_playback_v2",
        agreement_sha256=sha(ROOT / "uncertainty_agreement.json"),
        pixel_manifest_sha256=sha(args.assets / "manifest.json"),
        definition="Comparison maps only. Original reconstruction videos remain untinted. White: shared top-10% selections; blue: QUTCC only; orange: Im2im only. Rank mode displays absolute percentile-rank differences; Spearman is one coefficient per frame. Width-gap mode displays absolute interval-width differences. All values come from the same saved numerical maps.",
        videos=results,
    )
    (ROOT / "videos-plot/overlap-playback.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "videos-plot/overlap-assets"
    )
    main(parser.parse_args())
