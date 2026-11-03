"""Collect verified checkpoint measurements and update only the interval JSON.

Runs in its own checkout so it cannot stage or overwrite other demo edits.
The optional loop exits after all twenty evaluations reach the public site.
"""

import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request

from build_exp4_interval_curves import build

REPOSITORY = Path(__file__).resolve().parents[1]
REMOTE = "https://github.com/Shdakudow/ConvRML-Uncertainty-Demo.git"
HOST = "jy2228@unicorn-login-02.coecis.cornell.edu"
REMOTE_OUTPUT = (
    "/home/jy2228/ConvRML/experiments/experiment4_epoch_intervals_20261103/output/"
)
PUBLIC = "https://shdakudow.github.io/ConvRML-Uncertainty-Demo/experiment4/interval-curves.json"


def command(parts, cwd=None):
    completed = subprocess.run(
        parts,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
    )
    if completed.returncode:
        raise RuntimeError(f"{parts[0]} failed: {completed.stderr[-2000:]}")
    return completed.stdout.strip()


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def collect(state):
    output = state / "output"
    output.mkdir(exist_ok=True)
    transport = (
        f"ssh -i {Path.home()}/.ssh/id_ed25519 -o BatchMode=yes -o ConnectTimeout=12"
    )
    command(
        [
            "rsync",
            "-az",
            "--include=*/",
            "--include=READY.json",
            "--include=result.json",
            "--include=progress.json",
            "--exclude=*",
            "-e",
            transport,
            f"{HOST}:{REMOTE_OUTPUT}",
            str(output) + "/",
        ]
    )
    data = build(output)
    write(state / "verified-curves.json", data)
    return data


def publish(state, data):
    checkout = state / "publish"
    if not (checkout / ".git").exists():
        command(["git", "clone", "--shared", str(REPOSITORY), str(checkout)])
        command(["git", "remote", "set-url", "origin", REMOTE], checkout)
    command(["git", "pull", "--rebase", "origin", "main"], checkout)
    relative = "experiment4/interval-curves.json"
    path = checkout / relative
    payload = (json.dumps(data, indent=2, allow_nan=False) + "\n").encode()
    if path.read_bytes() != payload:
        path.write_bytes(payload)
        command(["git", "add", relative], checkout)
        command(
            [
                "git",
                "commit",
                "--quiet",
                "-m",
                f'Add verified Exp 4 interval measurements ({data["completed"]}/20 checkpoints)',
            ],
            checkout,
        )
    command(["git", "push", "origin", "HEAD:main"], checkout)
    commit = command(["git", "rev-parse", "HEAD"], checkout)
    receipt = dict(
        completed=data["completed"],
        expected=20,
        commit=commit,
        interval_sha256=hashlib.sha256(payload).hexdigest(),
        time=time.time(),
    )
    write(state / "uploaded.json", receipt)
    if data["complete"]:
        with urllib.request.urlopen(
            PUBLIC + "?check=" + commit, timeout=30
        ) as response:
            if (
                hashlib.sha256(response.read()).digest()
                == hashlib.sha256(payload).digest()
            ):
                write(state / "published.json", receipt)
                return True
    return False


def main(args):
    args.state.mkdir(parents=True, exist_ok=True)
    with (args.state / "publisher.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while not (args.state / "published.json").exists():
            try:
                data = collect(args.state)
                write(
                    args.state / "status.json",
                    dict(
                        stage="verified",
                        completed=data["completed"],
                        expected=20,
                        time=time.time(),
                    ),
                )
                if data["completed"] and publish(args.state, data):
                    print(
                        "All twenty checkpoint evaluations verified and live",
                        flush=True,
                    )
                    return
                print(
                    f'{data["completed"]}/20 checkpoint evaluations verified and uploaded',
                    flush=True,
                )
            except Exception as error:
                write(
                    args.state / "status.json",
                    dict(stage="retry", error=str(error), time=time.time()),
                )
                print(str(error), flush=True)
                if not args.loop:
                    raise
            if not args.loop:
                return
            for _ in range(5):
                time.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        type=Path,
        default=Path.home() / ".local/share/convrml-exp4-intervals-20261103",
    )
    parser.add_argument("--loop", action="store_true")
    main(parser.parse_args())
