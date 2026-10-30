"""Collect completed inference-only reports for the raw demo's full-test table."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect(results):
    modes = {
        mode: {study: {} for study in ("clean", "corrupted")}
        for mode in ("tight90", "reference")
    }
    for path in sorted(results.glob("*.json")):
        if path.name.endswith(".progress.json"):
            continue
        report = json.loads(path.read_text())
        if report.get("passed") is not True:
            raise ValueError("Evaluation did not pass: " + str(path))
        for mode, record in report["reports"].items():
            rows = record["per_image"]
            if (
                record["count"] != 2000
                or len(rows) != 2000
                or record["training_performed"]
                or record["calibration_refitted"]
                or not record["first_50_reproduced"]
            ):
                raise ValueError("Wrong evaluation scope or provenance")
            ids = [str(row["id"]) for row in rows]
            if len(set(ids)) != 2000:
                raise ValueError("Duplicate test identities")
            compact = {
                key: value for key, value in record.items() if key != "per_image"
            }
            compact["test_ids_sha256"] = hashlib.sha256(
                "\n".join(ids).encode()
            ).hexdigest()
            compact["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            existing = modes[mode][record["study"]]
            if record["method"] in existing:
                raise ValueError("Duplicate model evaluation")
            existing[record["method"]] = compact
    for studies in modes.values():
        for methods in studies.values():
            if len({r["test_ids_sha256"] for r in methods.values()}) > 1:
                raise ValueError("Methods evaluated on different test IDs/order")
    result = dict(
        count=2000,
        definition="Mean image-wise LPIPS-AlexNet, Pearson and Spearman over the full 2000-image test split; correlations use unsmoothed RGB-average maps; outputs clipped [0,1]",
        training_performed=False,
        calibration_refitted=False,
        modes=modes,
    )
    output = ROOT / "raw-diffusercam/full_analysis_metrics.json"
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    tmp.replace(output)
    print(
        {
            mode: {study: list(models) for study, models in studies.items()}
            for mode, studies in modes.items()
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    collect(parser.parse_args().results)
