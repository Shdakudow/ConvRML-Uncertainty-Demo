"""Check learning-curve cohort integrity and the displayed arithmetic average."""

import copy
import unittest
from build_exp4_learning import build, NAMES


def fixture():
    source = {"methods": {}}
    for method in ("qutcc", "im2im"):
        config = dict(
            method=method,
            epochs=100,
            manifest_sha256="155670232c27b3201582f5a1b67fb4196e8123e40f388d9c951df4418f7144fb",
            validation_indices=list(range(100)),
            source_commit="fixture",
        )
        history = []
        for epoch in range(1, 101):
            conditions = {
                key: dict(
                    count=100,
                    ssim=(index + 1) / 20 + epoch / 1000,
                    psnr=10 + index + epoch / 100,
                )
                for index, key in enumerate(NAMES)
            }
            history.append(dict(epoch=epoch, validation=dict(conditions=conditions)))
        source["methods"][method] = dict(
            config=config, history=history, history_sha256="fixture"
        )
    return source


class LearningTests(unittest.TestCase):
    def test_average_is_over_the_ten_matched_conditions(self):
        result = build(fixture())
        row = result["methods"]["qutcc"]["history"][-1]
        self.assertAlmostEqual(row["mean"]["ssim"], 0.375)
        self.assertAlmostEqual(row["mean"]["psnr"], 15.5)
        self.assertEqual(row["conditions"]["gaussian"]["ssim"], 0.2)
        self.assertEqual(result["validation_scene_count"], 100)
        self.assertEqual(result["validation_pairs"], 1000)

    def test_incomplete_history_is_rejected(self):
        source = fixture()
        source["methods"]["qutcc"]["history"].pop()
        with self.assertRaises(ValueError):
            build(source)

    def test_changed_panel_and_unbalanced_conditions_are_rejected(self):
        source = fixture()
        source["methods"]["im2im"]["config"]["validation_indices"][0] = 999
        with self.assertRaises(ValueError):
            build(source)
        source = fixture()
        source["methods"]["qutcc"]["history"][0]["validation"]["conditions"][
            "gaussian"
        ]["count"] = 99
        with self.assertRaises(ValueError):
            build(source)


if __name__ == "__main__":
    unittest.main()
