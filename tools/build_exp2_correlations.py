"""Evaluate correlations on the exact calibrated Experiment 2 demo arrays.

These are per-image results for the 50 displayed examples, not full-test means.
The fixed asset commits ensure that model/quantile/calibration changes cannot
silently reuse these values.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

from build_raw_analysis import asset_from_commit, unpack

ROOT = Path(__file__).resolve().parents[1]


def build(cache):
    metadata = json.loads((ROOT / "coverage90.json").read_text())
    groups = {}
    for camera in ("diffuser", "rml"):
        groups[camera] = {}
        for method in ("qutcc", "im2im", "ensemble5", "mc_005"):
            entry = metadata["groups"][camera][method]
            rows = []
            for index, identifier in enumerate(entry["ids"]):
                payload = asset_from_commit(cache, entry["base"], index)
                header, arrays = unpack(payload)
                if str(header["id"]) != str(identifier) or header["index"] != index:
                    raise ValueError("Saved example order/identity changed")
                prediction = arrays["prediction"].astype(np.float64)
                target = arrays["target"].astype(np.float64) / 255
                lower = arrays["lower"].astype(np.float64)
                upper = arrays["upper"].astype(np.float64)
                if not all(
                    np.isfinite(v).all() for v in (prediction, target, lower, upper)
                ):
                    raise ValueError("Nonfinite saved output")
                if not all(
                    v.min() >= 0 and v.max() <= 1 for v in (prediction, lower, upper)
                ):
                    raise ValueError("Expected the demo's clipped outputs")
                error = np.abs(prediction - target).mean(axis=0).ravel()
                width = (upper - lower).mean(axis=0).ravel()
                pearson = spearman = None
                if np.ptp(error) > 0 and np.ptp(width) > 0:
                    pearson = float(stats.pearsonr(width, error).statistic)
                    spearman = float(stats.spearmanr(width, error).statistic)
                rows.append(
                    dict(
                        index=index,
                        id=str(identifier),
                        pearson=pearson,
                        spearman=spearman,
                    )
                )
            groups[camera][method] = dict(
                base=entry["base"],
                epoch=entry["epoch"],
                count=len(rows),
                per_image=rows,
            )
            values = [r["spearman"] for r in rows if r["spearman"] is not None]
            print(
                camera,
                method,
                len(rows),
                "mean Spearman",
                float(np.mean(values)),
                flush=True,
            )
    result = dict(
        calibration="tight90",
        scope="Per-image values for the 50 displayed examples",
        definition="Pearson/Spearman on unsmoothed RGB-average interval width versus absolute error; float64; average ranks for ties; constant maps are null",
        groups=groups,
    )
    output = ROOT / "corrected-epoch50/calibrated_correlations.json"
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    temporary.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path.home() / ".local/share/convrml-coverage90-20261022/assets",
    )
    build(parser.parse_args().cache)
