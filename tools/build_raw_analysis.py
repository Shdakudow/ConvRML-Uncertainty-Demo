"""Evaluate LPIPS and error/width correlations on the demo's exact saved arrays.

Only the 50 displayed images are available here, not the full 2,000-image test
outputs. Both calibration modes are evaluated independently. Immutable asset
commits and compressed-file hashes identify every evaluated prediction.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from urllib.parse import urlparse

import numpy as np
from scipy import stats
import torch
from torchmetrics.image.lpip import LearnedPerceptualImagePatchSimilarity

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = Path.home() / ".local/share"


def unpack(payload):
    content = gzip.decompress(payload)
    size = struct.unpack("<I", content[:4])[0]
    header = json.loads(content[4 : 4 + size])
    arrays = {}
    for descriptor in header["arrays"]:
        start = 4 + size + descriptor["offset"]
        raw = content[start : start + descriptor["length"]]
        # Existing packers hash the stored byte order, before float unshuffling.
        if hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
            raise ValueError("Array checksum mismatch")
        values = np.frombuffer(raw, dtype=np.uint8)
        if descriptor["encoding"] == "float32-shuffled":
            values = values.reshape(4, -1).T.copy().reshape(-1).view("<f4")
        elif descriptor["encoding"] != "uint8":
            raise ValueError("Unsupported array encoding")
        arrays[descriptor["name"]] = values.reshape(descriptor["shape"]).copy()
    return header, arrays


def asset_from_commit(repository, base, index):
    parts = urlparse(base).path.strip("/").split("/")
    commit, prefix = parts[2], "/".join(parts[3:])
    path = f"{prefix}/example_{index:02d}.bin.gz"
    return subprocess.check_output(
        ["git", "-C", str(repository), "show", f"{commit}:{path}"]
    )


def finite(value):
    return float(value) if np.isfinite(value) else None


def summarize(rows):
    summary = {}
    for key in ("lpips", "pearson", "spearman"):
        values = [r[key] for r in rows if r[key] is not None]
        summary[key] = dict(
            mean=float(np.mean(values)) if values else None,
            std=float(np.std(values)) if values else None,
            n_valid=len(values),
        )
    return summary


@torch.inference_mode()
def build(cache):
    torch.set_num_threads(4)
    metric = (
        LearnedPerceptualImagePatchSimilarity(
            net_type="alex", normalize=True, reduction="none"
        )
        .eval()
        .requires_grad_(False)
    )
    reference = json.loads((ROOT / "raw-diffusercam/data.json").read_text())
    overlays = json.loads((ROOT / "coverage90.json").read_text())
    original_base = json.loads((ROOT / "raw-diffusercam/assets.json").read_text())[
        "base"
    ]
    result = dict(
        scope="The 50 displayed examples per study/method, not all 2000 test images",
        lpips="LPIPS-AlexNet v0.1; TorchMetrics normalize=True; clipped RGB [0,1]",
        correlations="Per-image Pearson and Spearman between unsmoothed RGB-average absolute-error and interval-width maps; average rank for ties; constant maps are null",
        modes={},
    )
    for mode in ("tight90", "reference"):
        result["modes"][mode] = {}
        for study in ("clean", "corrupted"):
            result["modes"][mode][study] = {}
            for method in ("qutcc", "im2im"):
                if mode == "tight90":
                    entry = overlays["groups"]["raw_" + study][method]
                    base, epoch = entry["base"], entry["epoch"]
                    repo = cache / "convrml-coverage90-20261022/assets"
                else:
                    entry = reference["studies"][study][method]
                    base = (
                        original_base
                        + "/"
                        + entry.get("asset_study", study)
                        + "/"
                        + method
                    )
                    epoch = entry["epoch"]
                    repo = cache / "convrml-raw-demo-20261019/assets"
                rows = []
                for index in range(entry["example_count"]):
                    payload = asset_from_commit(repo, base, index)
                    header, arrays = unpack(payload)
                    expected = entry.get("ids")
                    if expected and str(header["id"]) != str(expected[index]):
                        raise ValueError("Example identity mismatch")
                    # Match browser Number arithmetic; float32 Pearson can lose
                    # precision on large, nearly dark maps.
                    prediction = arrays["prediction"].astype(np.float64).clip(0, 1)
                    target = arrays["target"].astype(np.float64) / 255
                    width = (
                        arrays["upper"].astype(np.float64).clip(0, 1)
                        - arrays["lower"].astype(np.float64).clip(0, 1)
                    ).mean(axis=0)
                    error = np.abs(prediction - target).mean(axis=0)
                    if not all(
                        np.isfinite(a).all() for a in (prediction, target, width, error)
                    ):
                        raise ValueError("Nonfinite inference arrays")
                    lpips = metric(
                        torch.from_numpy(prediction).float()[None],
                        torch.from_numpy(target).float()[None],
                    ).item()
                    metric.reset()
                    if np.ptp(width) == 0 or np.ptp(error) == 0:
                        pearson = spearman = None
                    else:
                        pearson = finite(
                            stats.pearsonr(width.ravel(), error.ravel()).statistic
                        )
                        spearman = finite(
                            stats.spearmanr(width.ravel(), error.ravel()).statistic
                        )
                    rows.append(
                        dict(
                            index=index,
                            id=header["id"],
                            lpips=lpips,
                            pearson=pearson,
                            spearman=spearman,
                            asset_sha256=hashlib.sha256(payload).hexdigest(),
                        )
                    )
                result["modes"][mode][study][method] = dict(
                    epoch=epoch,
                    base=base,
                    count=len(rows),
                    per_image=rows,
                    summary=summarize(rows),
                )
                print(mode, study, method, epoch, summarize(rows), flush=True)
    output = ROOT / "raw-diffusercam/analysis_metrics.json"
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    temporary.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    build(parser.parse_args().cache)
