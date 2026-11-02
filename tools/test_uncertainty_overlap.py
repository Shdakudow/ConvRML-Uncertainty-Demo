"""Known-set overlap, cutoff ties, and common validity-mask behavior."""

import unittest
import numpy as np
from uncertainty_overlap import top10_overlap


class OverlapTests(unittest.TestCase):
    def test_identical_ranking_has_full_overlap_despite_different_scale(self):
        q = np.arange(100, dtype=float).reshape(10, 10)
        row = top10_overlap(q, 5 * q + 2)
        self.assertEqual(row["top10_iou"], 1)
        self.assertEqual(row["top10_intersection"], 10)
        self.assertEqual(row["top10_union"], 10)

    def test_disjoint_and_partially_shared_sets(self):
        q = np.arange(100, dtype=float)
        self.assertEqual(top10_overlap(q, q[::-1])["top10_iou"], 0)
        row = top10_overlap(q, np.roll(q, 5))
        self.assertAlmostEqual(row["top10_iou"], 1 / 3)
        self.assertEqual(row["top10_intersection"], 5)
        self.assertEqual(row["top10_union"], 15)

    def test_ties_stay_together_instead_of_using_spatial_tiebreaking(self):
        q = np.r_[np.arange(80), np.full(20, 100.0)]
        row = top10_overlap(q, q)
        self.assertEqual(row["top10_qutcc_count"], 20)
        self.assertEqual(row["top10_im2im_count"], 20)
        self.assertEqual(row["top10_iou"], 1)

    def test_invalid_values_and_crossings_use_one_common_mask(self):
        q = np.arange(100, dtype=float)
        i = q.copy()
        q[2] = np.nan
        i[3] = np.inf
        valid = np.ones(100, dtype=bool)
        valid[99] = False
        original = valid.copy()
        row = top10_overlap(q, i, valid)
        self.assertEqual(row["top10_valid_pixels"], 97)
        self.assertEqual(row["top10_iou"], 1)
        np.testing.assert_array_equal(valid, original)

    def test_constant_or_empty_maps_have_undefined_overlap(self):
        for first, second in [
            (np.ones(100), np.arange(100)),
            (np.array([]), np.array([])),
            (np.ones(1), np.ones(1)),
        ]:
            row = top10_overlap(first, second)
            self.assertIsNone(row["top10_iou"])
            self.assertIsNotNone(row["top10_reason"])
            self.assertEqual(row["top10_union"], 0)

    def test_shapes_must_match(self):
        with self.assertRaises(ValueError):
            top10_overlap(np.zeros(4), np.zeros((2, 2)))
        with self.assertRaises(ValueError):
            top10_overlap(np.zeros(4), np.zeros(4), np.ones(3))


if __name__ == "__main__":
    unittest.main()
