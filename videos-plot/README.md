# DiffuserCam video reconstruction and uncertainty

Five external sequences from the linked DiffuserCam capture folder: videos 1, 4, 6, 7, and 10. The page compares the same frozen clean-raw epoch-50 QUTCC and Im2im models used by the named-capture demo.

Each MP4 shows a reconstruction above its uncertainty map. Both models play synchronously and share a frame slider. The plot displays each frame's mean interval width and a solid cumulative average from frame 1 through the current frame. Width-axis zoom is enabled by default. Unchecking it restores the fixed 0–0.25 plot range; the heatmap colors always remain 0–1. The cumulative average is hidden initially and can be overlaid using “Show cumulative average”.

## Meaning of the measurements

For each frame, width is the mean of `clip(upper, 0, 1) - clip(lower, 0, 1)` over RGB and all pixels, calculated before video encoding. The uncertainty image averages this width over RGB and uses the fixed raw-DiffuserCam blue-to-red color scale from 0 to 1, independently of the mean-width plot’s 0–0.25 axis. Crossed bounds appear in magenta. Bounds are not sorted to hide crossings.

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

Blue-to-red 0–1 source exports can be rotated and accelerated locally with `tools/restyle_saved_videos.py`; no model replay or color-range inversion is required.

Plot legend: QUTCC is green; Im2im is orange. Thin solid lines show per-frame width; an optional slightly stronger overlay shows the cumulative average while the per-frame lines fade. CSVs include both values.

The canonical palette is defined in `tools/heatmap_colors.py`, matching raw DiffuserCam. Video color changes are rendered from float model outputs, not inferred by inverting compressed video colors. The collector checks the palette metadata before publishing.

Click a reconstruction or uncertainty pixel to pause both videos and display the
numerical RGB-mean interval width for both models. The selected coordinate follows
frame seeks; playback clears it. Sidecars are float32 values from the frozen
models, fetched on demand through `../pixel_maps.json`, rather than inferred
from compressed video colors. Coordinates follow the displayed 180° rotation.

The model-agreement plot below mean width has a shared comparison selector:
**Spearman correlation** or **Overlap · most uncertain 10% of pixels** (default).
Changing either the graph selector or the selected-frame panel selector updates
both. Each graph point compares QUTCC with Im2im at one frame. Frame seeking,
playback and low-agreement jump buttons use the selected measure. In overlap
mode, all selected locations are displayed rather than one rank-gap patch. The
legacy rank inspection/tracking controls appear in Spearman mode.

Overlap is intersection-over-union (IoU). Both models use the same finite,
uncrossed pixels. Within each map, select widths at or above its 90th percentile
(linear interpolation), then compute `shared / selected_by_either`. A score of
100% means identical selected locations; 0% means no shared location. Cutoff ties
are kept together, so selection can slightly exceed 10%; displayed counts show
this. A constant map has no distinct high-uncertainty set and is undefined.
The categorical map uses purple for both models, green for QUTCC only, orange for
Im2im only, dark blue for neither, and magenta for excluded pixels.

This is a full-frame comparison, with no foreground mask or attention model.
It measures agreement about relatively high uncertainty, not reconstruction
accuracy or actual coverage. The five lowest-overlap frames are selected
separately from the five lowest-Spearman frames, with at least 20 frames between
jump buttons. The named-capture page has the same selector and overlap display.
CSV exports contain both measures, thresholds, intersection/union and selected
counts. `agreement/overlap-overview.{png,pdf}` shows all five videos and ten named
captures. Saved numerical maps are reused; no inference, retraining or calibration
fitting is performed. Existing correlation and rank-gap values are preserved.

## Brightness–uncertainty correlation per frame

The brightness plot measures spatial correlation **within each frame**, then
plots those coefficients against frame number. Its two curves are QUTCC and
Im2im. Spearman ρ is the default; Pearson r is an optional linear-association
view. The vertical axis stays at −1 to +1, with a zero reference line. Hover
shows coefficients and valid-pixel counts; clicking seeks both videos. The plot
also follows playback, the frame slider, and keyboard left/right arrows when
focused. CSV, PNG, and PDF exports retain every frame without temporal smoothing.

For each model, brightness is the RGB mean of its own clipped full-precision
reconstruction. It is **estimated image brightness**, not measured illumination,
linear-light luminance, or sensor-pixel intensity. Uncertainty is the RGB mean of
`clip(upper,0,1) - clip(lower,0,1)`. Both coefficients use identical spatial pixels,
excluding nonfinite values and any crossed RGB interval in either model. The same
180° rotation is applied to both displayed maps; correlation is unchanged by that
shared permutation. Ties receive average ranks; a constant map gives an undefined
coefficient and a gap in the graph. No pixel-independence p-values are reported.

Positive correlation means brighter reconstructed pixels tend to have wider
intervals; negative means darker pixels tend to have wider intervals. A value
near zero does not rule out a curved relationship. These are within-model
associations: the models produce different brightness estimates. They do not
establish causality, uncertainty accuracy, or real video coverage. Clipping and
scene structure can influence the coefficients. Width divided by intensity is
not used, since it measures relative width and is unstable near black.

`tools/analyze_video_intensity.py` replays the original frozen epoch-50 models
using the exact published calibration and receipt-verified prepared inputs. It
checks per-frame mean brightness and width against the published video reports
before recording correlations; no video colors are inverted. The analysis job
is independent of all ongoing training and never refits calibration.
`tools/build_video_intensity.py` verifies the completed export and creates
`intensity/data.json`, per-video CSVs, and publication figures. The four numerical
tests cover nonlinear monotonic associations, tied ranks, common exclusion masks,
and undefined constant maps.
