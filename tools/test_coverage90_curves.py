"""Reject mixed splits/protocols, invented metrics and duplicate milestones."""

import copy
import unittest

from publish_coverage90_curves import empty, validate


class Curves(unittest.TestCase):
    def test_all_expected_checkpoints_are_explicit(self):
        payload = validate(empty())
        self.assertEqual(
            payload["counts"], dict(complete=0, failed=0, pending=100, expected=100)
        )
        self.assertEqual(len(payload["groups"]["raw_clean"]["qutcc"]), 10)

    def test_failed_calibration_has_no_invented_test_metric(self):
        payload = empty()
        row = payload["groups"]["raw_clean"]["qutcc"][0]
        row.update(status="failed", error="No feasible extreme quantile endpoints")
        self.assertEqual(validate(payload)["counts"]["failed"], 1)
        row["metrics"] = dict(coverage=0.9)
        with self.assertRaises(ValueError):
            validate(payload)

    def test_duplicate_epoch_rejected(self):
        payload = empty()
        payload["groups"]["rml"]["im2im"][1]["epoch"] = 5
        with self.assertRaises(ValueError):
            validate(payload)

    def test_full_test_count_and_calibration_provenance_required(self):
        payload = empty()
        row = payload["groups"]["rml"]["im2im"][0]
        row.update(
            status="complete",
            test_count=5000,
            report_sha256="a" * 64,
            calibration=dict(
                calibrated_on="calibration split only",
                confidence_guarantee=False,
                n_images=2048,
                calibration_coverage=0.9,
            ),
            metrics=dict(clipped=dict(coverage=0.899, width=0.02, psnr=30, ssim=0.9)),
        )
        self.assertEqual(validate(payload)["counts"]["complete"], 1)
        row["metrics"]["raw"] = dict(coverage=0.895, width=1.8, psnr=20, ssim=0.7)
        self.assertEqual(validate(payload)["counts"]["complete"], 1)
        bad = copy.deepcopy(payload)
        bad["groups"]["rml"]["im2im"][0]["test_count"] = 50
        with self.assertRaises(ValueError):
            validate(bad)
        row["calibration"]["confidence_guarantee"] = True
        with self.assertRaises(ValueError):
            validate(payload)


if __name__ == "__main__":
    unittest.main()
