"""Deterministic Phase 3A-03 validation regression tests."""
import datetime as dt
import unittest
from scripts.quality import evaluate

TODAY = dt.date(2026, 11, 11)


def metric(value=3.5, date="2026-11-10", status="ok", unit="%"):
    return {"value": value, "date": date, "status": status, "unit": unit}


class QualityTests(unittest.TestCase):
    def test_valid_observation_passes(self):
        report = evaluate({"metrics": {"hy": metric()}}, {}, TODAY)
        self.assertEqual(report["metrics"]["hy"]["quality"], "pass")

    def test_expired_observation_is_blocked(self):
        report = evaluate({"metrics": {"hy": metric(date="2026-10-01")}}, {}, TODAY)
        self.assertEqual(report["metrics"]["hy"]["quality"], "blocked")
        self.assertIn("observation_older_than_limit", report["metrics"]["hy"]["errors"])

    def test_future_date_is_blocked(self):
        report = evaluate({"metrics": {"hy": metric(date="2026-11-12")}}, {}, TODAY)
        self.assertIn("future_observation_date", report["metrics"]["hy"]["errors"])

    def test_invalid_value_is_blocked(self):
        report = evaluate({"metrics": {"hy": metric(value=float("nan"))}}, {}, TODAY)
        self.assertEqual(report["metrics"]["hy"]["quality"], "blocked")

    def test_partial_source_is_not_scoreable(self):
        report = evaluate({"metrics": {"breadth": metric(status="partial")}}, {}, TODAY)
        self.assertEqual(report["metrics"]["breadth"]["quality"], "blocked")

    def test_institutional_sources_are_separate(self):
        snapshot = {"metrics": {"inst": {"status": "partial", "date": "2026-11-10",
            "official_sources": {
                "cash_inst": {"status": "ok", "date": "2026-11-10", "unit": "TWD",
                              "categories": [{"name": "合計", "net_twd": -100}]},
                "futures": {"status": "ok", "date": "2026-11-10", "unit": "口",
                            "foreign_tx_net_oi": -50}}}}}
        report = evaluate(snapshot, {}, TODAY)
        self.assertEqual(report["metrics"]["inst.cash_inst"]["quality"], "pass")
        self.assertEqual(report["metrics"]["inst.futures"]["quality"], "pass")
        self.assertEqual(report["metrics"]["inst"]["quality"], "blocked")

    def test_official_taiex_disagreement_blocks(self):
        snapshot = {"metrics": {"taiex": {
            "status": "ok", "value": 40000, "date": "2026-11-10", "unit": "points",
            "official_sources": {"tw_price": {"status": "ok", "value": 41000,
                "date": "2026-11-10", "unit": "points"}}}}}
        report = evaluate(snapshot, {}, TODAY)
        self.assertIn("official_yahoo_taiex_disagreement", report["metrics"]["taiex"]["errors"])


if __name__ == "__main__":
    unittest.main()
