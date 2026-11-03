"""Protect scientific weighting and separation of calibration/test cohorts."""

import unittest

from build_exp4_interval_curves import CONDITIONS, summarize


def measurement():
    calibration, test = {}, {}
    for condition in CONDITIONS:
        exposure = condition.startswith("exposure")
        calibration[condition] = dict(
            count=150 if exposure else 300, coverage=0.9, width=0.1, crossing=0
        )
        test[condition] = dict(count=2000, coverage=0.8, width=0.2, crossing=0)
    calibration["exposure_050"]["width"] = 0.3
    calibration["exposure_150"]["width"] = 0.5
    test["exposure_050"]["coverage"] = 0.5
    test["exposure_150"]["coverage"] = 0.7
    return dict(
        request=dict(epoch=10, checkpoint_sha256="fixture"),
        calibration=dict(
            conditions=calibration, overall=dict(count=3000, coverage=0.9, width=0.13)
        ),
        test=test,
        fit=dict(calibration_coverage=0.9, status="fitted", target_met=True),
    )


class IntervalCurves(unittest.TestCase):
    def test_equal_training_families_combine_two_exposures(self):
        result = summarize(measurement())
        self.assertAlmostEqual(result["mean"]["calibration_width"], 0.13)
        self.assertAlmostEqual(
            result["conditions"]["exposure"]["calibration_width"], 0.4
        )
        self.assertAlmostEqual(result["mean"]["test_coverage"], 0.78)
        self.assertAlmostEqual(result["conditions"]["exposure"]["test_coverage"], 0.6)

    def test_wrong_test_or_calibration_count_is_rejected(self):
        for split in ("test", "calibration"):
            data = measurement()
            group = data[split] if split == "test" else data[split]["conditions"]
            group["gaussian"]["count"] -= 1
            with self.assertRaises(ValueError):
                summarize(data)

    def test_audit_must_match_fitted_coverage(self):
        data = measurement()
        data["fit"]["calibration_coverage"] = 0.95
        with self.assertRaises(ValueError):
            summarize(data)

    def test_failed_calibration_is_retained_and_marked(self):
        data = measurement()
        data["fit"].update(
            status="target_unattainable", target_met=False, failure="fixture failure"
        )
        result = summarize(data)
        self.assertFalse(result["calibration_target_met"])
        self.assertEqual(result["calibration_failure"], "fixture failure")


if __name__ == "__main__":
    unittest.main()
