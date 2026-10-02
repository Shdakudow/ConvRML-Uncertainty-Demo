# ConvRML: reconstruction error and uncertainty

Public demo: https://shdakudow.github.io/ConvRML-Uncertainty-Demo/

Compare four methods on the first 20 held-out test images from each camera: fixed-head ConvRML (im2im-style), q-conditioned ConvRML, five-member Gaussian-NLL deep ensemble, and MSE-trained MC dropout with 30 inference draws.

The three aligned rows show reconstruction, mean RGB absolute error `|ground truth - reconstruction|`, and mean RGB interval width `upper bound - lower bound`. Both heatmaps share one scale within each camera, across all four models and all examples. Click a pixel for numerical comparison; use the next/random buttons and shared zoom.

## Exact experiments shown

| Camera | Backbone checkpoint | Fixed-head training | Train / validation / test |
|---|---:|---:|---|
| RML | Epoch 45 | 10 additional epochs | 60,000 / 5,000 / 5,000 |
| DiffuserCam | Epoch 40 | 10 additional epochs | 60,000 / 5,000 / 5,000 |

These are the latest complete comparisons exported for this release, not the pending epoch-50 results. The calibration factors target 90% empirical coverage using 2,048 separate images. This demo does not show RCPS intervals. Uncertainty width describes a range; it is not expected to equal the observed absolute error. RGB channels are averaged after taking absolute differences.

Each camera's data/protocol.json records provenance, calibration factors, and full-test aggregate metrics. The per-image UI metrics describe the selected example. MC dropout uses fresh reproducible draws for this export. Arrays are float32; images are clipped to [0,1] only for display. Pixel inspection reports unclipped saved values. The heatmap scale saturates at the pooled 99.5th percentile of error and width maps. Camera scales differ and are labeled.

## Hosting

GitHub Pages serves the repository root on main. No model server is required: example buttons load saved responses. Keep index.html, app.js, dataset.js, style.css and data/ together to open the viewer locally. The previous quantile explorer is retained in Git history at ba23277d830eea88ac7142e20a0e25b9f735aaa1.

Architecture reference: https://github.com/lakabuli/ConvRML/. This is an independent research visualization, not an official project release.
