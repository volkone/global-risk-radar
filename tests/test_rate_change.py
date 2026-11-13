import datetime as dt
import unittest
from scripts.scores import rate_change_signal
class RateChangeTests(unittest.TestCase):
 def metric(self,n=90):
  rows=[{'date':(dt.date(2024,1,1)+dt.timedelta(days=i)).isoformat(),'value':4+i*i/10000} for i in range(n)]
  return {'date':rows[-1]['date'],'value':rows[-1]['value'],'history':rows}
 def test_prior_only_and_window_invariant(self):
  m=self.metric();self.assertEqual(rate_change_signal(m),100)
  m['history'].append({'date':'2025-01-01','value':999})
  self.assertEqual(rate_change_signal(m),100)
  m['history']=m['history'][9:];self.assertEqual(rate_change_signal(m),100)
 def test_insufficient_and_latest_mismatch(self):
  self.assertIsNone(rate_change_signal(self.metric(80)))
  m=self.metric();m['value']=999;self.assertIsNone(rate_change_signal(m))
 def test_duplicates_rejected(self):
  m=self.metric();m['history'].append(m['history'][-1])
  with self.assertRaises(ValueError):rate_change_signal(m)
 def test_flat_ties(self):
  m=self.metric()
  for r in m['history']:r['value']=4
  m['value']=4;self.assertEqual(rate_change_signal(m),50)
