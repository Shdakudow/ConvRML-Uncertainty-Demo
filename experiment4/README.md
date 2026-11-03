# Experiment 4 display

The scene viewer compares clean-trained epoch-50 and generalized epoch-100
QUTCC and Im2im models on the same 50 displayed test scenes. Predictions and
metrics in `data.json` retain their original export. Uncertainty maps and
metrics load when their section is expanded.

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
visible below reconstructions; the uncertainty section starts collapsed.

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
