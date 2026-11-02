"""Overlap of high-uncertainty locations on one common valid pixel set."""

import numpy as np


def top10_overlap(first, second, valid=None):
    """Return Jaccard/IoU for values at or above each map's 90th percentile.

    Percentiles use NumPy's linear interpolation. Include all cutoff ties rather
    than arbitrarily choosing spatial pixels to force an exact 10% count. Report
    the selected counts. A constant map has no distinct high-uncertainty set, so
    overlap is undefined. ``valid`` can exclude crossed intervals in both maps.
    """
    first, second = np.asarray(first), np.asarray(second)
    if first.shape != second.shape:
        raise ValueError("Uncertainty maps must have matching shapes")
    if valid is None:
        valid = np.ones(first.shape, dtype=bool)
    valid = np.asarray(valid, dtype=bool)
    if valid.shape != first.shape:
        raise ValueError("Common mask must match both maps")
    valid = valid & np.isfinite(first) & np.isfinite(second)
    q = first[valid].astype(np.float64)
    i = second[valid].astype(np.float64)
    result = dict(
        top10_iou=None,
        top10_intersection=0,
        top10_union=0,
        top10_qutcc_count=0,
        top10_im2im_count=0,
        top10_threshold_qutcc=None,
        top10_threshold_im2im=None,
        top10_valid_pixels=len(q),
        top10_reason=None,
    )
    if len(q) < 2:
        result["top10_reason"] = "Fewer than two jointly valid pixels"
        return result
    if np.ptp(q) == 0 or np.ptp(i) == 0:
        result["top10_reason"] = "A constant map has no distinct most-uncertain pixels"
        return result
    threshold_q, threshold_i = np.quantile(q, 0.9), np.quantile(i, 0.9)
    selected_q, selected_i = q >= threshold_q, i >= threshold_i
    intersection = int(np.count_nonzero(selected_q & selected_i))
    union = int(np.count_nonzero(selected_q | selected_i))
    result.update(
        top10_iou=intersection / union,
        top10_intersection=intersection,
        top10_union=union,
        top10_qutcc_count=int(selected_q.sum()),
        top10_im2im_count=int(selected_i.sum()),
        top10_threshold_qutcc=float(threshold_q),
        top10_threshold_im2im=float(threshold_i),
    )
    return result
