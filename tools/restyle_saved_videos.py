"""Rotate the original 0–1 video exports and double playback speed without model replay."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import time

import imageio_ffmpeg
from PIL import Image


def export_pair(source, destination):
    report = json.loads((source / "report.json").read_text())
    assert report["heatmap_range"] == [0, 1] and report["fps"] == 10
    assert report.get("display_rotation_degrees", 0) == 0
    destination.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    # Keep both label strips upright; rotate only the two image panels.
    stacked_filter = (
        "[0:v]split=4[t][r][l][u];"
        "[t]crop=480:24:0:0[top];"
        "[r]crop=480:270:0:24,hflip,vflip[rec];"
        "[l]crop=480:24:0:294[label];"
        "[u]crop=480:270:0:318,hflip,vflip[unc];"
        "[top][rec][label][unc]vstack=inputs=4,setpts=PTS/2[out]"
    )
    for kind in ["reconstruction", "uncertainty", "reconstruction_uncertainty"]:
        path = destination / f"{kind}.mp4"
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-y",
            "-filter_threads",
            "1",
            "-filter_complex_threads",
            "1",
            "-i",
            str(source / f"{kind}.mp4"),
        ]
        if kind == "reconstruction_uncertainty":
            command += ["-filter_complex", stacked_filter, "-map", "[out]"]
        else:
            command += ["-vf", "hflip,vflip,setpts=PTS/2"]
        command += [
            "-an",
            "-r",
            "20",
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
        ]
        subprocess.run(command, check=True)
        count, duration = imageio_ffmpeg.count_frames_and_secs(str(path))
        assert count == report["frames"] and abs(duration - count / 20) < 0.02
    for name in ["poster.png", "uncertainty_poster.png", "measurement_poster.png"]:
        with Image.open(source / name) as image:
            image.transpose(Image.Transpose.ROTATE_180).save(destination / name)
    report.update(
        fps=20,
        display_rotation_degrees=180,
        original_metric_values_retained=True,
        presentation_source=str(source),
        presentation_transform="Original 0–1 exports; rotate each image panel 180 degrees; present all frames at 20 fps; labels remain upright",
        export_seconds=time.monotonic() - started,
    )
    report["per_frame"] = [
        dict(row, seconds=(row["frame"] - 1) / 20) for row in report["per_frame"]
    ]
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    # The collector reads the report for combined CSVs; retain a per-model CSV too.
    import csv

    with (destination / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(report["per_frame"][0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(report["per_frame"])
    print(
        report["video"],
        report["method"],
        "restored 0–1 colors; rotation and 20 fps verified",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    pairs = [
        (args.source / video / method, args.destination / video / method)
        for video in ["video1", "video4", "video6", "video7", "video10"]
        for method in ["qutcc", "im2im"]
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda pair: export_pair(*pair), pairs))


if __name__ == "__main__":
    main()
