# ConvRML reconstruction and uncertainty demo

Four models: reconstruction, |ground truth - reconstruction| and UB - LB. Twenty test examples per camera; shared heatmap scales; clickable pixel comparison.

RML: backbone epoch 50, fixed head 10 epochs, RCPS (Hoeffding–Bentkus) calibration.
DiffuserCam: backbone epoch 50, fixed head 10 epochs, Empirical calibration.

RCPS uses alpha=0.10 and delta=0.05, fitted on 2,048 separate calibration images. Target coverage is 90%; measured test coverage may be higher. It is not a per-image guarantee. Current per-camera provenance and 5,000-image aggregate metrics are in data/{camera}/protocol.json. No test-set tuning.

https://shdakudow.github.io/ConvRML-Uncertainty-Demo/
