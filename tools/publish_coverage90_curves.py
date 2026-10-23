"""Publish independently recalibrated five-epoch curves without image caches.

Checkpoint identity is verified by the evaluator. This collector additionally
checks split identity against the published latest checkpoint for each method.
Missing/failed milestones remain explicit; no interpolation or test-set fitting.
"""

import argparse
from contextlib import nullcontext
import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(
    os.environ.get("CONVRML_DEMO_ROOT", str(Path(__file__).resolve().parents[1]))
)
WORK = Path.home() / ".local/share/convrml-coverage90-20261022"
REMOTE = "/home/jy2228/ConvRML/experiments/coverage90_20261022/results"
METHODS = {
    "rml": ["im2im", "ensemble5", "mc_005", "qutcc"],
    "diffuser": ["im2im", "ensemble5", "mc_005", "qutcc"],
    "raw_clean": ["im2im", "qutcc"],
    "raw_corrupted": ["im2im", "qutcc"],
}


def expected():
    return {
        group: {
            method: list(range(5, (30 if group == "raw_corrupted" else 50) + 1, 5))
            for method in methods
        }
        for group, methods in METHODS.items()
    }


def empty():
    return dict(
        protocol="tight_empirical_coverage90",
        target_calibration_coverage=[0.9, 0.901],
        groups={
            group: {
                method: [dict(epoch=epoch, status="pending") for epoch in epochs]
                for method, epochs in methods.items()
            }
            for group, methods in expected().items()
        },
    )


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(payload):
    """Reject wrong protocols, missing milestones, and incomplete test results."""
    require(payload["protocol"] == "tight_empirical_coverage90", "Wrong curve protocol")
    require(
        payload["target_calibration_coverage"] == [0.9, 0.901], "Wrong coverage target"
    )
    layout = expected()
    require(set(payload["groups"]) == set(layout), "Wrong experiment groups")
    total = sum(
        len(epochs) for methods in layout.values() for epochs in methods.values()
    )
    counts = dict(complete=0, failed=0, pending=0, expected=total)
    for group, methods in layout.items():
        require(
            set(payload["groups"][group]) == set(methods), "Missing or unexpected model"
        )
        raw = group.startswith("raw_")
        for method, epochs in methods.items():
            rows = payload["groups"][group][method]
            require(
                [row["epoch"] for row in rows] == epochs,
                "Missing, duplicated, or unordered epochs",
            )
            for row in rows:
                status = row["status"]
                require(
                    status in ("complete", "failed", "pending"),
                    "Unknown evaluation state",
                )
                counts[status] += 1
                if status != "complete":
                    require(
                        "metrics" not in row,
                        "Unfinished evaluations must not contain metrics",
                    )
                    continue
                require(
                    row["test_count"] == (2000 if raw else 5000),
                    "Wrong held-out test count",
                )
                calibration = row["calibration"]
                require(
                    calibration["calibrated_on"] == "calibration split only",
                    "Invalid calibration split",
                )
                require(
                    calibration["confidence_guarantee"] is False,
                    "Empirical calibration is not an RCPS certificate",
                )
                require(
                    calibration["n_images"] == (3000 if raw else 2048),
                    "Wrong calibration count",
                )
                require(
                    0 <= calibration["calibration_coverage"] <= 1,
                    "Invalid calibration coverage",
                )
                require(len(row["report_sha256"]) == 64, "Missing source report hash")
                for mode, metrics in row["metrics"].items():
                    require(
                        all(math.isfinite(value) for value in metrics.values()),
                        "Nonfinite metrics",
                    )
                    require(0 <= metrics["coverage"] <= 1, "Invalid test coverage")
                    if mode == "clipped":
                        require(
                            -1 <= metrics["width"] <= 1,
                            "Clipped width outside the intensity range",
                        )
    require(
        sum(counts[key] for key in ("complete", "failed", "pending")) == total,
        "Incomplete curve ledger",
    )
    payload["counts"] = counts
    return payload


def collect():
    """Use the cluster helper so collection shares the same report checks as scheduling."""
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-i",
        str(Path.home() / ".ssh/id_ed25519"),
        "-o",
        "ConnectTimeout=20",
        "jy2228@unicorn-login-02.coecis.cornell.edu",
        shlex.join(
            [
                "/home/jy2228/.conda/envs/convrml/bin/python",
                str(Path(REMOTE).parent / "coverage90_cluster.py"),
                "curves",
            ]
        ),
    ]
    response = subprocess.check_output(command, input="{}", text=True, timeout=120)
    return validate(json.loads(response))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--already-locked", action="store_true")
    args = parser.parse_args()
    lock = None
    if not args.already_locked:
        lock = (
            Path.home() / ".local/share/convrml-raw-demo-20261019/publisher.lock"
        ).open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
    with lock if lock else nullcontext():

        def git(*args):
            return subprocess.check_output(
                ["git", *args], cwd=ROOT, text=True, timeout=180
            ).strip()

        if git("diff", "--cached", "--name-only"):
            raise RuntimeError("Unrelated staged changes; retry later")
        payload = collect()
        path = ROOT / "coverage90_curves.json"
        previous = json.loads(path.read_text()) if path.exists() else None
        if previous:
            previous.pop("updated_at", None)
        if payload != previous:
            payload["updated_at"] = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
            path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
        if not args.prepare:
            if git("status", "--porcelain", "--", path.name):
                git("add", "--", path.name)
                git("diff", "--cached", "--check")
                git("commit", "-m", "Update independently calibrated five-epoch curves")
            git("push", "origin", "main")
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / "curve_publication.json").write_text(
            json.dumps(payload["counts"], indent=2) + "\n"
        )
        print(json.dumps(payload["counts"]), flush=True)


if __name__ == "__main__":
    main()
