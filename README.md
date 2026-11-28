# ConvRML Reconstruction and Uncertainty Demo

Interactive browser demos for lensless imaging reconstruction and uncertainty quantification. Four models: QUTCC, Im2im, Deep Ensemble, MC Dropout.

## Demos

| Link | Description |
|------|-------------|
| [MIRFLICKR + PLD](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/mirflickr-demo/) | Main demo — MIRFLICKR and Parallel Lensless Dataset, with/without ground truth, video sequences |
| [Simplified comparison](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/comparison/) | Single-page four-model comparison, two datasets |
| [Experiment 2](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/corrected-epoch50/) | Near-90% calibration, RML dataset |
| [Experiment 3](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/raw-diffusercam/) | Near-90% calibration, raw DiffuserCam |
| [Named captures](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/named-captures/) | Ten external TIFF captures, no ground truth |
| [Legacy](https://shdakudow.github.io/ConvRML-Uncertainty-Demo/) | Original 50-epoch benchmark |

## Calibration

Bounds use K-RCPS (MIRFLICKR / PLD) or RCPS Hoeffding–Bentkus (earlier experiments). Target coverage 90% (α=0.10, δ=0.05) on 2,048–3,000 held-out calibration images. Test coverage is reported separately and may differ.

## Metrics shown

Per scene, per model: SSIM, PSNR, LPIPS, mean interval width, Spearman correlation (uncertainty vs. error), AUSE (100-step sparsification). Heatmaps use a shared per-scene scale: 0 → max(error, width) across all models.

## Data

Binary exports (`.bin.gz`) contain float32 prediction, lower bound, upper bound, and measurement arrays. All metrics are computed from these arrays; no values are read from PNGs or video frames.
