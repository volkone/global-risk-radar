import json
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import taiwan_crash_watch as watch
from crash_watch_validation import evaluate
from quality import evaluate as quality


def timestamp(value):
    return datetime.fromisoformat(value + "+08:00")


class CrashWatchTests(unittest.TestCase):
    def test_us_session_spring_dst_and_holiday(self):
        self.assertEqual(watch.expected_us_session(timestamp("2026-11-20T08:30")), "2026-11-19")
        self.assertEqual(watch.expected_us_session(timestamp("2026-11-27T08:30")), "2026-11-25")
        self.assertEqual(watch.expected_us_session(timestamp("2026-11-20T04:59")), "2026-11-18")
        self.assertEqual(watch.expected_us_session(timestamp("2026-07-17T04:16")), "2026-07-16")

    def test_rule_boundaries(self):
        features = {"prior_day_pct": -1, "drawdown_20_pct": watch.pct(92, 100)}
        self.assertTrue(watch.warning(features, -2, -2))
        self.assertFalse(watch.warning(features, -2, -1.99))

    def test_premarket_uses_previous_sessions_and_keeps_successful_capture(self):
        day = date(2026, 11, 20)
        now = timestamp("2026-11-20T08:29")
        opens = {day - timedelta(days=i): True for i in range(21)}
        closes = {d.isoformat(): 100 for d in opens}
        closes["2026-11-19"] = 96
        closes["2026-11-20"] = 50
        us = [datetime.combine(date(2026, 11, d), watch.OPEN, watch.NEW_YORK).timestamp()
              for d in (18, 19, 20)]

        def quote(source):
            symbol = "TSM" if "/TSM?" in source else "^SOX"
            return json.dumps({"chart": {"result": [{
                "meta": {"symbol": symbol, "exchangeTimezoneName": "America/New_York"},
                "timestamp": us, "indicators": {"quote": [{"close": [100, 97, 1]}]}
            }]}})

        signal = watch.premarket(now, opens, closes, quote, lambda: now)
        self.assertEqual(signal["status"], "alert")
        self.assertEqual(signal["us_date"], "2026-11-19")
        self.assertEqual(signal["tsm"]["value"], -3)
        self.assertEqual(signal["taiwan"]["prior_day_pct"], -4)
        late = watch.premarket(now, opens, closes, quote, lambda: timestamp("2026-11-20T09:00"))
        self.assertEqual(late["status"], "unavailable")

        metrics = {"inst": {}, "margin": {}}
        after = timestamp("2026-11-20T13:35")
        called = []

        def fail(source):
            called.append(source)
            raise OSError("test")

        out = watch.snapshot(metrics, {"premarket": signal}, closes, fail, after, opens,
                             utcnow=lambda: after)
        self.assertEqual(out["premarket"], signal)
        self.assertFalse(any("finance.yahoo.com" in item for item in called))

    def test_publication_date_and_source_for_official_close(self):
        near = timestamp("2026-11-20T08:30")
        raw = {"stat": "OK", "fields": ["日期", "發行量加權股價指數", "成交股數", "成交金額"],
               "data": [["115/11/19", "38,426.89", "9", "50"], ["115/11/20", "36,033.29", "9", "50"]]}
        metric = {}
        watch.publish_official_close(metric, {"value": 1, "date": "2026-11-20"},
                                     lambda _: json.dumps(raw), near, watch.calendar())
        self.assertEqual((metric["provider"], metric["value"], metric["date"]),
                         ("TWSE", 38426.89, "2026-11-19"))
        self.assertEqual(quality({"metrics": {"taiex": metric}}, {}, date(2026, 11, 20))["metrics"]
                         ["taiex"]["quality"], "pass")

    def test_mis_uses_last_regular_trade_not_unmatched_auction(self):
        now = timestamp("2026-11-20T10:31")
        rows = [
            {"ex": "tse", "c": "1111", "d": "20261120", "t": "10:30:00",
             "z": "-", "trade": {"t": "10:29:45", "z": "90"}, "y": "100", "w": "90"},
            {"ex": "tse", "c": "2222", "d": "20261120", "t": "10:30:00",
             "z": "101", "y": "100", "w": "90"},
            {"ex": "tse", "c": "3333", "d": "20261119", "t": "13:30:00",
             "z": "90", "y": "100", "w": "90"},
        ]
        good = watch.intraday_counts(rows, "tse", {"1111", "2222"}, now)
        self.assertEqual((good["down_pct"], good["limit_down_pct"], good["coverage_pct"]), (50, 50, 100))
        incomplete = watch.intraday_counts(rows, "tse", {"1111", "2222", "3333"}, now)
        self.assertIsNone(incomplete["down_pct"])
        self.assertIsNone(incomplete["limit_down_pct"])

    def test_venue_and_time_checks_for_gap_and_relative_index(self):
        now = timestamp("2026-11-20T10:30")
        raw = {"rtcode": "0000", "msgArray": [
            {"ex": "tse", "c": "t00", "d": "20261120", "t": "10:29:50", "z": 95, "o": 98, "y": 100},
            {"ex": "otc", "c": "o00", "d": "20261120", "t": "10:29:55", "z": 184, "o": 194, "y": 200},
        ]}
        actual = watch.indices(raw, now, 100)
        self.assertEqual((actual["gap_pct"], actual["relative_pp"]), (-2, -3))
        with self.assertRaisesRegex(ValueError, "out of phase"):
            watch.indices(raw, timestamp("2026-11-20T11:10"), 100)

    def test_margin_requires_exact_session_dates_and_cash_is_not_mixed(self):
        dates = [f"2026-11-{d:02}" for d in (13, 16, 17, 18, 19, 20)]
        margin = {"status": "ok", "provider": "TWSE", "date": dates[-1], "value": 90_000,
                  "unit": "TWD", "scope": "TWSE上市市場", "source_url": "https://www.twse.com.tw"}
        metrics = {"inst": {}, "margin": {"official_sources": {"margin": margin}}}

        def dated_margin(source):
            # The D-5 endpoint returned the wrong day in the same month.
            return json.dumps({"date": "20261119", "tables": [
                {"fields": ["項目", "今日餘額"], "data": [["融資金額(仟元)", "100"]]},
            ]})

        result = watch.leverage(metrics, dates, dated_margin, {})
        self.assertEqual(result["one_day_pct"], -10)
        self.assertIsNone(result["five_day_pct"])
        self.assertIsNone(result["cash"])

    def test_historical_rolling_windows_are_grouped_for_episode_counts(self):
        sample = [
            dict(i=0, event=True, rule=True, lead_sessions=2),
            dict(i=1, event=True, rule=True, lead_sessions=1),
            dict(i=6, event=True, rule=False, lead_sessions=4),
            dict(i=9, event=False, rule=True, lead_sessions=None),
        ]
        result = evaluate(sample, months=2, horizon=5, key="rule")
        self.assertEqual((result["hits"], result["misses"], result["false_per_month"]), (2, 1, .5))
        self.assertEqual((result["episodes_hit"], result["episodes"]), (1, 2))


if __name__ == "__main__":
    unittest.main()
