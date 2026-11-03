"""Render synchronized top-decile highlights from verified numerical width maps.

Only display exports are encoded. Original models, calibration, metrics, input
frames, and source videos are unchanged. Highlight only each reconstruction;
leave the original uncertainty panel readable. Map classes follow saved display
coordinates (already rotated 180 degrees).
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image

from pixel_maps import load_pixel_map

ROOT = Path(__file__).resolve().parents[1]
COLORS = np.array(
    [[16, 23, 34], [0, 190, 255], [255, 112, 0], [240, 240, 240]], dtype=np.uint8
)
METHODS = ("qutcc", "im2im")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def classes(q, i, crossed_q, crossed_i, row):
    valid = np.isfinite(q) & np.isfinite(i) & ~crossed_q & ~crossed_i
    result = np.zeros(q.shape, np.uint8)
    if row["top10_iou"] is not None:
        # Keep the interpolated float64 cutoffs; float32 scalar promotion can
        # round a cutoff onto a neighboring pixel value and change the set.
        result[valid & (q.astype(np.float64) >= row["top10_threshold_qutcc"])] |= 1
        result[valid & (i.astype(np.float64) >= row["top10_threshold_im2im"])] |= 2
    assert int(np.count_nonzero(result == 3)) == row["top10_intersection"]
    assert int(np.count_nonzero(result)) == row["top10_union"]
    result[~valid] = 255
    return result


def highlight(frame, codes, method):
    image = frame.copy()
    selected = (codes != 255) & ((codes & (1 if method == "qutcc" else 2)) != 0)
    region = image[24:294]
    colors = COLORS[np.minimum(codes, 3)]
    # Emphasize exclusive selections; keep shared selections more transparent.
    alpha = np.where(codes[selected] == 3, 0.35, 0.70)[:, None]
    region[selected] = np.floor(
        region[selected].astype(float) * (1 - alpha) + colors[selected] * alpha + 0.5
    ).astype(np.uint8)
    return image


def writer(path, size, fps):
    stream = imageio_ffmpeg.write_frames(
        str(path),
        size,
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
    readers = {}
    writers = {}
    for method in METHODS:
        path = ROOT / "videos-plot" / video["models"][method]["video"].split("?")[0]
        reader = imageio_ffmpeg.read_frames(
            str(path),
            pix_fmt="rgb24",
            input_params=["-threads", "1"],
            output_params=["-threads", "1"],
        )
        meta = next(reader)
        if tuple(meta["size"]) != (480, 588) or abs(meta["fps"] - video["fps"]) > 0.01:
            raise ValueError("Source video shape/rate changed")
        readers[method] = reader
        writers[method] = writer(
            destination / (method + ".partial.mp4"), (480, 588), video["fps"]
        )
    writers["map"] = writer(destination / "map.partial.mp4", (480, 270), video["fps"])
    try:
        for index, row in enumerate(report["rows"], 1):
            maps = {}
            for method in METHODS:
                relative = f"videos/{name}/{method}/frame_{index:04d}.bin.gz"
                path = assets / relative
                if sha(path) != known[relative]:
                    raise ValueError("Numerical map hash changed")
                maps[method] = load_pixel_map(path)
            codes = classes(
                maps["qutcc"][0],
                maps["im2im"][0],
                maps["qutcc"][1],
                maps["im2im"][1],
                row,
            )
            rgb = COLORS[np.minimum(codes, 3)].copy()
            rgb[codes == 255] = (227, 32, 201)
            writers["map"].send(np.ascontiguousarray(rgb))
            if index == 1:
                Image.fromarray(rgb).save(destination / "map.png")
            for method in METHODS:
                frame = np.frombuffer(next(readers[method]), np.uint8).reshape(
                    588, 480, 3
                )
                image = highlight(frame, codes, method)
                writers[method].send(np.ascontiguousarray(image))
                if index == 1:
                    Image.fromarray(image).save(destination / (method + ".png"))
        for reader in readers.values():
            if next(reader, None) is not None:
                raise ValueError("Source video has unexpected extra frames")
    finally:
        for stream in writers.values():
            stream.close()
        for reader in readers.values():
            reader.close()
    result = dict(frames=len(report["rows"]), fps=video["fps"], models={})
    for method in (*METHODS, "map"):
        temporary = destination / (method + ".partial.mp4")
        count, duration = imageio_ffmpeg.count_frames_and_secs(str(temporary))
        if count != video["frames"] or abs(duration - count / video["fps"]) > 0.02:
            raise ValueError("Encoded frame count/duration mismatch")
        path = destination / (method + ".mp4")
        temporary.replace(path)
        digest = sha(path)
        poster = destination / (method + ".png")
        item = dict(
            video=f"overlap-assets/{name}/{method}.mp4?v={digest[:12]}",
            poster=f"overlap-assets/{name}/{method}.png?v={sha(poster)[:12]}",
            sha256=digest,
        )
        if method == "map":
            result["map"] = item
        else:
            result["models"][method] = item
    print(name, video["frames"], "frames complete", flush=True)
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
        schema="overlap_playback_v1",
        agreement_sha256=sha(ROOT / "uncertainty_agreement.json"),
        pixel_manifest_sha256=sha(args.assets / "manifest.json"),
        definition="Precomputed top-10% selections from full-precision numerical width maps. White: both models; bright blue: QUTCC only; vivid orange: Im2im only. Only the reconstruction panel receives the highlight; statistical metrics are unchanged.",
        videos=results,
    )
    (ROOT / "videos-plot/overlap-playback.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    print("READY: synchronized display exports for all 1,580 source frames", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("assets", type=Path)
    p.add_argument("--output", type=Path, default=ROOT / "videos-plot/overlap-assets")
    main(p.parse_args())
