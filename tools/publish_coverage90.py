"""Publish completed near-90% evaluations, leaving reference data untouched.

Run manually with --prepare --already-locked while holding the shared publisher
lock, or normally from the five-minute LaunchAgent. Only coverage90.json is
committed automatically; the UI source is reviewed/deployed separately.
"""

import argparse
from contextlib import nullcontext
import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

from build_coverage90 import build

ROOT = Path(__file__).resolve().parents[1]
WORK = Path.home() / ".local/share/convrml-coverage90-20261022"
ASSETS = WORK / "assets"
BRANCH = "coverage90-assets-20261022"
REMOTE = "/home/jy2228/ConvRML/experiments/coverage90_20261022/results"
HOST = "jy2228@unicorn-login-02.coecis.cornell.edu"
SSH = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-i",
    str(Path.home() / ".ssh/id_ed25519"),
    "-o",
    "ConnectTimeout=15",
    HOST,
]


def run(command, *, cwd=ROOT, **kwargs):
    return subprocess.check_output(
        [str(part) for part in command], cwd=cwd, text=True, **kwargs
    ).strip()


def publish_metadata():
    # Also retry a previous push failure when no additional GPU jobs finished.
    if run(["git", "status", "--porcelain", "--", "coverage90.json"]):
        run(["git", "add", "--", "coverage90.json"])
        run(["git", "diff", "--cached", "--check"])
        run(
            ["git", "commit", "-m", "Publish ready near-90-percent calibration results"]
        )
    run(["git", "push", "origin", "main"], timeout=600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--already-locked", action="store_true")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    lock = None
    if not args.already_locked:
        lock = (
            Path.home() / ".local/share/convrml-raw-demo-20261019/publisher.lock"
        ).open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another publisher active; retry next interval", flush=True)
            return
    with lock if lock else nullcontext():
        if run(["git", "diff", "--cached", "--name-only"]):
            raise RuntimeError("Unrelated staged edits; publication postponed")
        probe = f"""from pathlib import Path
import hashlib,json
root=Path({REMOTE!r});ready=[]
for path in sorted(root.glob("*/*/epoch_*/report.json")):
 if not (path.parent/"examples.npz").is_file():continue
 relative=path.relative_to(root);group,method=relative.parts[:2]
 ready.append(dict(group=group,method=method,folder=str(path.parent),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
print(json.dumps(ready))
"""
        ready = json.loads(run(SSH + ["python3 -c " + shlex.quote(probe)], timeout=60))
        metadata_path = ROOT / "coverage90.json"
        metadata = json.loads(metadata_path.read_text())
        previous = metadata.setdefault("groups", {})
        new = [
            row
            for row in ready
            if previous.get(row["group"], {})
            .get(row["method"], {})
            .get("report_sha256")
            != row["sha256"]
        ]
        if not new:
            print("No new completed evaluations", len(ready), flush=True)
            if not args.prepare:
                publish_metadata()
            return
        ASSETS.mkdir(exist_ok=True)
        if not (ASSETS / ".git").exists():
            run(["git", "init", "--initial-branch=" + BRANCH], cwd=ASSETS)
            run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/Shdakudow/ConvRML-Uncertainty-Demo.git",
                ],
                cwd=ASSETS,
            )
        changed = 0
        for row in new:
            group, method = row["group"], row["method"]
            source = WORK / "downloads" / group / method
            source.mkdir(parents=True, exist_ok=True)
            cached = ASSETS / group / method / "summary.json"
            summary = json.loads(cached.read_text()) if cached.exists() else None
            if (
                summary
                and summary.get("report_sha256") == row["sha256"]
                and len(list(cached.parent.glob("example_*.bin.gz"))) == 50
            ):
                previous.setdefault(group, {})[method] = summary
                changed += 1
                continue
            try:
                run(
                    [
                        "rsync",
                        "-az",
                        "--include=report.json",
                        "--include=examples.npz",
                        "--exclude=*",
                        "-e",
                        "ssh -o BatchMode=yes -i "
                        + shlex.quote(str(Path.home() / ".ssh/id_ed25519")),
                        HOST + ":" + row["folder"] + "/",
                        str(source) + "/",
                    ],
                    timeout=900,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                print(
                    "Transfer postponed; retry next interval",
                    group,
                    method,
                    str(exc),
                    flush=True,
                )
                continue
            assert (
                hashlib.sha256((source / "report.json").read_bytes()).hexdigest()
                == row["sha256"]
            )
            summary = build(source, ASSETS / group / method)
            previous.setdefault(group, {})[method] = summary
            changed += 1
            print("Verified 50 exact examples", group, method, flush=True)
        if not changed:
            print("No new transfers completed; retry next interval", flush=True)
            return
        run(["git", "add", "--all"], cwd=ASSETS)
        if run(["git", "diff", "--cached", "--name-only"], cwd=ASSETS):
            run(
                [
                    "git",
                    "commit",
                    "-m",
                    "Add audited near-90-percent calibrated examples",
                ],
                cwd=ASSETS,
            )
        commit = run(["git", "rev-parse", "HEAD"], cwd=ASSETS)
        run(["git", "push", "origin", BRANCH], cwd=ASSETS, timeout=1800)
        for group, methods in previous.items():
            for method, summary in methods.items():
                summary["base"] = (
                    f"https://raw.githubusercontent.com/Shdakudow/ConvRML-Uncertainty-Demo/{commit}/{group}/{method}"
                )
        metadata["updated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        metadata["status"] = (
            "Published completed models; remaining models show inference pending."
        )
        metadata_path.write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")
        if not args.prepare:
            # A changing reference data.json/analysis_metrics.json may belong to
            # another publisher. Commit only this independent metadata overlay.
            publish_metadata()
        count = sum(len(methods) for methods in previous.values())
        (WORK / "demo_publication.json").write_text(
            json.dumps(
                dict(
                    completed=count,
                    expected=12,
                    asset_commit=commit,
                    updated_at=metadata["updated_at"],
                ),
                indent=2,
            )
            + "\n"
        )
        print("Near-90% publication", count, "/12 ready", flush=True)


if __name__ == "__main__":
    main()
