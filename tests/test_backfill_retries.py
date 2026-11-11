"""Offline tests for bounded TWSE transient failures."""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from scripts import backfill_twse as module


class TestRequestRetries(unittest.TestCase):
    def test_transient_503_then_success(self):
        failure = urllib.error.HTTPError("https://example.invalid", 503, "busy", {}, None)
        good = io.BytesIO(json.dumps({"date": "2026-10-01"}).encode())
        with patch.object(module.urllib.request, "urlopen", side_effect=[failure, good]) as fetch, \
             patch.object(module.time, "sleep"):
            self.assertEqual(module.request_json("https://example.invalid")["date"], "2026-10-01")
            self.assertEqual(fetch.call_count, 2)

    def test_404_not_retried(self):
        failure = urllib.error.HTTPError("https://example.invalid", 404, "missing", {}, None)
        with patch.object(module.urllib.request, "urlopen", side_effect=failure) as fetch, \
             patch.object(module.time, "sleep"):
            with self.assertRaises(urllib.error.HTTPError):
                module.request_json("https://example.invalid")
            self.assertEqual(fetch.call_count, 1)

    def test_429_stops_after_three_attempts(self):
        failure = urllib.error.HTTPError("https://example.invalid", 429, "limited", {}, None)
        with patch.object(module.urllib.request, "urlopen", side_effect=failure) as fetch, \
             patch.object(module.time, "sleep"):
            with self.assertRaises(urllib.error.HTTPError):
                module.request_json("https://example.invalid")
            self.assertEqual(fetch.call_count, 3)


if __name__ == "__main__":
    unittest.main()
