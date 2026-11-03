# Experiment 4 display

The scene viewer compares clean-trained epoch-50 and generalized epoch-100
QUTCC and Im2im models on the same 50 displayed test scenes. Predictions and
metrics in `data.json` retain their original export. Uncertainty maps and
metrics are visible directly in the active category.

Absolute-error maps show the RGB mean of `|clip(prediction, 0, 1) − target|`,
computed before display quantization. Every map uses the same 0–1 color scale.
`error-maps.json` points to an immutable asset commit containing 2,200 PNGs:
11 conditions × four models × 50 scenes. The exporter replays the original
frozen models and deterministic inputs, verifies checkpoint hashes, and checks
per-scene PSNR, SSIM, and MAE against the original evaluation. The metadata
builder checks every image hash, dimensions, scene order, and replay tolerance.

The Overview tab includes learning curves from the recorded generalized-model histories, with one
validation point per completed epoch (1–100). Both models use the same fixed
100 validation scenes under each of ten conditions. “Average” is the arithmetic
mean of those ten equally sized groups. Checkboxes add or remove condition
curves; solid lines show QUTCC and dashed lines show Im2im. The average uses teal
for QUTCC and orange for Im2im; category colors match their checkbox borders. Hover shows epoch
values. Plot selections do not change the displayed test scene.

Category tabs load their own scene images when selected. Absolute errors remain
visible below reconstructions, followed by uncertainty maps and metrics.

Reconstruction comparisons use one row per model, with clean-trained
and generalized results beside each other. Sensor inputs and ground truth are
reference images. Uncertainty and absolute-error maps have wider rows than
reconstructions. “Uneven pixel response” is the display name for
the existing `fixed_pattern` gain-and-offset modification; its parameters and
stored condition ID are unchanged.

Click a reconstruction, ground truth, error map, or uncertainty map to mark
the same image coordinate across all four models. This reuses the earlier
experiments’ `HeatmapPixels.pointAt` and `HeatmapPixels.mark` helpers: the same
24-screen-pixel square, with white/black/yellow outlines. Clicking elsewhere
moves the marker; Escape clears it. The position persists across scene and
category changes. Sensor inputs are unmarked, as in Exp 3. Images remain
full-frame with their existing sizes and metrics; there are no zoom controls
or inspection panels.

Every graph has numeric axis ticks, a written scale, units, and a model key:
QUTCC is solid; Im2im is dashed. Mobile graphs use a smaller coordinate system
to keep tick labels readable. Uncheck “Zoom vertical scales” to use the full
SSIM, coverage, and width ranges instead of fitting the selected curves.

Below validation SSIM/PSNR, the same condition checkboxes control calibration
interval width and independent test coverage against training epoch. Saved
checkpoints are evaluated every 10 epochs. Each checkpoint has one global
calibration fit targeting 90% on the original 3,000-scene mixture, shared by all
conditions. Width is measured on that calibration split. Test coverage uses all
2,000 separate test scenes per displayed condition. Exposure combines both gains
equally; Average weights each of the ten training families equally.

`interval-curves.json` contains verified results only and reports progress out
of twenty model/checkpoint evaluations. Dots mark measured checkpoints; lines
join adjacent completed 10-epoch measurements and leave gaps where evaluations
are missing. Failed calibration targets remain marked rather than discarded.
The 90% test-coverage reference does not imply guaranteed conditional or test
coverage. Epoch-100 test results reuse the original exact-checkpoint evaluation;
calibration-width audits are newly measured. Small floating-point audit
differences are bounded by the export verifier.

The histories logged exposure as one family mixing gains 0.50 and 1.50, so its
learning curve combines them. The test-scene viewer displays the gains
separately. Historical clean-trained baselines did not record the same
per-corruption validation panel, so they do not appear in these learning curves.
Validation curves and the independent 2,000-scene test metrics use different
cohorts and should not be treated as the same measurement.

Reproduction tools in `../tools/`:

- `export_exp4_error_maps.py`: frozen-model replay and absolute-error export.
- `build_exp4_error_metadata.py`: completed-export verification and asset links.
- `build_exp4_learning.py`: history validation and learning-data export.
- `test_exp4_learning.py`: cohort, completeness, and averaging checks.
- `verify_video_intensity.py`: browser checks covering this page and the videos.
- `evaluate_exp4_epoch_intervals.py`: frozen-checkpoint calibration and evaluation.
- `build_exp4_interval_curves.py`: receipt, cohort, and weighting verification.
- `test_exp4_interval_curves.py`: exposure weighting and calibration/test checks.
- `publish_exp4_interval_curves.py`: collect results and publish just the interval
  JSON from an isolated checkout, exiting after all measurements are live.
