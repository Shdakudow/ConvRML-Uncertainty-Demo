"""Audit frozen near-90% results and package exact float32 browser arrays."""

import gzip
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


def build(source, output):
    report = json.loads((source / "report.json").read_text())
    request = report["request"]
    assert request["calibration"] == "tight_empirical"
    assert request["test_used_for_calibration"] is False
    assert report["calibration"]["calibrated_on"] == "calibration split only"
    assert report["calibration"]["confidence_guarantee"] is False
    assert report["test_count"] == (2000 if request["camera"] == "raw" else 5000)
    assert report["example_count"] == 50
    rows = report["per_image"][:50]
    arrays = np.load(source / "examples.npz")
    names = ("measurement", "target", "prediction", "lower", "upper")
    assert set(arrays.files) == set(names)
    expected_shape = (
        (50, 3, 270, 480) if request["camera"] == "raw" else (50, 3, 256, 256)
    )
    values = {name: arrays[name] for name in names}
    for value in values.values():
        assert value.shape == expected_shape and np.isfinite(value).all()
        assert value.min() >= 0 and value.max() <= 1
    output.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(rows):
        metrics = row["clipped"]
        x, pred, lo, hi = (values[name][index] for name in names[1:])
        actual = dict(
            width=float(np.mean(hi - lo)),
            coverage=float(np.mean((x >= lo) & (x <= hi))),
            mae=float(np.mean(np.abs(pred - x))),
            crossing=float(np.mean(lo > hi)),
            psnr=float(-10 * np.log10(max(float(np.mean((pred - x) ** 2)), 1e-12))),
        )
        for key, value in actual.items():
            tolerance = 0.0001 if key == "psnr" else 2e-6
            assert abs(value - metrics[key]) < tolerance, (
                index,
                key,
                value,
                metrics[key],
            )
        chunks, descriptors, offset = [], [], 0
        for name in names:
            array = values[name][index]
            if name in ("measurement", "target"):
                raw = np.rint(array * 255).astype("uint8").tobytes()
                encoding = "uint8"
                assert np.allclose(
                    np.frombuffer(raw, dtype="uint8").reshape(array.shape) / 255,
                    array,
                    atol=1e-7,
                )
            else:
                array = np.asarray(array, dtype="<f4")
                raw = array.reshape(-1).view("uint8").reshape(-1, 4).T.copy().tobytes()
                restored = (
                    np.frombuffer(raw, dtype="uint8")
                    .reshape(4, -1)
                    .T.copy()
                    .view("<f4")
                    .reshape(array.shape)
                )
                assert np.array_equal(restored, array)
                encoding = "float32-shuffled"
            descriptors.append(
                dict(
                    name=name,
                    shape=list(array.shape),
                    offset=offset,
                    length=len(raw),
                    encoding=encoding,
                    sha256=hashlib.sha256(raw).hexdigest(),
                )
            )
            chunks.append(raw)
            offset += len(raw)
        header = json.dumps(
            dict(id=str(row["id"]), index=index, metrics=metrics, arrays=descriptors),
            separators=(",", ":"),
        ).encode()
        binary = struct.pack("<I", len(header)) + header + b"".join(chunks)
        packed = gzip.compress(binary, compresslevel=6, mtime=0)
        assert gzip.decompress(packed) == binary
        (output / f"example_{index:02d}.bin.gz").write_bytes(packed)
    arrays.close()
    summary = dict(
        epoch=request["epoch"],
        method=request["method"],
        ids=[str(row["id"]) for row in rows],
        example_count=50,
        test_count=report["test_count"],
        calibration=report["calibration"],
        metrics=report["metrics"],
        per_image=rows,
        aggregate={
            key: float(np.mean([r["clipped"][key] for r in rows]))
            for key in rows[0]["clipped"]
        },
        report_sha256=hashlib.sha256((source / "report.json").read_bytes()).hexdigest(),
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    return summary
