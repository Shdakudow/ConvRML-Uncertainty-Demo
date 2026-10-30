# DiffuserCam video reconstruction and uncertainty

Five external sequences from the linked DiffuserCam capture folder: videos 1, 4, 6, 7, and 10. The page compares the same frozen clean-raw epoch-50 QUTCC and Im2im models used by the named-capture demo.

Each MP4 shows a reconstruction above its uncertainty map. Both models play synchronously and share a frame slider. The plot displays each frame's mean interval width and a dashed whole-video mean. Its default vertical scale is 0–0.25; “Zoom width axis to data” reveals smaller temporal changes without changing the heatmaps.

## Meaning of the measurements

For each frame, width is the mean of `clip(upper, 0, 1) - clip(lower, 0, 1)` over RGB and all pixels, calculated before video encoding. The uncertainty image averages this width over RGB and uses the fixed inferno color scale from 0 to 1, independently of the mean-width plot’s 0–0.25 axis. Crossed bounds appear in magenta. Bounds are not sorted to hide crossings.

The table reports the mean, standard deviation, coefficient of variation (standard deviation divided by mean), minimum, and maximum of frame means. Low variation means the image-average width stays relatively constant; it does not imply accurate reconstruction, valid coverage, or unchanged spatial maps.

These are unpaired external measurements. The reference GIFs are reconstructions, not ground truth. PSNR, SSIM, LPIPS, actual coverage, and uncertainty–error correlation are unavailable. Original calibration parameters are reused without fitting to videos.

## Data and reproducibility

All 1,580 source TIFFs are read in numerical frame order: 226, 280, 339, 397, and 338 frames respectively. These video TIFFs are 8-bit RGB, unlike the 16-bit-container named still images. Video preprocessing divides by 255, applies a full-field 4×4 area mean to 270×480, and rounds to the training loader's 8-bit-equivalent input values. No per-frame contrast normalization, temporal smoothing, or retraining is used. The reconstruction and uncertainty panels are rotated 180° after inference, with labels upright and reconstruction above uncertainty. Playback is explicitly presented at 20 fps (twice the previous speed), retaining every source frame; acquisition fps is unverified.

- `data.json`: per-frame metrics, model and calibration provenance, and summary values.
- `assets/video*/{qutcc,im2im}/`: MP4s, first-frame PNGs, CSV, and inference report with checkpoint SHA-256.
- `assets/video*/frame_metrics.csv`: both models' numerical frame metrics.
- `assets/video*/width_plot.png`: full 0–0.25 and detailed width plots.
- `../tools/reconstruct_videos.py`: inference and streaming H.264 export using the original model source.
- `../tools/build_video_demo.py`: numerical verification, plot generation, and publication from completed reports.

The processing receipts retain Drive IDs, original filenames, raw TIFF SHA-256, dtype/range, and prepared-input SHA-256 outside this public demo. Authenticated temporary download URLs are not published.

The original 0–1 exports can be rotated and accelerated locally with `tools/restyle_saved_videos.py`; no model replay or color-range inversion is required.
