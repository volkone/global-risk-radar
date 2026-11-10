"""Strict official TWSE backfill parser tests (no live network)."""
import unittest
from scripts.backfill_twse import parse_margin, parse_cash, parse_roc_date


class BackfillTests(unittest.TestCase):
    def test_roc_date(self):
        self.assertEqual(parse_roc_date("115年10月05日"), "2026-10-05")

    def test_margin_thousands_to_twd_and_scope(self):
        obj = {"date": "115年10月05日", "tables": [{"fields": ["項目", "今日餘額"],
            "data": [["融資金額", "536,678,732"]]}]}
        row = parse_margin(obj, "2026-10")[0]
        self.assertEqual(row["value"], 536678732000)
        self.assertEqual(row["scope"], "TWSE上市市場")

    def test_reject_wrong_month(self):
        obj = {"date": "115年11月10日", "tables": []}
        with self.assertRaises(ValueError):
            parse_margin(obj, "2026-10")

    def test_cash_total_only(self):
        obj = {"date": "115年10月05日", "fields": ["單位名稱", "買賣差額"],
               "data": [["投信", "100"], ["合計", "-11,761,616,175"]]}
        row = parse_cash(obj, "2026-10")[0]
        self.assertEqual(row["value"], -11761616175)


if __name__ == "__main__":
    unittest.main()
