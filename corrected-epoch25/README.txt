Corrected ConvRML comparison at epoch 25

Open https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-epoch25/
Use the camera selector for RML or DiffuserCam. Each has the first 50 held-out
test examples in manifest order. Click any image to compare the same pixel.
Prediction, absolute error, interval width, lower bound, and upper bound are shown.

Models (all fresh corrected training; same saved epoch 25):
- Im2im: jointly trained center/lower/upper head, all backbone weights trainable.
- QUTCC adaptation: pinball-only loss, all-block FiLM, median reconstruction.
- Ensemble: 10 independently initialized/shuffled Gaussian-NLL members.
- MC dropout: dropout throughout, p=0.1, 30 stochastic passes, MSE training.
  This interim setting was fixed before testing, not chosen on these examples.
  Final validation-based dropout selection remains pending.

60,000 training / 5,000 validation / 5,000 test images per camera.
2,048 separate calibration images; no calibration on displayed test examples.
RCPS-HB uses independent lower/upper scaling with alpha=0.10, delta=0.05 and
Bonferroni allocation across tails. The calibration unit is an image; statistical
interpretation requires exchangeable/independent calibration and test images.
Coverage is the fraction of RGB channel values inside the bounds, not a promise
that every example attains exactly 90% or that the entire image is jointly covered.
QUTCC here uses native q=.05/.95 then scale calibration, rather than searching q.

Means, lower bounds, upper bounds, metrics, and heatmaps are clipped to [0,1].
Arrays are float32 with lossless gzip transport; no float16 quantization.
Displayed metrics were calculated before encoding. Width and error share a fixed
pooled color scale per camera. Values above its 99.5th percentile saturate.

Table aggregates cover these 50 examples only. Learning curves use all 5,000
validation images; MC validation disables dropout. Individual ensemble-member
validation is not reported as ensemble-aggregate performance. Interval-width
learning curves have not been inferred from reconstruction-only logs.

Rebuild assets using tools/build_corrected_demo.py with the frozen inference
outputs from tools/export_corrected_milestone.py (run as a script inside the
ConvRML workspace; it imports the corrected model and calibration modules).
After building JSONP intermediates, run tools/pack_demo_assets.py corrected-epoch25
to write the lossless binary/gzip assets read by the website.
No trained checkpoint files are hosted in this demo repository.
