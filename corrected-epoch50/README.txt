Completed corrected experiment, epoch 50.

Models: end-to-end im2im, 10-member Gaussian-NLL ensemble, and MC dropout
(p=0.1, 30 stochastic passes, all-block dropout). A camera can initially show
only the finished exports; its manifest explicitly lists pending methods.
Adaptive QUTCC is marked Unavailable until its exact epoch-20 checkpoint has
been calibrated and exported. Each camera updates independently. Its epoch-20
results are explicitly labeled against epoch-50 baselines (unequal budgets).

60,000 training images; 5,000 validation; 5,000 test; 2,048 independent
calibration images. The page shows the first 50 manifest test examples per
camera, without selecting attractive examples. Averages are for those 50 only.

Native bounds:
- im2im: learned lower/upper outputs trained at q=0.05/0.95; center trained MSE.
- Ensemble: mean of the 10 member means; variance = mean(member variance +
  member mean squared) - ensemble mean squared. Native bounds are mean +/-
  1.6448536 standard deviations, a Gaussian moment-matching approximation.
- MC dropout: sample mean and population variance of 30 dropout draws;
  same Gaussian bound approximation. The p=0.1/30-draw policy is fixed for
  continuity with the earlier demo, not claimed to be validation-optimal.

Calibration leaves point predictions unchanged. Separate nonnegative global
lower/upper scales are fit per model, camera and checkpoint. Scale distances
from the raw center to each native endpoint (floored at 1e-6), then clip the
calibrated endpoints to [0,1]. Independent RCPS uses alpha=0.10 and delta=0.05,
with alpha/2 and delta/2 for each tail. The unit for confidence is an image;
its loss is the fraction of missed RGB pixel values. This targets average
coverage and does not promise exactly 90% coverage on each example.

Error is mean RGB |ground truth - prediction|. Uncertainty is mean RGB UB-LB.
Their shared color scale supports comparison but the two need not be equal.
The pixel inspector uses exact saved float32 values. SSIM/PSNR, coverage and
width use clipped predictions/endpoints. Learning curves use validation
metrics; the MC curve is dropout-off, not the stochastic test prediction.
Ensemble member validation curves are not presented as ensemble metrics.

Exact float32 assets are hosted on an immutable commit in the same repository
on a dedicated asset branch, preserving older demos within Pages size limits.
See assets.json for the commit, and each camera's protocol.json for the fitted
scales, calibration audit, sample IDs, manifest hashes and checkpoint provenance.
The browser displays saved inference; it does not run model training/inference.

Automatic update (requested October 15, 2026):
- RML epoch-20 inference job 288596 depends on training job 278657.
- DiffuserCam epoch-20 inference job 288597 depends on training job 278682.
- Both passed the GPU inference smoke gate (job 288595).
- New QUTCC exports use results/adaptive_q20_demo_20261015 on Unicorn.
- A user LaunchAgent checks every 300 seconds while the Mac is awake/online.
  It retries on later checks/reboot and expires after 30 days; once all eight
  camera/model exports are published, further checks exit without network work.
- Publisher status, logs and last published readiness are in
  ~/.local/share/convrml-epoch50-auto/results/ (also linked from
  ~/Downloads/ConvRML_Epoch50_Demo/).

Ensemble learning curves: evaluate all ten saved members at epochs 5,10,...,50
on all 5,000 validation images, average raw predicted means, clip the combined
prediction, and compute per-image PSNR/SSIM before averaging over images.
No retraining and no averaging of individual-member PSNR/SSIM. Curve exports
are in results/ensemble10_validation_curves_20261015 on Unicorn and publish
automatically after all 20 camera/milestone evaluations complete.
