"""Backtest and historical institutional extraction regression tests."""
import unittest
from scripts.backtest import run
from scripts.history import observations


class HistoricalTests(unittest.TestCase):
    def test_no_short_sample_threshold_claim(self):
        fx = [{"date": f"2026-01-{i:02d}", "value": 30 + i*.01}
              for i in range(1, 29)]
        tw = [{"date": f"2026-01-{i:02d}", "value": 1000 + i}
              for i in range(1, 29)]
        r = run(fx, tw)
        self.assertEqual(r["status"], "insufficient_samples")
        self.assertIsNone(r["recommended_live_threshold"])

    def test_future_outcome_never_generates_live_threshold(self):
        fx = [{"date": f"2026-{1+i//28:02d}-{1+i%28:02d}", "value": 30+i*.01}
              for i in range(120)]
        tw = [{"date": x["date"], "value": 1000+i} for i,x in enumerate(fx)]
        r = run(fx, tw)
        self.assertFalse(r["full_model_validated"])
        self.assertIsNone(r["recommended_live_threshold"])

    def test_institutional_scalar_extraction(self):
        snapshot = {"metrics": {"inst": {"status": "partial", "official_sources": {
            "cash_inst": {"status": "ok", "date": "2026-11-10", "unit": "TWD",
                          "provider": "TWSE", "categories": [
                              {"name": "合計", "net_twd": -100}]},
            "futures": {"status": "ok", "date": "2026-11-09", "unit": "口",
                        "provider": "TAIFEX", "foreign_tx_net_oi": -50}}}}}
        rows = list(observations(snapshot))
        self.assertEqual({x[0]: x[4] for x in rows},
                         {"inst.cash_inst": -100, "inst.futures": -50})


if __name__ == "__main__":
    unittest.main()
