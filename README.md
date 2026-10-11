# ConvRML reconstruction and uncertainty demo

Four models: reconstruction, |ground truth - reconstruction| and UB - LB. Test examples selected in manifest order; shared heatmap scales; clickable pixel comparison.

RML: backbone epoch 50, fixed head 10 epochs, RCPS (Hoeffding–Bentkus) calibration.
DiffuserCam: backbone epoch 50, fixed head 10 epochs, RCPS (Hoeffding–Bentkus) calibration.

RCPS uses alpha=0.10 and delta=0.05, fitted on 2,048 separate calibration images. Target coverage is 90%; measured test coverage may be higher. It is not a per-image guarantee. Current per-camera provenance and 5,000-image aggregate metrics are in data/{camera}/protocol.json. No test-set tuning.

https://shdakudow.github.io/ConvRML-Uncertainty-Demo/

## Corrected experiment: epoch 25

[Open the new comparison](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-epoch25/). Both cameras use the same saved epoch for end-to-end im2im, all-block FiLM QUTCC, ten-member ensemble, and all-block MC dropout (p=0.1, 30 passes). Each camera shows 50 held-out examples with reconstruction, absolute error, RCPS interval width, and clickable lower/upper bounds. Calibration uses 2,048 separate images. These sample averages are not full-test estimates.

The earlier demo remains available at the repository root. Its example assets now use lossless gzip transport to reduce storage; the underlying predictions and metrics are unchanged. Both pages require a modern browser with DecompressionStream support and HTTP(S) hosting. See corrected-epoch25/README.txt for the complete interim protocol.

## QUTCC quantile-search refinement

The epoch-25 page now defaults to learned lower/upper quantile queries selected
on the calibration set, instead of fixing q=0.05/0.95 and scaling their distances.
Its selector restores the previous fixed-q view for a direct visual comparison.
A separate table compares fixed-q scaling, equal-tail quantile search, and
asymmetric quantile search on all 5,000 test images. The three other models are
unchanged. Both quantile searches control the 90% target with an image-level
risk procedure; the asymmetric search accounts for all candidate endpoints.
Weights are frozen, and reconstruction accuracy is not being improved by calibration.
