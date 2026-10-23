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


def validate(payload):
    assert payload["protocol"] == "tight_empirical_coverage90"
    assert payload["target_calibration_coverage"] == [0.9, 0.901]
    assert set(payload["groups"]) == set(METHODS)
    counts = dict(complete=0, failed=0, pending=0, expected=112)
    for group, methods in expected().items():
        assert set(payload["groups"][group]) == set(methods)
        for method, epochs in methods.items():
            rows = payload["groups"][group][method]
            assert [row["epoch"] for row in rows] == epochs
            for row in rows:
                assert row["status"] in ("complete", "failed", "pending")
                counts[row["status"]] += 1
                if row["status"] == "complete":
                    assert row["test_count"] == (
                        2000 if group.startswith("raw_") else 5000
                    )
                    cal = row["calibration"]
                    assert cal["calibrated_on"] == "calibration split only"
                    assert cal["confidence_guarantee"] is False
                    assert cal["n_images"] == (
                        3000 if group.startswith("raw_") else 2048
                    )
                    assert 0 <= cal["calibration_coverage"] <= 1
                    assert len(row["report_sha256"]) == 64
                    for mode, metrics in row["metrics"].items():
                        assert all(math.isfinite(value) for value in metrics.values())
                        assert 0 <= metrics["coverage"] <= 1
                        if mode == "clipped":
                            assert -1 <= metrics["width"] <= 1
                else:
                    assert "metrics" not in row
    assert (
        sum(counts[k] for k in ("complete", "failed", "pending")) == counts["expected"]
    )
    payload["counts"] = counts
    return payload


def collect():
    probe = f"""from pathlib import Path
import hashlib,json
root=Path({REMOTE!r});out=json.loads({json.dumps(empty())!r})
for group,methods in out["groups"].items():
 for method,rows in methods.items():
  latest=root/group/method/("epoch_030" if group=="raw_corrupted" else "epoch_050")/"report.json"
  identity=json.loads(latest.read_text())["split_identity"]
  for row in rows:
   folder=root/group/method/("epoch_"+str(row["epoch"]).zfill(3));path=folder/"report.json"
   if path.is_file():
    raw=path.read_bytes();report=json.loads(raw)
    assert report["split_identity"]==identity,(group,method,row["epoch"],"split identity mismatch")
    req=report["request"]
    assert req["epoch"]==row["epoch"] and req["method"]==method and req["calibration"]=="tight_empirical"
    assert req["test_used_for_calibration"] is False and req["endpoint_clipping"]==[0,1]
    assert len(report["per_image"])==report["test_count"]
    row.update(status="complete",metrics=report["metrics"],calibration=report["calibration"],test_count=report["test_count"],report_sha256=hashlib.sha256(raw).hexdigest())
   else:
    failure=folder/"failure.json"
    if failure.exists():
     error=json.loads(failure.read_text())
     if error.get("status")=="calibration_infeasible":row.update(status="failed",error=error["error"])
print(json.dumps(out,allow_nan=False))
"""
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-i",
        str(Path.home() / ".ssh/id_ed25519"),
        "-o",
        "ConnectTimeout=20",
        "jy2228@unicorn-login-02.coecis.cornell.edu",
        "python3 -c " + shlex.quote(probe),
    ]
    return validate(
        json.loads(subprocess.check_output(command, text=True, timeout=120))
    )


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
