Four models: reconstruction, |ground truth - reconstruction| and UB - LB. Test examples selected in manifest order; shared heatmap scales; clickable pixel comparison.

RML: backbone epoch 50, fixed head 10 epochs, RCPS (Hoeffding–Bentkus) calibration.
DiffuserCam: backbone epoch 50, fixed head 10 epochs, RCPS (Hoeffding–Bentkus) calibration.

RCPS uses alpha=0.10 and delta=0.05, fitted on 2,048 separate calibration images. Target coverage is 90%; measured test coverage may be higher. It is not a per-image guarantee. Current per-camera provenance and 5,000-image aggregate metrics are in data/{camera}/protocol.json. No test-set tuning.

Raw DiffuserCam comparison (2026-10-19)
Public page: https://shdakudow.github.io/ConvRML-Uncertainty-Demo/raw-diffusercam/
Original raw QUTCC/Im2im at epoch 50.
Includes reconstruction, absolute error, calibrated interval width, bounds, pixel inspector, full-test coverage and five-epoch calibration curves.
Paper-style quantile calibration and asymmetric Im2im scale calibration are labeled separately from earlier RCPS experiments.
