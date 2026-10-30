# ConvRML reconstruction and uncertainty demo

## Simplified comparison

[One experiment · two datasets](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/comparison/)
keeps the current four-model comparison in one page. Choose RML or normalized
DiffuserCam, browse images, inspect pixels and bounds, and hover the learning
curves. Extra explanations and studies are folded away. This presentation copy
reuses the existing saved results; the original pages remain available.

## Current comparison · coverage close to 90%

[Experiment 2](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-epoch50/)
and [Experiment 3](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/raw-diffusercam/)
default to **Near 90%** empirical calibration. The latest frozen checkpoints use
separate calibration images to target 90.0–90.1% coverage after clipping. Tables
show actual calibration coverage and held-out test coverage separately. The test
set never chooses interval parameters; test coverage may vary.

The selector's **Reference** mode preserves the original RCPS/paper-style results
and its original milestone curves. Near-90% PSNR, SSIM, width and test-coverage
curves evaluate saved checkpoints at epochs **5, 10, …, 50**, independently
calibrating each one. Corrupted raw stops at its actual 30 adaptation epochs.
Pending evaluations and calibration failures remain gaps. The image, bound, error and width
maps use saved float32 arrays, audited against their metrics before publication.
Near-90% accuracy curves use the full held-out test set, including 30-pass MC
predictions; Reference retains the original validation curves. Reference uncertainty–error correlation
analyses are not presented as analyses of the new intervals.

`tools/publish_coverage90.py` fetches completed evaluations, verifies and packages
50 examples per model, publishes immutable array assets on a separate branch,
and updates only `coverage90.json`. It never changes the reference result files.
Run `tools/verify_coverage90.py` with the browser-test environment to check the
local site, or pass the deployed base URL. Legacy/named-capture tabs retain their
reference intervals.

`tools/publish_coverage90_curves.py` collects compact metrics with matching split
identities and updates `coverage90_curves.json`. A local five-minute automation
publishes results as the milestone jobs finish, without downloading new image
caches. Hovering an epoch compares models' exact values and calibration coverage.

## Raw DiffuserCam analysis metrics

Experiment 2 also shows per-image Pearson and Spearman in its calibrated
four-model comparison for RML and normalized DiffuserCam. These values use the
selected saved interval maps; `tools/build_exp2_correlations.py` regenerates the
Near-90% values from the exact immutable exports. They are per-image scores, not
5,000-image test means.

The [raw comparison](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/raw-diffusercam/)
shows LPIPS, Pearson r and Spearman rho beside each model, plus averages over the
50 displayed examples. The separate full-test table still covers 2,000 images.
Correlations compare unsmoothed RGB-average interval width with absolute error
within each image. LPIPS uses pretrained AlexNet on clipped RGB images.

Clean/corrupted studies and Near-90%/Reference modes have separate analysis
records tied to their exact immutable array exports and checkpoint epochs. A
changed export displays unavailable scores until its analysis is rebuilt.
`tools/build_raw_analysis.py` regenerates these records from the local asset Git
repositories and verifies every packed array checksum; no training is needed.

## Named captures · Sensor12

[Open the separate named-captures tab](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/named-captures/).
It shows all ten named TIFF captures reconstructed by **Exp3 clean raw QUTCC and Im2im at epoch 50**, using the explicit Sensor12 (`TIFF / 4095`) input assumption. The lower/upper bound checkbox applies to both models. Images, interval widths, original filenames and selection links are preserved; no models run in the browser. Exp2 outputs and Sensor16 outputs are not included in this tab.

These external captures have no matched ground truth. SSIM, PSNR and actual coverage are unavailable. Saved calibration parameters are reused, and bounds/predictions are clipped to [0,1]. Heatmaps use one shared scale across both models and all ten captures. `tools/build_named_captures.py` rebuilds the small static asset subset from the existing local inference report; `tools/verify_named_captures.py` checks the tab in a browser.

## Earlier benchmark demos

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
