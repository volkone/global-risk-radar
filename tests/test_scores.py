"""Regression checks for Phase 3B coverage-gated independent scores."""
import unittest
from scripts.scores import evaluate


class ScoreTests(unittest.TestCase):
    def test_no_inputs_never_produces_zero_risk(self):
        result = evaluate({"metrics": {}}, {"metrics": {}})
        self.assertIsNone(result["global"]["score"])
        self.assertIsNone(result["taiwan"]["score"])

    def test_taiwan_and_global_remain_separate(self):
        metrics = {"hy": {"value": 8}, "ig": {"value": 3},
                   "vix": {"value": 45}, "indices": {"drawdown_pct": 30},
                   "nfci": {"value": 1.5}, "us10y": {"value": 5}}
        quality = {"metrics": {key: {"quality": "pass"} for key in metrics}}
        result = evaluate({"metrics": metrics}, quality)
        self.assertEqual(result["global"]["status"], "provisional")
        self.assertIsNotNone(result["global"]["score"])
        self.assertIsNone(result["taiwan"]["score"])

    def test_blocked_input_excluded_from_coverage(self):
        metrics = {"hy": {"value": 8}, "ig": {"value": 3},
                   "vix": {"value": 45}, "indices": {"drawdown_pct": 30},
                   "nfci": {"value": 1.5}}
        quality = {"metrics": {key: {"quality": "pass"} for key in metrics}}
        quality["metrics"]["hy"]["quality"] = "blocked"
        result = evaluate({"metrics": metrics}, quality)
        self.assertIsNone(result["global"]["score"])
        self.assertLess(result["global"]["coverage"], 0.85)


if __name__ == "__main__":
    unittest.main()
