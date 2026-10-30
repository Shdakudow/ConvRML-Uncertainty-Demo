"""Build browsing categories from saved reconstruction metrics."""

import argparse
import gzip
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]



def header(path):
    with gzip.open(path, "rb") as file:
        length = struct.unpack("<I", file.read(4))[0]
        return json.loads(file.read(length))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True,
                        help="JSON containing exp2 per-image metrics")
    args = parser.parse_args()
    source = json.loads(args.source.read_text())
    result = {"difficulty_protocol": "Relative thirds of the displayed images, ranked by reference reconstruction SSIM (lower is harder). These are browsing groups, not full-test subsets or intrinsic scene labels.",
              "legacy": {}, "exp2": {}, "raw": {}}
    for camera in ["rml", "diffuser"]:
        entries = []
        for i in range(50):
            item = header(ROOT / "data" / camera / f"example_{i:02d}.bin.gz")["example"]
            entries.append(dict(index=i, id=item["id"], reference_ssim=item["models"]["fixed"]["metrics"]["ssim"]))
        result["legacy"][camera] = dict(reference="Fixed head", entries=entries)
        result["exp2"][camera] = dict(reference="Im2im", entries=[dict(index=i,id=r["id"],reference_ssim=r["ssim"]) for i,r in enumerate(source["exp2"][camera])])
    work = Path.home() / ".local/share/convrml-raw-demo-20261019/assets/exports"
    for study in ["clean"]:
        entries = []
        for i in range(50):
            item = header(work / study / "im2im" / f"example_{i:02d}.bin.gz")
            entry = dict(index=i,id=item["id"],reference_ssim=item["metrics"]["ssim"])
            entries.append(entry)
        result["raw"][study] = dict(reference="Im2im", entries=entries)
    (ROOT / "example-categories.json").write_text(json.dumps(result,indent=2)+"\n")
    print("Saved 250 reference scores.")


if __name__ == "__main__":
    main()
