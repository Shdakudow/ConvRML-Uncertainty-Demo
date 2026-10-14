# ConvRML reconstruction and uncertainty demo

Four models: reconstruction, |ground truth - reconstruction| and UB - LB. Test examples selected in manifest order; shared heatmap scales; clickable pixel comparison.

RML: backbone epoch 50, fixed head 10 epochs, RCPS (Hoeffding–Bentkus) calibration.
DiffuserCam: backbone epoch 50, fixed head 10 epochs, RCPS (Hoeffding–Bentkus) calibration.

RCPS uses alpha=0.10 and delta=0.05, fitted on 2,048 separate calibration images. Target coverage is 90%; measured test coverage may be higher. It is not a per-image guarantee. Current per-camera provenance and 5,000-image aggregate metrics are in data/{camera}/protocol.json. No test-set tuning.

https://shdakudow.github.io/ConvRML-Uncertainty-Demo/

## Latest corrected experiment

[Open the updated comparison](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-latest/).
RML uses epoch 40; DiffuserCam uses epoch 35. Within each camera, all four methods
use the same saved epoch. There are 50 test examples per camera, with independent
RCPS calibration on 2,048 images (alpha=0.10, delta=0.05).

Compare end-to-end im2im, sampled-q pinball QUTCC with 48 FiLM sites, ten-member
NLL ensemble, and MC dropout (p=0.1, 30 draws). QUTCC bounds use q=.05/.95 then
separate RCPS scale factors. No learned-q head is included. The current refresh
uses checkpoint-specific scale calibration, not the earlier quantile-grid search.

Reconstruction, absolute error, interval width, lower/upper images, clipped
metrics, and linked pixel inspection use saved float32 outputs. Sample averages
cover these 50 cases only; reconstruction learning curves use 5,000 validation
images. See corrected-latest/README.txt for details.

The legacy 50-epoch experiment remains at the repository root. The earlier
epoch-25 comparison is archived in Git commit 34262cb; its old URL redirects to
the latest comparison. Training checkpoints are not hosted in this repository.
