Corrected ConvRML comparison at epoch 25

Open https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-epoch25/
Use the camera selector for RML or DiffuserCam. Each has the first 50 held-out
test examples in manifest order. Click any image to compare the same pixel.
Prediction, absolute error, interval width, lower bound, and upper bound are shown.

Models (all fresh corrected training; same saved epoch 25):
- Im2im: jointly trained center/lower/upper head, all backbone weights trainable.
- QUTCC adaptation: pinball-only loss, all-block FiLM, median reconstruction;
  default bounds now query calibration-selected quantiles (see below).
- Ensemble: 10 independently initialized/shuffled Gaussian-NLL members.
- MC dropout: dropout throughout, p=0.1, 30 stochastic passes, MSE training.
  This interim setting was fixed before testing, not chosen on these examples.
  Final validation-based dropout selection remains pending.

60,000 training / 5,000 validation / 5,000 test images per camera.
2,048 separate calibration images; no calibration on displayed test examples.
For im2im, ensemble, and MC dropout, RCPS-HB uses independent lower/upper
scaling with alpha=0.10, delta=0.05 and
Bonferroni allocation across tails. The calibration unit is an image; statistical
interpretation requires exchangeable/independent calibration and test images.
Coverage is the fraction of RGB channel values inside the bounds, not a promise
that every example attains exactly 90% or that the entire image is jointly covered.
The previous QUTCC fixed q=.05/.95 + scaling remains accessible through the
QUTCC bounds selector; archived arrays come from immutable commit 115a797.

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

QUANTILE SEARCH UPDATE
Frozen epoch-25 QUTCC weights, no retraining. Two searches on 2,048 calibration
images, then evaluation on all 5,000 test images per camera:
1. Default asymmetric search: 18 lower candidates and 18 upper candidates fixed
   before calibration. Simultaneous image-level Hoeffding-Bentkus upper risk
   bounds use delta/36. Select the smallest calibration mean width among the
   324 pairs whose lower+upper risk bounds sum to <=0.10. No fixed tail split
   and no required q gap. This is a finite-grid search, not a global optimum.
2. Equal-tail reference: test each tail in a predeclared broad-to-narrow order,
   stopping at the first failed HB test. Tail alpha=.05, delta=.025. Later
   passing candidates after a failure are not accepted. This fixed-sequence
   procedure does not require assuming the network is monotone in q.
Bounds are clipped learned quantiles, anchored to the median to handle crossing.
No multiplicative interval scaling is used for either searched variant.
Selected global q values differ between cameras; pixel bounds depend on input.
Training weights and median reconstruction rule remain unchanged. Re-evaluating
on different GPUs can produce small BF16 numerical differences; this is not a
reconstruction improvement from calibration.
The asymmetric view is the default; equal-tail metrics are shown in the table.
Full-test comparison reports: data/{camera}/quantile_search_results.json.
The older fixed-q view is fetched from the public repository's immutable commit,
so it requires network access even when serving this page locally.
Rebuild with tools/update_quantile_search_demo.py using downloaded search outputs.
Run the inference scripts in the ConvRML workspace with its model dependencies.
