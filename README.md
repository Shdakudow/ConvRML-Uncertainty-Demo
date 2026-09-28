# ConvRML uncertainty demo

Interactive comparison of fixed-head ConvRML, q-conditioned ConvRML, deep ensemble, and MC dropout on 20 held-out image pairs.

Open `index.html` locally, or visit the GitHub Pages deployment. No model server or GPU is required. The site loads saved inference for each example.

## Features

- Four reconstructions in a compact aligned view, with uncertainty and difference maps.
- Full images at quantiles 0.05, 0.25, 0.50, 0.75, and 0.95.
- Click a pixel to see its RGB values and magnified neighborhood across all quantiles.
- Shared zoom, example navigation, and comparison against ground truth or another model.

## Scientific interpretation

The fixed-head model uses 50 reconstruction-backbone epochs followed by 50 fresh quantile-head epochs. The other models use 50 epochs per model/member. Training budgets differ.

Fixed-head native outputs are only q=0.025 and 0.975. Its five requested quantiles are unavailable by default; optional linear interpolation is explicitly labeled as assumed.

Quantile images and curves are raw, uncalibrated predictions. Interval-width maps use empirical 90% calibration fitted on 2,048 separate images. Coverage is not a per-image guarantee. The 20 displayed examples are the first shared test entries, not a representative substitute for the 1,000-image benchmark.

Ensemble quantiles come from a five-component Gaussian mixture. MC quantiles use 30 reproducible stochastic draws. Q-conditioned quantiles are queried directly. RGB display arrays use float16 precision; metrics were computed before conversion. These are marginal quantile images, not joint posterior samples.

## Provenance

The reconstruction architecture is based on [ConvRML](https://github.com/lakabuli/ConvRML). This repository contains a research visualization and exported predictions, not an official release of that project. See `data/protocol.json` and `README.txt` for experiment details.

## Hosting

GitHub Pages can serve the repository root on the `main` branch. `.nojekyll` enables static-file publishing. Keep the `data/` folder alongside `index.html`, `app.js`, and `style.css`.
