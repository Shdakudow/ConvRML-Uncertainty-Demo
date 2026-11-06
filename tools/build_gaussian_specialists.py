"""Import completed Gaussian-specialist reports and matching display images."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]


def build(source, reference_assets):
    reference = json.loads((ROOT / "experiment4/data.json").read_text())
    ids = reference["ids"]
    result = dict(schema="gaussian_specialists_v1", ids=ids, arms={}, files={})
    for method in ("qutcc", "im2im"):
        folder = source / method
        report_path = folder / "report.json"
        digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
        ready = json.loads((folder / "READY.json").read_text())
        assert ready["completed"] and ready["report_sha256"] == digest
        report = json.loads(report_path.read_text())
        assert report["request"]["epoch"] == 50 and report["request"]["sigma"] == 0.01
        assert report["test_count"] == reference["results"]["gaussian"]["count"] == 2000
        assert (
            report["modified_input_float32_sha256"]
            == reference["results"]["gaussian"]["modified_input_float32_sha256"]
        )
        assert [row["id"] for row in report["per_image"][: len(ids)]] == ids
        arm = method + "_gaussian50"
        result["arms"][arm] = dict(
            mean=report["metrics"]["clipped"],
            examples=[r["clipped"] for r in report["per_image"][: len(ids)]],
            calibration=report["calibration"],
            request=report["request"],
            report_sha256=digest,
        )
        for index in range(len(ids)):
            src = folder / "examples" / f"{index:03d}"
            for name, relative in [
                ("input", f"images/gaussian/{index:03d}-input.png"),
                ("target", f"images/shared/{index:03d}-target.png"),
            ]:
                with Image.open(src / (name + ".png")) as a, Image.open(
                    reference_assets / relative
                ) as b:
                    assert (
                        a.size == b.size
                        and ImageChops.difference(
                            a.convert("RGB"), b.convert("RGB")
                        ).getbbox()
                        is None
                    ), (method, index, name)
            for kind, name in [
                ("prediction", "reconstruction"),
                ("width", "uncertainty"),
                ("error", "absolute_error"),
            ]:
                relative = f"gaussian-specialists/{arm}/{index:03d}-{kind}.png"
                destination = ROOT / "experiment4" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(src / (name + ".png")) as im:
                    assert im.size == (480, 270)
                shutil.copyfile(src / (name + ".png"), destination)
                result["files"][relative] = hashlib.sha256(
                    destination.read_bytes()
                ).hexdigest()
    (ROOT / "experiment4/gaussian-specialists.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        "Verified both reports, all scene IDs, identical Gaussian inputs/targets, and 300 display images."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("reference_assets", type=Path)
    args = parser.parse_args()
    build(args.source, args.reference_assets)
