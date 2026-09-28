CONVRML INTERACTIVE VIEWER

Open index.html in Chrome, Safari, or Firefox. Keep app.js, style.css and the entire data folder beside it. No installation, web server, internet connection, or cluster login is required.

Use Next example, Previous, Random example, or the dropdown to explore 20 real held-out examples. Buttons load saved inference, not a new GPU calculation. Click any image/heatmap to inspect that pixel across all methods. Choose Red/Green/Blue or type x/y coordinates. Focus a model canvas and use arrow keys for fine movement.

The maps show empirical calibrated 90% interval width (RGB averaged) and absolute reconstruction error, with common scales across methods and examples. Per-image SSIM is shown to five significant figures. These 20 examples are not the full 1,000-image aggregate benchmark.

Pixel curves show RAW q=.05,.25,.50,.75,.95 quantiles, not calibrated intervals or a PDF. Q-conditioned is queried directly. Ensemble uses the five-Gaussian mixture. MC uses 30 new reproducible dropout draws. The fixed head only predicts .025/.975; missing values are left blank by default. Its optional linear interpolation is explicitly an assumption and cannot establish distribution accuracy.

Models: exact epoch 50. Fixed model: exact 50-epoch normal backbone, then 50 fresh endpoint-head epochs. Other models reuse the full 25k experiment checkpoints, not the 5k CRPS or compact toy models.

First 20 shared test entries; no visual selection. Separate 2,048-image calibration factors. RGB float16 browser arrays; metrics were computed at original precision. Display clipping does not affect metrics. See data/protocol.json for provenance.

UPDATED COMPACT VIEW
Four models share one desktop row. Main image selects reconstruction or one of the five quantiles. The gallery shows all five quantile images for every model. Shared 2x/4x zoom crops around the selected pixel; use coordinate inputs to select a precise region. Difference map compares the currently displayed image against ground truth or another model. Metrics continue to describe the ordinary reconstruction. Fixed-head missing quantiles remain unavailable by default; optional interpolation is labeled.

CLICK-TO-INSPECT PIXEL
Click any main image or quantile image to open a dialog with the same selected pixel across all five quantiles and four models. Each cell shows a 17x17 magnified neighborhood with the exact selected pixel outlined, plus that pixel's RGB color and values. Use the quantile slider to highlight q=.05/.25/.50/.75/.95 and update the full images. Enter x/y for precise positioning. Escape or Close dismisses the dialog.
