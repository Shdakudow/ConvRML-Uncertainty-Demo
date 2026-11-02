"""Known-order, common-mask, and constant-map checks for video correlations."""

import unittest
import numpy as np
from analyze_video_intensity import frame_correlations


class VideoIntensityTests(unittest.TestCase):
    def test_monotonic_nonlinear_relation_has_perfect_rank_correlation(self):
        intensity = np.arange(1.0, 10.0).reshape(3, 3)
        values = frame_correlations(
            dict(qutcc=intensity, im2im=intensity),
            dict(qutcc=intensity**3, im2im=-(intensity**3)),
            dict(qutcc=np.zeros((3, 3), bool), im2im=np.zeros((3, 3), bool)),
        )
        self.assertAlmostEqual(values["qutcc"]["spearman"], 1)
        self.assertAlmostEqual(values["im2im"]["spearman"], -1)
        self.assertLess(values["qutcc"]["pearson"], 0.99)

    def test_models_share_mask_and_invalid_pixels_cannot_change_scores(self):
        image = np.arange(6.0).reshape(2, 3)
        q = np.array([[0.0, 1.0, 1000.0], [3.0, 4.0, 5.0]])
        i = image.copy()
        i[1, 0] = np.nan
        crossed_q = np.zeros((2, 3), bool)
        crossed_q[0, 2] = True
        values = frame_correlations(
            dict(qutcc=image, im2im=image),
            dict(qutcc=q, im2im=i),
            dict(qutcc=crossed_q, im2im=np.zeros((2, 3), bool)),
        )
        for row in values.values():
            self.assertEqual(row["valid_pixels"], 4)
            self.assertAlmostEqual(row["spearman"], 1)

    def test_constant_maps_and_no_valid_pixels_are_null_not_zero(self):
        image = np.ones((2, 3))
        values = frame_correlations(
            dict(qutcc=image, im2im=image),
            dict(qutcc=image, im2im=image),
            dict(qutcc=np.zeros((2, 3), bool), im2im=np.zeros((2, 3), bool)),
        )
        self.assertIsNone(values["qutcc"]["spearman"])
        self.assertIsNone(values["im2im"]["pearson"])
        values = frame_correlations(
            dict(qutcc=image, im2im=image),
            dict(qutcc=image, im2im=image),
            dict(qutcc=np.ones((2, 3), bool), im2im=np.zeros((2, 3), bool)),
        )
        self.assertEqual(values["qutcc"]["valid_pixels"], 0)
        self.assertIsNone(values["qutcc"]["valid_mean_width"])

    def test_tied_values_use_average_ranks(self):
        image = np.array([[1.0, 1.0, 2.0, 3.0]])
        width = np.array([[3.0, 3.0, 2.0, 1.0]])
        mask = np.zeros(image.shape, bool)
        values = frame_correlations(
            dict(qutcc=image, im2im=image),
            dict(qutcc=width, im2im=width),
            dict(qutcc=mask, im2im=mask),
        )
        self.assertAlmostEqual(values["qutcc"]["spearman"], -1)


if __name__ == "__main__":
    unittest.main()
