# One experiment, two datasets

Open `comparison/` to compare Im2im, deep ensemble, MC dropout and QUTCC on
**RML** or **normalized DiffuserCam**. The dataset selector switches between the
two; images, error/width maps, bounds, pixel inspection and milestone curves keep
the existing viewer behavior. Detailed settings and extra comparisons are folded
away to reduce text.

This is a presentation copy of `corrected-epoch50/`, not a new training run.
The HTML base URL points there, so scripts, result metadata and immutable saved
arrays are reused. No checkpoints, metrics, calibration settings or sample IDs
are changed or copied. Original experiment pages remain available.

The existing calibration selector is preserved: Near 90% uses empirical fits;
Reference uses the original RCPS baseline / paper-style QUTCC results. These are
different calibration procedures, not interchangeable guarantees. Missing results
stay unavailable. A later update to the shared results also updates this page.
