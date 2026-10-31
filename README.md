# Pixel inspection sidecars

Numerical interval-width maps for the public video and named-capture demos.
Maps store float32 mean-RGB width from clipped calibrated endpoints, plus an
any-RGB crossed-bound mask. Gzip and byte shuffling are lossless; colors are
never inverted to obtain values. Video coordinates follow the 180-degree display
rotation. Named-capture coordinates follow the unrotated 480×270 images.

The ten named captures reuse their saved float32 inference. All video frames
are replayed with the original frozen epoch-50 clean-raw models and calibration;
checkpoint identities and per-frame means are checked against the published
reports. No training or calibration fitting is performed. The main branch's
`tools/pixel_maps.py` documents the binary layout; `heatmap-pixels.js` reads it.
