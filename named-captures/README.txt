Named DiffuserCam captures — Sensor12, Exp3 models only

This page uses the saved epoch-50 clean raw QUTCC and Im2im checkpoints on the
ten user-supplied TIFF measurements. It contains no Exp2 or Sensor16 predictions.

Preprocessing: unsigned TIFF / 4095, 4x4 area mean downsampling to 270x480,
then round to the raw training cache's 8-bit-equivalent RGB intensity levels.
The actual sensor acquisition bit depth has not been independently confirmed.
There is no per-image contrast stretch, auto rotation or output rescaling.

The original checkpoint calibration is reused. Predictions and calibrated
endpoints are clipped to [0,1]. Model identities and fitted parameters are in
data.json, without weight binaries or private filesystem paths.

Uncertainty maps are RGB-average upper-minus-lower. A single shared inferno
color scale uses the 99.5th percentile across the two models and all ten images.
Higher widths saturate. A pixel with any crossed RGB interval is magenta.
Bounds are never silently sorted. The Show lower & upper bounds checkbox
reveals the actual saved lower and upper PNGs for both models.

No matched ground truth was supplied or found in the checked cluster datasets.
SSIM, PSNR, MAE, LPIPS, error maps, actual coverage and error/width correlations
cannot be measured for these captures. The saved 90% calibration target does
not certify coverage on this external distribution. metrics.csv contains widths
and latency; unavailable ground-truth metrics are empty, not zero.

Saved inference ran on Apple MPS in float32. Metrics use saved float32 arrays;
PNG assets are encoded at 8 bits/channel. Original TIFFs and trained weights
are not uploaded to this demo.

The page runs no models and fits no calibration in the browser. Image names,
selection and bounds visibility persist in its URL. The separate navigation
tab leaves benchmark experiments 1, 2 and 3 available at their existing routes.
