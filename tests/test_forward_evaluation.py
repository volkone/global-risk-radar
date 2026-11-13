import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluate_forward import metrics,nonoverlap,audit_outcome
from phase5_forward_capture import canonical,sha
class EvaluationTests(unittest.TestCase):
 def test_no_samples_null_ratios(self):
  self.assertIsNone(metrics([])['precision']);self.assertIsNone(metrics([])['recall'])
 def test_confusion_matrix(self):
  r=metrics([{'alert':a,'event':e} for a,e in [(True,True),(True,False),(False,True),(False,False)]])
  self.assertEqual(r['precision'],.5);self.assertEqual(r['recall'],.5);self.assertEqual(r['false_positive_rate'],.5)
 def test_nonoverlap_shared_boundary_excluded(self):
  rows=[dict(date='2026-01-01',end='2026-01-06'),dict(date='2026-01-06',end='2026-01-11'),dict(date='2026-01-07',end='2026-01-12')]
  self.assertEqual(nonoverlap(rows),[rows[0],rows[2]])
 def fixture(self):
  dates=[f'2026-11-{d:02}' for d in range(16,22)]
  snapshots={d:{'completed_at_utc':d+'T13:00:00+00:00','sources':{'taiex':{'value':[100 if i==0 else 96,dates[:i+1]]}}} for i,d in enumerate(dates)}
  pred={'forecast_session':dates[0],'created_at_utc':dates[0]+'T14:00:00+00:00','frozen_protocol_sha256':'p','score':70,'frozen_research_threshold':64}
  out={'forecast_session':dates[0],'horizon':5,'forecast_sha256':sha(canonical(pred)),'forward_snapshot_dates':dates[1:],'created_after_forward_window_completed_at_utc':dates[-1]+'T14:00:00+00:00','worst_forward_close_drawdown_pct':-4.,'terminal_forward_price_return_pct':-4.,'event_cutoff_pct':-3.,'event_occurred':True}
  return out,pred,snapshots,dates,'p'
 def test_verified_outcome(self):self.assertTrue(audit_outcome(*self.fixture())['event'])
 def test_changed_outcome_rejected(self):
  args=self.fixture();args[0]['event_occurred']=False
  with self.assertRaises(ValueError):audit_outcome(*args)
 def test_premature_outcome_rejected(self):
  args=self.fixture();args[0]['created_after_forward_window_completed_at_utc']='2026-11-17T14:00:00+00:00'
  with self.assertRaises(ValueError):audit_outcome(*args)
