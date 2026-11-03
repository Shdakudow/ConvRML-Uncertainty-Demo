"""Submit the twenty Exp 4 checkpoint evaluations once, using at most two GPUs."""

import fcntl
import json
from pathlib import Path
import subprocess

ROOT = Path("/home/jy2228/ConvRML/experiments/experiment4_epoch_intervals_20261103")


def main():
    with (ROOT / "submission.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record = ROOT / "submission.json"
        if record.exists():
            print(record.read_text())
            return
        subprocess.run(
            ["bash", "-n", str(ROOT / "run_exp4_epoch_intervals.sbatch")], check=True
        )
        command = [
            "/usr/local/slurm/current/bin/sbatch",
            "--parsable",
            "--job-name=exp4-epoch-intervals",
            "--array=0-19%2",
            f"--chdir={ROOT}",
            f"--output={ROOT}/logs/%A_%a.out",
            f"--error={ROOT}/logs/%A_%a.err",
            str(ROOT / "run_exp4_epoch_intervals.sbatch"),
        ]
        response = subprocess.check_output(command, text=True).strip()
        job = response.split(";")[0]
        if not job.isdigit():
            raise ValueError("Unrecognized submission response")
        result = dict(
            job=job,
            command=command,
            methods=["qutcc", "im2im"],
            epochs=list(range(10, 101, 10)),
        )
        temporary = record.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        temporary.replace(record)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
