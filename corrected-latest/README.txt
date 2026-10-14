Latest corrected ConvRML comparison

RML: epoch 40. DiffuserCam: epoch 35. All four methods within each camera use
the same immutable checkpoint epoch. First 50 test examples in manifest order.
60k train / 5k validation / 5k test; independent 2048-image calibration.
RCPS-HB alpha=.10, delta=.05, separate lower/upper factors for every method.
QUTCC: sampled-q pinball training, 48 FiLM sites; inference q=.05/.95 then scaling.
No learned-q head or quantile search is included in this milestone refresh.
Im2im: end-to-end center and endpoint training. Ensemble: 10 Gaussian-NLL members.
MC dropout: p=.1, 30 samples, fixed before testing; final p selection is pending.
All displayed images/metrics are clipped to [0,1]. Predictions are saved float32.
The 50-example aggregates are not full-test estimates. Learning curves use 5k
validation images; MC validation disables dropout. There is no ensemble-mean
learning curve from individual-member validation. Width and absolute error share
a pooled color scale per camera, saturating at the 99.5th percentile.
Pixel clicks show actual saved lower/upper values; no distribution interpolation.
Old epoch25 exports remain in Git history, commit 34262cb.
