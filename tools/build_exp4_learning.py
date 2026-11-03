"""Validate recorded generalized training history and export category learning curves."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = dict(
    clean="Clean",
    gaussian="Gaussian noise",
    poisson="Poisson noise",
    poisson_gaussian="Poisson + Gaussian",
    exposure="Exposure · both gains",
    dead_pixels="Dead pixels",
    fixed_pattern="Fixed-pattern noise",
    gaussian_blur="Gaussian blur",
    resolution="Resolution loss",
    jpeg="JPEG compression",
)


def build(source):
    methods = {}
    indices = None
    for name in ("qutcc", "im2im"):
        record = source["methods"][name]
        config = record["config"]
        history = record["history"]
        if (
            config["epochs"] != 100
            or config["method"] != name
            or [r["epoch"] for r in history] != list(range(1, 101))
        ):
            raise ValueError("Incomplete or wrong training history")
        if (
            config["manifest_sha256"]
            != "155670232c27b3201582f5a1b67fb4196e8123e40f388d9c951df4418f7144fb"
        ):
            raise ValueError("Wrong original split")
        if indices is None:
            indices = config["validation_indices"]
        if indices != config["validation_indices"] or len(indices) != 100:
            raise ValueError("Validation panels differ")
        rows = []
        for item in history:
            values = item["validation"]["conditions"]
            if set(values) != set(NAMES) or any(
                v["count"] != 100 for v in values.values()
            ):
                raise ValueError("Validation condition counts changed")
            mean = {
                metric: sum(float(v[metric]) for v in values.values()) / len(values)
                for metric in ("psnr", "ssim")
            }
            rows.append(
                dict(
                    epoch=item["epoch"],
                    mean=mean,
                    conditions={
                        key: {m: float(v[m]) for m in ("psnr", "ssim")}
                        for key, v in values.items()
                    },
                )
            )
        methods[name] = dict(
            label="QUTCC" if name == "qutcc" else "Im2im",
            epochs=100,
            history_sha256=record["history_sha256"],
            training_source_commit=config["source_commit"],
            history=rows,
        )
    return dict(
        schema="exp4_learning_v1",
        definition="Generalized-model validation at every completed epoch. Average is the arithmetic mean over ten equally weighted conditions, with the same fixed 100 scenes under every condition (1,000 scene–condition pairs). Predictions clipped to [0,1].",
        exposure_definition="Exposure is one logged validation family, mixing gains 0.50 and 1.50. Separate gain learning curves were not logged.",
        baseline_definition="Historical clean-trained epoch-50 baselines did not log the same per-corruption validation panel; these learning curves show generalized training only.",
        conditions=[dict(id=k, label=v) for k, v in NAMES.items()],
        methods=methods,
        validation_scene_count=100,
        validation_pairs=1000,
        validation_indices_sha256=hashlib.sha256(
            json.dumps(indices).encode()
        ).hexdigest(),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument(
        "--output", type=Path, default=ROOT / "experiment4/learning-data.json"
    )
    a = p.parse_args()
    result = build(json.loads(a.source.read_text()))
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        "Verified 100 epochs for both models; matched 100-scene panel and ten conditions."
    )
