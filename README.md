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
use **Near 90%** empirical calibration. The latest frozen checkpoints use
separate calibration images to target 90.0–90.1% coverage after clipping. Tables
show actual calibration coverage and held-out test coverage separately. The test
set never chooses interval parameters; test coverage may vary.

PSNR, SSIM, width and test-coverage curves evaluate saved checkpoints at
epochs **5, 10, …, 50**, independently
calibrating each one.
The raw-QUTCC epoch-20 calibration failure is shown only as an explicitly labeled interpolation between epochs 15 and 25; its saved calibration failure is retained. Other missing evaluations remain unavailable. The image, bound, error and width
maps use saved float32 arrays, audited against their metrics before publication.
Near-90% accuracy curves use the full held-out test set, including 30-pass MC
predictions. Historical uncertainty–error correlation analyses are not presented
as analyses of the current intervals.

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

## Fixed-200 metric curves

Experiments 2 and 3 also plot mean LPIPS, Pearson r and Spearman rho at epochs
5, 10, …, 50. Every measured point uses the same first 200 held-out IDs for its
dataset and the checkpoint’s existing near-90 calibration. No training or
calibration is performed on those images. Ensemble curves use five members;
MC dropout retains 30 stochastic passes.

`metric_curves200.json` contains the 99 measured milestone means, per-metric valid
counts, cohort hashes and report hashes. The single failed raw-QUTCC epoch-20
point is a hollow-diamond estimate from epochs 15 and 25, with zero measured
samples. It does not supply a fitted quantile or a successful calibration result.
`tools/evaluate_metrics200.py` runs frozen-checkpoint inference on Unicorn;
`tools/collect_metrics200.py STUDY_DIRECTORY` validates cohort/calibration
identities and builds the public JSON. LPIPS uses AlexNet on clipped RGB;
correlations use unsmoothed mean-RGB width versus mean-RGB absolute error within
each image, then average the image scores. These 200-image curves are separate
from the existing full-test PSNR, SSIM, width and coverage curves.

Current-image metrics appear in a translucent white frame. Colored table cells
identify column-best values; coverage is ranked by closeness to 90%, and width
must be read alongside coverage.

## Raw DiffuserCam analysis metrics

Experiment 2 also shows per-image LPIPS, Pearson and Spearman in its calibrated
four-model comparison for RML and normalized DiffuserCam. These values use the
selected saved interval maps; `tools/build_exp2_correlations.py` regenerates the
Near-90% values from the exact immutable exports. They are per-image scores, not
5,000-image test means.

The [raw comparison](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/raw-diffusercam/)
shows per-image metrics in one comparison table. Its aggregate table includes
LPIPS, Pearson r and Spearman rho over the same 2,000 test images as PSNR, SSIM,
coverage and width. Missing full-test evaluations remain marked pending.
Correlations compare unsmoothed RGB-average interval width with absolute error
within each image. LPIPS uses pretrained AlexNet on clipped RGB images.

Near-90% analysis records are tied to their exact immutable array exports and
checkpoint epochs. A changed export displays unavailable scores until its
analysis is rebuilt.
`tools/build_raw_analysis.py` regenerates per-image analysis from the local asset
Git repositories and verifies every packed array checksum.
`tools/collect_raw_full_analysis.py` collects full-test inference-only reports;
`tools/evaluate_raw_full_analysis.py` produces those reports from explicit frozen
checkpoint/calibration tasks, checking the first 50 saved image metrics before
evaluating the full split. Checkpoints and calibration remain frozen; no training
is needed.

## Named captures · Sensor12

[Open the separate named-captures tab](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/named-captures/).
It shows all ten named TIFF captures reconstructed by **Exp3 clean raw QUTCC and Im2im at epoch 50**, using the explicit Sensor12 (`TIFF / 4095`) input assumption. The lower/upper bound checkbox applies to both models. Images, interval widths, original filenames and selection links are preserved; no models run in the browser. Exp2 outputs and Sensor16 outputs are not included in this tab.

These external captures have no matched ground truth. SSIM, PSNR and actual coverage are unavailable. Saved calibration parameters are reused, and bounds/predictions are clipped to [0,1]. Heatmaps use the fixed 0–1 scale, shared with the rest of the demo. Mean interval
width is shown for each capture and averaged across all ten, calculated from the
saved calibrated endpoints. `tools/build_named_captures.py` rebuilds the small static asset subset from the existing local inference report; `tools/verify_named_captures.py` checks the tab in a browser.

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

## Pixel inspection

Click a named-capture image or either panel of a video to inspect RGB-mean
interval width at that coordinate in both models. Videos pause together; seeking
another frame refreshes the selected pixel. Playback and image changes clear old
values. Crossed bounds are labeled explicitly.

The browser fetches one losslessly compressed float32 map per model/frame on
demand, using the immutable asset commit in `pixel_maps.json`. It never estimates
values from PNG or MP4 colors. Numerical sidecars live on the separate
`pixel-inspection-assets-20261030` branch to keep the Pages source small.
`tools/pixel_maps.py` writes the shared format. Add `--pixel-dir DIRECTORY` to
`tools/build_named_captures.py` or `tools/reconstruct_videos.py` to export maps;
video `--pixels-only` skips MP4 encoding during a frozen-checkpoint replay.

## Heatmap scale

The live error and interval-width maps use a fixed normalized-intensity range of
0–1 throughout the demo. This includes the legacy/current comparisons, raw data,
named captures, brightness examples and dropout-rate examples. Plot axes for
learning curves retain their metric-specific ranges. Changing map colors does
not change predictions, bounds, coverage, widths or correlation values.
