Exp2 MC dropout rate comparison
==============================

Open corrected-epoch50/ and choose RML or Normalized DiffuserCam.
The "MC dropout · which rate works best?" section is beneath the epoch curves.

Curves: epoch-50 models trained separately at p=0.05, 0.10 and 0.20.
Each is evaluated with dropout active on the same 5,000 validation images,
using averages of 30, 60 and 100 stochastic passes. Predictions and validation
metrics are clipped to [0,1]. The selected p=0.05 has the highest SSIM at
100 passes for both cameras. Test images were not used for this selection.
These are single-run results, without repeated-seed confidence intervals.
Different runs used different GPUs; the page does not compare their timings.
Dropout is placed at 36 encoder and 12 decoder sites; training loss is MSE.

Examples: first eight test images in manifest order, not chosen for quality.
Only p=0.05 and p=0.10 have saved test arrays. All displayed reconstructions
are existing 30-pass predictions, not the 100-pass validation outputs.
No p=0.20 examples are fabricated, regenerated or substituted.
Optional error and uncertainty maps share one scale per camera across both
rates and all eight images. Scale maximum is their joint 99.5th percentile.
Width maps use each checkpoint's saved asymmetric RCPS-HB calibrated bounds
(alpha=0.10, delta=0.05, 2,048 separate calibration images). Calibration does
not change the reconstructed image. Wider intervals alone do not imply
better or worse reconstruction.

Source on Unicorn:
  /home/jy2228/ConvRML/results/corrected_comparison_20261006/
    {rml,diffuser}/dropout_validation/{mc_005,mc_010,mc_020}.json
    {rml,diffuser}/dropout_policy.json
  /home/jy2228/ConvRML/results/corrected_demo_epoch50_20261011/
    {rml,diffuser}/{mc_005,mc_010}/{examples.npz,report.json}

sources/ contains the original validation JSON reports.
data.json contains plot values, matched sample IDs, example metrics and
the saved calibration scales. validation_trend.csv contains all 18 rows.
tools/fetch_dropout_rate_study.py exports the read-only source results.
tools/verify_dropout_rate_study.py checks the page in a real browser.

The main four-model comparison still uses p=0.05 and 30 passes.
"Normalized DiffuserCam" is the Cornell parallel-camera data used in Exp2,
not the raw DLMD data in Exp3.
