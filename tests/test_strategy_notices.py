import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import strategy_notices as notices
from scripts import collect


class StrategyNoticeTests(unittest.TestCase):
    now = dt.datetime(2026, 11, 16, 6, tzinfo=dt.timezone.utc)

    def close(self, value, **overrides):
        return {"value": value, "date": "2026-11-16", "provider": "TWSE",
                "status": "ok", "unit": "points", "checked_at": self.now.isoformat(), **overrides}

    def test_inclusive_threshold_and_gap(self):
        state = notices.evaluate(self.close(40689.90), {}, self.now)
        self.assertEqual(state["current_stage"], 2)
        self.assertEqual(state["pending_stage"], 2)
        self.assertIn("40,689.90", notices.message(state))
        self.assertEqual(state["planned_total_twd"], 8000000)

    def test_retry_after_failure_and_no_duplicate_after_confirmation(self):
        record = self.close(42000)
        first = notices.evaluate(record, {}, self.now)
        retry = notices.evaluate(record, first, self.now)
        self.assertEqual(notices.message(first), notices.message(retry))
        retry["pending_stage"] = None
        self.assertIsNone(notices.message(notices.evaluate(record, retry, self.now)))

    def test_stale_source_and_rebound_cancel_or_suppress_notice(self):
        active = notices.evaluate(self.close(40000), {}, self.now)
        for record in (self.close(38500, cache_status="stale"), self.close(38500, date="2026-11-13"),
                       self.close(38500, provider="Yahoo"), self.close(38500, checked_at="2026-11-16T05:29:00+00:00"), self.close(float("nan"))):
            state = notices.evaluate(record, active, self.now)
            self.assertIsNone(state["current_stage"])
            self.assertIsNone(notices.message(state))
        rebound = notices.evaluate(self.close(44000), active, self.now)
        self.assertIsNone(rebound["pending_stage"])
        self.assertEqual(notices.evaluate(self.close(40000), rebound, self.now)["pending_stage"], 2)

    def test_no_intraday_notice(self):
        before_close = self.now.replace(hour=5, minute=29)
        self.assertIsNone(notices.message(notices.evaluate(self.close(40000), {}, before_close)))


    def test_telegram_requires_api_acknowledgment(self):
        for body, expected in ((b'{"ok":true}', True), (b'{"ok":false}', False)):
            response = io.BytesIO(body)
            response.status = 200
            with patch.dict(collect.os.environ, {"TELEGRAM_BOT_TOKEN": "mock", "TELEGRAM_CHAT_ID": "mock"}), \
                    patch.object(collect.urllib.request, "urlopen", return_value=response):
                self.assertEqual(collect.telegram("research notice"), expected)
