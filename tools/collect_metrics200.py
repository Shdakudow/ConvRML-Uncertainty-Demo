"""Publish fixed-200 measured milestone means; label only failed epoch 20 as estimated."""

import argparse, csv, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    tasks = json.loads((args.source / "tasks.json").read_text())
    groups = {g: {} for g in ["rml", "diffuser", "raw_clean"]}
    missing = []
    cohorts = {}
    per_image = []
    for task in tasks:
        group, method = task["group"], task["method"]
        rows = groups[group].setdefault(method, [])
        if task["status"] != "ready":
            rows.append(
                dict(
                    epoch=task["epoch"],
                    status="failed",
                    reason="Calibration infeasible",
                )
            )
            continue
        path = args.source / "results" / (task["key"] + ".json")
        if not path.exists():
            missing.append(task["key"])
            continue
        r = json.loads(path.read_text())
        assert r["count"] == 200 and len(r["per_image"]) == 200
        assert not r["training_performed"] and not r["calibration_refitted"]
        assert (
            r["calibration"] == task["calibration"]
            and r["calibration_report_sha256"] == task["calibration_report_sha256"]
        )
        assert len({x["id"] for x in r["per_image"]}) == 200
        if group in cohorts:
            assert cohorts[group] == r["test_ids_sha256"]
        cohorts[group] = r["test_ids_sha256"]
        rows.append(
            dict(
                epoch=r["epoch"],
                status="complete",
                count=200,
                metrics=r["metrics"],
                n_valid=r["n_valid"],
                report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
        per_image.extend(
            dict(group=group, method=method, epoch=r["epoch"], **row)
            for row in r["per_image"]
        )
    if missing:
        raise RuntimeError("Missing measured milestones: " + ", ".join(missing))
    for models in groups.values():
        for rows in models.values():
            rows.sort(key=lambda r: r["epoch"])
            for row in rows:
                if row["epoch"] != 20 or row["status"] != "failed":
                    continue
                before = next(
                    r for r in rows if r["epoch"] == 15 and r["status"] == "complete"
                )
                after = next(
                    r for r in rows if r["epoch"] == 25 and r["status"] == "complete"
                )
                row.update(
                    status="estimated",
                    count=0,
                    source_epochs=[15, 25],
                    metrics={
                        key: (value + after["metrics"][key]) / 2
                        for key, value in before["metrics"].items()
                        if value is not None and after["metrics"][key] is not None
                    },
                    note="Linear interpolation of neighboring 200-image means; epoch-20 calibration failed; not a measured or calibrated result",
                )
    result = dict(
        protocol="fixed200_near90_clipped_rgb_unsmoothed_v1",
        sample_count=200,
        test_ids_sha256=cohorts,
        groups=groups,
        definition="LPIPS-AlexNet v0.1 on clipped RGB; Pearson/Spearman within each unsmoothed mean-RGB width/error map, averaged over the same first 200 test IDs at every epoch. Fitted calibration is reused unchanged. MC dropout uses 30 passes and fixed seed 20261030.",
        interpolation="Only the failed raw-QUTCC epoch 20 is a labeled estimate from epochs 15 and 25; no test-based calibration or invented q values.",
    )
    (ROOT / "metric_curves200.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    with (args.source / "per_image_metrics200.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(per_image[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(per_image)
    print(
        "Published",
        len(per_image),
        "per-image evaluations and one labeled epoch-20 estimate",
    )


if __name__ == "__main__":
    main()
