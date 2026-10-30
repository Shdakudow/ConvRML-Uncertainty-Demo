"""Shared 0–1 blue-to-red palette, matching the raw DiffuserCam canvas renderer."""

from matplotlib.colors import LinearSegmentedColormap
import numpy as np

STOPS = np.array(
    [[20, 35, 60], [34, 95, 157], [35, 185, 172], [243, 203, 85], [250, 112, 82]],
    dtype=float,
)
CROSSING_COLOR = np.array([227, 32, 201], dtype=np.uint8)
CSS_GRADIENT = (
    "linear-gradient(90deg, "
    + ", ".join("#%02x%02x%02x" % tuple(rgb.astype(int)) for rgb in STOPS)
    + ")"
)
CMAP = LinearSegmentedColormap.from_list("diffuser_blue_red", STOPS / 255, N=4096)
CMAP.set_bad("#e320c9")


def colorize(values, crossing=None):
    """Map normalized widths to RGB; retain explicit invalid-interval flags."""
    values = np.asarray(values)
    finite = np.isfinite(values)
    normalized = np.clip(np.where(finite, values, 0), 0, 1)
    positions = np.linspace(0, 1, len(STOPS))
    rgb = np.stack(
        [np.interp(normalized, positions, STOPS[:, channel]) for channel in range(3)],
        axis=-1,
    )
    rgb = np.floor(rgb + 0.5).astype(np.uint8)
    invalid = ~finite if crossing is None else (~finite | crossing)
    rgb[invalid] = CROSSING_COLOR
    return rgb
