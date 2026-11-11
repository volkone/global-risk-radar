import unittest
from scripts.audit_calendar import evaluate

class CalendarGateTests(unittest.TestCase):
    def test_missing_and_unexpected_are_blocked(self):
        cal = [{"date": "2026-10-01", "is_trading_day": "1"}, {"date": "2026-10-02", "is_trading_day": "0"}]
        rows = [{"metric_id": "margin.margin", "date": "2026-10-01"}, {"metric_id": "inst.cash_inst", "date": "2026-10-02"}]
        result = evaluate(rows, cal, "2026-10-01", "2026-10-02")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["metrics"]["inst.cash_inst"]["missing_dates"], ["2026-10-01"])
        self.assertEqual(result["metrics"]["inst.cash_inst"]["unexpected_dates"], ["2026-10-02"])

    def test_complete_passes(self):
        cal = [{"date": "2026-10-01", "is_trading_day": "1"}]
        rows = [{"metric_id": metric, "date": "2026-10-01"} for metric in ("margin.margin", "inst.cash_inst")]
        self.assertEqual(evaluate(rows, cal, "2026-10-01", "2026-10-01")["status"], "pass")

    def test_missing_calendar_date_fails_closed(self):
        with self.assertRaises(ValueError):
            evaluate([], [], "2026-10-01", "2026-10-01")
