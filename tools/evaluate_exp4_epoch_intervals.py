"""Calibrate saved generalized checkpoints and measure their interval curves.

Uses the frozen Exp 4 evaluator, held-out 3,000-image calibration mixture,
deterministic corruptions, and all 2,000 test images per displayed condition.
There is one calibration per model/checkpoint, shared by every condition.
"""

import argparse
import fcntl
import json
from pathlib import Path
import signal
import sys
import time

import torch

PROJECT = Path("/home/jy2228/ConvRML/experiments")
ORIGINAL = PROJECT / "experiment4_generalized_20261101"
sys.path.insert(0, str(ORIGINAL / "source"))
from experiments.experiment4_demo import evaluate as e

MANIFEST = PROJECT / "dlmd_raw_adaptive_size_20261016/data/split.json"
TRAINING = PROJECT / "raw_online_scratch_30epochs_20261031_v2/results"


def fresh_stats():
    return dict(count=0, covered=0, crossed=0, pixels=0, width_sum=0.0)


def add_stats(stats, lower, upper, target):
    stats["count"] += len(target)
    stats["covered"] += int(((target >= lower) & (target <= upper)).sum())
    stats["crossed"] += int((lower > upper).sum())
    stats["pixels"] += target.numel()
    stats["width_sum"] += float((upper - lower).mean()) * len(target)


def finish(stats):
    return dict(
        count=stats["count"],
        coverage=stats["covered"] / stats["pixels"],
        width=stats["width_sum"] / stats["count"],
        crossing=stats["crossed"] / stats["pixels"],
    )


@torch.inference_mode()
def measure(model, method, fit, dataset, destination, condition=None):
    if destination.exists():
        return json.loads(destination.read_text())
    overall = fresh_stats()
    groups = {key: fresh_stats() for key in e.IDS} if condition is None else {}
    started = time.monotonic()
    for index, batch in enumerate(e.loader(dataset)):
        e.interrupted()
        y, target = e.move(batch)
        prediction, lower, upper = e.predict(model, method, y, fit)
        e.finite(prediction, lower, upper, target)
        lower, upper = lower.clamp(0, 1), upper.clamp(0, 1)
        add_stats(overall, lower, upper, target)
        if groups:
            add_stats(groups[dataset.conditions[index]], lower, upper, target)
        if (index + 1) % 100 == 0:
            e.write(
                destination.parent / "progress.json",
                dict(
                    stage="calibration_audit" if condition is None else "test",
                    condition=condition,
                    processed=index + 1,
                    total=len(dataset),
                    seconds=time.monotonic() - started,
                ),
            )
            print(condition or "calibration", index + 1, "/", len(dataset), flush=True)
    result = dict(
        overall=finish(overall), conditions={k: finish(v) for k, v in groups.items()}
    )
    e.write(destination, result)
    return result


def load_model(method, epoch, reference):
    checkpoint = TRAINING / method / "checkpoints" / f"epoch_{epoch:03d}.pt"
    saved, digest = e.read_checkpoint(checkpoint)
    config = saved["config"]
    final = reference["arms"][f"{method}_general100"]["training_config"]
    if saved["epoch"] != epoch or saved.get("smoke", False):
        raise ValueError("Wrong checkpoint epoch")
    for key in (
        "method",
        "manifest_sha256",
        "initial_weights_sha256",
        "validation_indices",
        "seed",
    ):
        if config[key] != final[key]:
            raise ValueError(f"Checkpoint training lineage differs: {key}")
    if config.get("pretrained") or config.get("initial_trained_steps") != 0:
        raise ValueError("Checkpoint was not trained from scratch")
    history = saved["history"]
    if [r["epoch"] for r in history] != list(range(1, epoch + 1)):
        raise ValueError("Incomplete checkpoint history")
    if (
        epoch == 100
        and digest != reference["arms"][f"{method}_general100"]["checkpoint_sha256"]
    ):
        raise ValueError("Final checkpoint changed")
    model = e.QUTCC() if method == "qutcc" else e.Im2im()
    e.load_model_weights(model, saved["model"])
    return model.cuda().eval().requires_grad_(False), dict(
        checkpoint=str(checkpoint),
        checkpoint_sha256=digest,
        training_config=config,
        validation=history[-1]["validation"],
    )


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / "evaluation.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    signal.signal(signal.SIGUSR1, e.stop)
    signal.signal(signal.SIGTERM, e.stop)
    torch.set_num_threads(2)
    torch.manual_seed(20261101)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    e.audit_manifest(MANIFEST)
    reference_path = ORIGINAL / "output/web_data/data.json"
    reference = json.loads(reference_path.read_text())
    model, provenance = load_model(args.method, args.epoch, reference)
    request = dict(
        schema="exp4_epoch_intervals_v1",
        method=args.method,
        epoch=args.epoch,
        manifest_sha256=e.sha(MANIFEST),
        reference_sha256=e.sha(reference_path),
        evaluator_sha256=e.sha(Path(__file__)),
        frozen_evaluator_sha256=e.sha(Path(e.__file__)),
        checkpoint_sha256=provenance["checkpoint_sha256"],
        calibration_count=3000,
        test_count_per_condition=2000,
        conditions=list(e.IDS),
        target_calibration_coverage=0.9,
        test_used_for_calibration=False,
    )
    path = args.output / "request.json"
    if path.exists() and json.loads(path.read_text()) != request:
        raise ValueError("Evaluation request changed")
    e.write(path, request)
    arm = (
        f"{args.method}_general100"
        if args.epoch == 100
        else f"{args.method}_epoch{args.epoch:03d}"
    )
    if args.epoch == 100:
        # Reuse only the original fit belonging to this exact final checkpoint.
        e.write(args.output / f"calibration/{arm}.json", reference["calibration"][arm])
    calibration = e.ModifiedPairs(MANIFEST, "calibration")
    fit = e.calibrate(model, arm, calibration, args.output)
    audit = measure(
        model, args.method, fit, calibration, args.output / "calibration-audit.json"
    )
    if abs(audit["overall"]["coverage"] - fit["calibration_coverage"]) > 5e-6:
        raise ValueError("Calibration audit does not reproduce the fitted coverage")
    tests = {}
    for condition in e.IDS:
        if args.epoch == 100:
            old = reference["results"][condition]["arms"][arm]["mean"]
            tests[condition] = dict(
                count=2000, **{k: old[k] for k in ("width", "coverage", "crossing")}
            )
        else:
            dataset = e.ModifiedPairs(MANIFEST, "test", condition)
            tests[condition] = measure(
                model,
                args.method,
                fit,
                dataset,
                args.output / f"test-{condition}.json",
                condition,
            )["overall"]
    if e.sha(provenance["checkpoint"]) != provenance["checkpoint_sha256"]:
        raise ValueError("Checkpoint changed during evaluation")
    result = dict(
        request=request,
        provenance=provenance,
        fit=fit,
        calibration=audit,
        test=tests,
        gpu=torch.cuda.get_device_name(),
        passed=True,
    )
    e.write(args.output / "result.json", result)
    e.write(
        args.output / "READY.json",
        dict(passed=True, result_sha256=e.sha(args.output / "result.json")),
    )
    print("READY", args.method, args.epoch, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=("qutcc", "im2im"), required=True)
    parser.add_argument("--epoch", type=int, choices=range(10, 101, 10), required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
