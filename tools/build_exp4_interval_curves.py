"""Verify completed checkpoint evaluations and publish measured interval curves."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from build_exp4_learning import NAMES

ROOT = Path(__file__).resolve().parents[1]
EPOCHS = list(range(10, 101, 10))
MANIFEST_SHA = "155670232c27b3201582f5a1b67fb4196e8123e40f388d9c951df4418f7144fb"
REFERENCE_SHA = "53b0e596b0e5f036684185e5fb2854cd436890e45e68eb3da226d46b8253b197"
CONDITIONS = [key for key in NAMES if key != "exposure"] + [
    "exposure_050",
    "exposure_150",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def average(values):
    return sum(values) / len(values)


def summarize(result):
    calibration = result["calibration"]["conditions"]
    test = result["test"]
    if set(calibration) != set(CONDITIONS) or set(test) != set(CONDITIONS):
        raise ValueError("Condition panel changed")
    groups = {}
    for key in NAMES:
        members = ["exposure_050", "exposure_150"] if key == "exposure" else [key]
        for member in members:
            if (
                calibration[member]["count"] != (150 if key == "exposure" else 300)
                or test[member]["count"] != 2000
            ):
                raise ValueError("Calibration/test group size changed")
            for split in (calibration, test):
                for metric in ("width", "coverage", "crossing"):
                    value = split[member][metric]
                    if not math.isfinite(value) or not (
                        -1 <= value <= 1 if metric == "width" else 0 <= value <= 1
                    ):
                        raise ValueError("Invalid interval metric")
        groups[key] = dict(
            calibration_width=average([calibration[m]["width"] for m in members]),
            calibration_coverage=average([calibration[m]["coverage"] for m in members]),
            test_coverage=average([test[m]["coverage"] for m in members]),
            test_width=average([test[m]["width"] for m in members]),
        )
    mean = {
        metric: average([row[metric] for row in groups.values()])
        for metric in next(iter(groups.values()))
    }
    overall = result["calibration"]["overall"]
    if overall["count"] != 3000:
        raise ValueError("Calibration cohort changed")
    for metric in ("width", "coverage"):
        if abs(mean["calibration_" + metric] - overall[metric]) > 2e-6:
            raise ValueError("Weighted category mean differs from calibration mixture")
    if abs(overall["coverage"] - result["fit"]["calibration_coverage"]) > 5e-6:
        raise ValueError("Calibration audit differs from fit")
    return dict(
        epoch=result["request"]["epoch"],
        mean=mean,
        conditions=groups,
        calibration_status=result["fit"]["status"],
        calibration_target_met=result["fit"]["target_met"],
        calibration_fit_valid=(
            result["fit"]["status"] == "fitted"
            and result["fit"].get("within_tolerance", False)
            and result["fit"]["target_met"]
        ),
        calibration_failure=result["fit"].get("failure"),
        checkpoint_sha256=result["request"]["checkpoint_sha256"],
    )


def build(source):
    methods = {}
    reference_sha = None
    manifest_sha = None
    source_sha = None
    final_reference = json.loads((ROOT / "experiment4/data.json").read_text())
    for method in ("qutcc", "im2im"):
        rows = []
        for epoch in EPOCHS:
            folder = source / method / f"epoch_{epoch}"
            ready_path = folder / "READY.json"
            if not ready_path.exists():
                continue
            ready = json.loads(ready_path.read_text())
            result_path = folder / "result.json"
            if not ready["passed"] or ready["result_sha256"] != sha(result_path):
                raise ValueError("Evaluation receipt/hash mismatch")
            result = json.loads(result_path.read_text())
            request = result["request"]
            if (
                request["method"] != method
                or request["epoch"] != epoch
                or not result["passed"]
            ):
                raise ValueError("Checkpoint identity mismatch")
            if (
                request["target_calibration_coverage"] != 0.9
                or request["test_used_for_calibration"]
            ):
                raise ValueError("Calibration protocol changed")
            if (request["reference_sha256"], request["manifest_sha256"]) != (
                REFERENCE_SHA,
                MANIFEST_SHA,
            ):
                raise ValueError("Not the original Exp 4 reference and split")
            if source_sha is None:
                source_sha = (
                    request["evaluator_sha256"],
                    request["frozen_evaluator_sha256"],
                )
            if source_sha != (
                request["evaluator_sha256"],
                request["frozen_evaluator_sha256"],
            ):
                raise ValueError("Evaluator changed across checkpoints")
            if (
                epoch == 100
                and request["checkpoint_sha256"]
                != final_reference["arms"][f"{method}_general100"]["checkpoint_sha256"]
            ):
                raise ValueError("Final checkpoint differs from the demo")
            if reference_sha is None:
                reference_sha, manifest_sha = (
                    request["reference_sha256"],
                    request["manifest_sha256"],
                )
            if (reference_sha, manifest_sha) != (
                request["reference_sha256"],
                request["manifest_sha256"],
            ):
                raise ValueError(
                    "Evaluation reference/split differs across checkpoints"
                )
            rows.append(summarize(result))
        methods[method] = dict(
            label="QUTCC" if method == "qutcc" else "Im2im", history=rows
        )
    complete = sum(len(m["history"]) for m in methods.values())
    return dict(
        schema="exp4_interval_curves_v1",
        methods=methods,
        expected_epochs=EPOCHS,
        completed=complete,
        expected=20,
        complete=complete == 20,
        calibration_count=3000,
        test_count_per_condition=2000,
        reference_sha256=reference_sha,
        manifest_sha256=manifest_sha,
        definition="Each saved checkpoint is calibrated once on the same 3,000-scene mixture. Calibration width uses that split; test coverage uses all 2,000 independent test scenes per displayed condition. Average weights each of ten training families equally; exposure averages gains 0.50 and 1.50. Calibration is never fitted per condition or on test images.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "experiment4/interval-curves.json"
    )
    args = parser.parse_args()
    data = build(args.source)
    args.output.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    print(f"Verified {data['completed']}/{data['expected']} checkpoint evaluations")
