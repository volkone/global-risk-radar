import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from global_history import parse_observations,at_or_before,reconstruct
class GlobalHistoryTests(unittest.TestCase):
 def test_future_and_stale_excluded(self):
  p=[{'date':'2023-01-01','value':1},{'date':'2024-01-01','value':2}]
  self.assertIsNone(at_or_before(p,'2023-03-01',7))
  self.assertEqual(at_or_before(p,'2023-01-02',7)['value'],1)
 def test_invalid_and_duplicate(self):
  for rows in [[{'date':'2024-01-01','value':'nan'}],[{'date':'2024-01-01','value':'1'}]*2]:
   with self.assertRaises(ValueError):parse_observations({'observations':rows})
 def test_missing_warmup_withholds(self):
  f={k:{'history':[{'date':'2024-01-02','value':1}]} for k in ('hy','ig','vix','nfci')}
  r=reconstruct(['2024-01-02'],f,[{'date':'2024-01-02','value':100}])[0]
  self.assertIsNone(r['score'])
 def test_existing_five_factor_weights_preserved(self):
  f={k:{'history':[{'date':'2024-01-02','value':v}]} for k,v in [('hy',4),('ig',1),('vix',25),('nfci',0)]}
  index=[{'date':'2022-12-30','value':90},{'date':'2023-12-01','value':100},{'date':'2024-01-02','value':90}]
  r=reconstruct(['2024-01-02'],f,index)[0]
  self.assertEqual(r['coverage'],.85);self.assertIsNotNone(r['score'])
  self.assertAlmostEqual(sum(c['effective_weight'] for c in r['components']),1)
  self.assertEqual(sum(c['eligible'] for c in r['components']),5)
