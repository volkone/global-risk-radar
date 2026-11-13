import datetime as dt
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from forward_health import due,health
class HealthTests(unittest.TestCase):
 def now(self,s):return dt.datetime.fromisoformat(s).replace(tzinfo=ZoneInfo('Asia/Taipei'))
 def test_capture_window(self):
  self.assertFalse(due(self.now('2026-11-13T19:59:00')))
  self.assertTrue(due(self.now('2026-11-13T20:00:00')))
  self.assertFalse(due(self.now('2026-11-14T21:00:00')))
 def test_stale_report_is_not_success(self):
  h=health(self.now('2026-11-13T21:00:00'),{'completed_at_utc':'2026-11-12T13:00:00+00:00'}, {},False)
  self.assertEqual(h['status'],'capture_due_no_current_attempt')
 def test_missing_snapshot_incomplete_even_successful_job(self):
  h=health(self.now('2026-11-13T21:00:00'),{'completed_at_utc':'2026-11-13T13:00:00+00:00'}, {},False)
  self.assertEqual(h['status'],'capture_incomplete')
 def test_validated_snapshot_present(self):
  self.assertEqual(health(self.now('2026-11-13T21:00:00'),{}, {},True)['status'],'captured')
