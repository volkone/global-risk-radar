import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import taiwan_credit as credit
import taiwan_market_breadth as breadth
from validate_market_breadth import rule_at


class CreditTests(unittest.TestCase):
    def setUp(self):
        self.calendar = {
            date.fromisoformat(day): day != "2026-11-21"
            for day in ("2026-11-19", "2026-11-20", "2026-11-21", "2026-11-23")
        }
        self.calendar[date(2026, 11, 22)] = False
        self.row = {"date": "20261120", "keepRate": 151.78, "belowAccNum": 6462,
                    "callAccNum": 6186, "callAmt": 6463856762, "exeAccNum": 632, "exeAmt": 1495357574}

    def test_uses_below_130_count_and_aligns_next_session(self):
        result = credit.parse_report({"stat": "OK", "data": [self.row]}, "2026-11-20",
                                     self.calendar, datetime.now(timezone.utc))
        record = credit.summarize(result, "2026-11-20", self.calendar, "ok")
        self.assertEqual(record["maintenance_pct"], 151.78)
        self.assertEqual(record["accounts_below_130"], 6462)
        self.assertEqual(record["disposal_date"], "2026-11-23")
        self.assertEqual(record["disposal_accounts"], 632)
        self.assertNotIn("change_1d_pp", record)

    def test_future_or_malformed_entries_are_rejected(self):
        for updates in ({"date": "20261121"}, {"keepRate": True}, {"exeAmt": -1}):
            with self.assertRaises(ValueError):
                credit.parse_report({"stat": "OK", "data": [dict(self.row, **updates)]}, "2026-11-20",
                                    self.calendar, datetime.now(timezone.utc))

    def test_previous_official_date_is_shown_when_current_report_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(credit, "HISTORY", Path(tmp) / "archive.json"):
                metric = {}
                reports = lambda _: json.dumps({"stat": "OK", "data": [self.row]})
                result = credit.refresh(metric, reports, "2026-11-23", self.calendar)
                self.assertEqual(result["status"], "pending")
                self.assertEqual(result["expected_date"], "2026-11-23")
                self.assertEqual(metric["date"], "2026-11-20")
                self.assertEqual(metric["scope"], credit.SCOPE)
                self.assertEqual(metric["value"], 151.78)

    def test_history_keeps_observation_time_until_source_facts_change(self):
        prior = {"maintenance_pct": 145, "accounts_below_130": 61, "margin_call_twd": 51,
                 "disposal_accounts": 23, "disposal_twd": 44, "observed_at": "prior"}
        day = "2026-11-20"
        seen_again = dict(prior, observed_at="later")
        self.assertEqual(credit.merge_reports({day: prior}, {day: seen_again})[day], prior)
        revision = dict(seen_again, maintenance_pct=146)
        self.assertEqual(credit.merge_reports({day: prior}, {day: revision})[day], revision)


class BreadthTests(unittest.TestCase):
    def test_ordinary_share_parsing_rejects_wrong_date_and_etfs(self):
        expr = {"stat": "OK", "date": "20261120", "tables": [{
            "fields": ["證券代號", "收盤價"],
            "data": [[str(code), "1,200.50"] for code in range(1100, 1650)]
                    + [["0050", "200.00"], ["9105", "129.00"], ["1001", "--"]],
        }]}
        actual = breadth.parse_daily_closes(expr, "tse", "2026-11-20")
        self.assertEqual(len(actual), 550)
        self.assertEqual(actual["1100"], 120050)
        for code in ("0050", "9105", "1001"):
            self.assertNotIn(code, actual)
        with self.assertRaises(ValueError):
            breadth.parse_daily_closes(expr, "tse", "2026-11-19")

    def test_moving_average_requires_contiguous_exchange_sessions(self):
        days = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(60)]
        repo = {day: {"prices": {"1101": 100, "1102": 100, "1103": 100}} for day in days}
        repo[days[-1]]["prices"] = {"1101": 200, "1102": 100, "1103": 110, "1104": 130}
        del repo[days[0]]["prices"]["1103"]
        result = breadth.breadth_at(repo, days)
        self.assertEqual(result["ma20"], {"above": 2, "eligible": 3, "pct": 66.6667})
        self.assertEqual(result["ma60"], {"above": 1, "eligible": 2, "pct": 50.0})
        del repo[days[-9]]
        self.assertNotIn("ma20", breadth.breadth_at(repo, days))

    def test_premarket_breadth_rule_never_reads_candidate_date(self):
        days = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(61)]
        tw = dict.fromkeys(days, 100)
        values = {day: (78 - i * 3, 100) for i, day in enumerate(days[-7:-1])}
        self.assertTrue(rule_at(tw, days, 60, values))
        tw[days[-1]] = 10
        values[days[-1]] = (100, 10)
        self.assertTrue(rule_at(tw, days, 60, values))


if __name__ == "__main__":
    unittest.main()
