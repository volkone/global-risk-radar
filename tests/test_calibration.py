"""3B-02 calibration regression tests."""
import unittest
from scripts.calibration import evaluate, rank, transform, extract


class CalibrationTests(unittest.TestCase):
    def test_rank_does_not_include_current(self):
        self.assertEqual(rank(5, [1, 2, 3, 4]), 100)

    def test_short_history_cannot_generate_signal(self):
        data = {"metrics": {"fx": {"date": "2026-11-10", "value": 33,
                                  "history": [{"date": "2026-11-09", "value": 32}]}}}
        q = {"metrics": {"fx": {"quality": "pass"}}}
        r = evaluate(data, q, {"observations": []})
        self.assertIsNone(r["signals"]["fx"]["score"])
        self.assertIn("insufficient_historical_sessions", r["signals"]["fx"]["errors"])

    def test_unverified_source_is_blocked(self):
        data = {"metrics": {"margin": {"official_sources": {"margin": {
            "date": "2026-11-10", "value": 500000000000}}}}}
        r = evaluate(data, {"metrics": {"margin": {"quality": "blocked"}}},
                     {"observations": []})
        self.assertIn("quality_gate_not_passed", r["signals"]["margin"]["errors"])

    def test_twenty_session_change(self):
        p = [(f"2026-10-{i+1:02d}", 100.0) for i in range(20)]
        p.append(("2026-10-21", 110.0))
        self.assertAlmostEqual(transform("fx", p)[0][1], 10.0)

    def test_snapshot_replaces_same_date_history(self):
        data = {"metrics": {"fx": {"date": "2026-11-10", "value": 33}}}
        h = {"observations": [{"metric_id": "fx", "observation_date": "2026-11-10",
                               "value": 32}]}
        points, _ = extract(data, h, "fx")
        self.assertEqual(points, [("2026-11-10", 33.0)])

    def test_institutional_no_denominator_no_score(self):
        data = {"metrics": {"inst": {"official_sources": {
            "cash_inst": {"date": "2026-11-10", "categories": [
                {"name": "合計", "net_twd": -100}]},
            "futures": {"date": "2026-11-10", "foreign_tx_net_oi": -200}}}}}
        q = {"metrics": {"inst.cash_inst": {"quality": "pass"},
                         "inst.futures": {"quality": "pass"}}}
        r = evaluate(data, q, {"observations": []})
        for key in ("inst.cash_inst", "inst.futures"):
            self.assertIsNone(r["signals"][key]["score"])
            self.assertIn("normalization_denominator_unavailable", r["signals"][key]["errors"])


if __name__ == "__main__":
    unittest.main()
