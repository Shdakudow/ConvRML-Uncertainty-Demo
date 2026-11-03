"""Verify all replayed error maps and link immutable assets into Exp 4."""

import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024**2), b""):
            h.update(block)
    return h.hexdigest()


def verify(source, reference):
    ready = json.loads((source / "READY.json").read_text())
    path = source / "error-maps.json"
    data = json.loads(path.read_text())
    if (
        ready.get("passed") is not True
        or ready["maps"] != 2200
        or ready["metadata_sha256"] != sha(path)
    ):
        raise ValueError("Incomplete or changed error export")
    if data["request"]["reference_sha256"] != sha(reference):
        raise ValueError("Original evaluation reference differs")
    original = json.loads(reference.read_text())
    if (
        data["ids"] != original["ids"]
        or set(data["arms"]) != set(original["arms"])
        or data["conditions"] != [c["id"] for c in original["conditions"]]
    ):
        raise ValueError("Error-map cohort differs from the comparison")
    if data["request"]["checkpoints"] != {
        a: v["checkpoint_sha256"] for a, v in original["arms"].items()
    }:
        raise ValueError("Error maps use different models")
    expected = {
        f"errors/{c}/{a}/{index:03d}.png"
        for c in data["conditions"]
        for a in data["arms"]
        for index in range(50)
    }
    actual = {str(p.relative_to(source)) for p in (source / "errors").rglob("*.png")}
    if expected != set(data["files"]) or expected != actual:
        raise ValueError("Incomplete error-map inventory")
    for name, record in data["files"].items():
        p = source / name
        if p.stat().st_size != record["bytes"] or sha(p) != record["sha256"]:
            raise ValueError("Error image hash changed: " + name)
        with Image.open(p) as image:
            if image.size != (480, 270) or image.mode != "RGB":
                raise ValueError("Wrong error-image dimensions")
            image.verify()
    for report in data["reports"].values():
        if report["count"] != 50:
            raise ValueError("Wrong example count")
        for arm, values in report["maximum_replay_difference"].items():
            if any(
                values[k] > t for k, t in dict(psnr=0.001, ssim=5e-5, mae=2e-5).items()
            ):
                raise ValueError("Replay verification failed")
    return data


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--asset-base")
    a = p.parse_args()
    d = verify(a.source, a.reference)
    if a.asset_base:
        result = {
            k: d[k]
            for k in [
                "schema",
                "definition",
                "scale",
                "palette",
                "ids",
                "conditions",
                "arms",
                "reports",
                "request",
            ]
        }
        result.update(
            base=a.asset_base,
            map_count=2200,
            manifest_url=a.asset_base.rstrip("/") + "/error-maps.json",
        )
        (ROOT / "experiment4/error-maps.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )
    print(
        "Verified 2,200 full-precision error-map exports, four checkpoint identities, and per-image replay metrics."
    )
