"""Small lossless sidecars for inspecting float32 RGB-mean interval widths."""

import gzip
import json
import struct
from pathlib import Path

import numpy as np


def load_pixel_map(path):
    """Read a sidecar as (float32 width map, boolean crossed-bound mask)."""
    payload = gzip.decompress(Path(path).read_bytes())
    header_size = struct.unpack("<I", payload[:4])[0]
    header = json.loads(payload[4 : 4 + header_size])
    assert header["version"] == 1 and header["encoding"] == "float32-shuffled-le"
    height, width = header["height"], header["width"]
    count, start = height * width, 4 + header_size
    assert len(payload) == start + count * 4 + (count + 7) // 8
    values = (
        np.frombuffer(payload[start : start + 4 * count], np.uint8)
        .reshape(4, count)
        .T.copy()
        .view("<f4")
        .reshape(height, width)
    )
    crossing = np.unpackbits(np.frombuffer(payload[start + 4 * count :], np.uint8))
    return values, crossing[:count].reshape(height, width).astype(bool)


def save_pixel_map(path, width, crossing):
    """Store a displayed H×W width map and any-RGB crossed-bound mask.

    Byte shuffling improves gzip compression without quantizing the float32 map.
    The mask is packed most-significant bit first. Coordinates follow the display.
    """
    width = np.asarray(width, dtype="<f4")
    crossing = np.asarray(crossing, dtype=bool)
    assert width.ndim == 2 and width.shape == crossing.shape
    assert np.isfinite(width).all()
    height, columns = width.shape
    header = json.dumps(
        dict(version=1, width=columns, height=height, encoding="float32-shuffled-le"),
        separators=(",", ":"),
    ).encode()
    shuffled = np.frombuffer(width.tobytes(), np.uint8).reshape(-1, 4).T.tobytes()
    payload = (
        struct.pack("<I", len(header))
        + header
        + shuffled
        + np.packbits(crossing.ravel()).tobytes()
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(payload, compresslevel=4, mtime=0))
