import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_pit_full_replay import replay_audit

class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.v={'series':{'vix':{'bootstrap_date':'2024-01-01','bootstrap':[{'date':'2024-01-01','value':10}], 'changes':[{'observed_date':'2024-01-01','vintage_date':'2024-01-03','value':20},{'observed_date':'2024-01-10','vintage_date':'2024-01-02','value':99}]}}}
        self.p={'rows':[{'date':'2024-01-03','us_previous_dated_observations':{'vix':{'asof_us_calendar_date':'2024-01-02','decision_at_taipei':'2024-01-03T16:00:00+08:00','observed_date':'2024-01-01','value':10,'time_gate_passed':True}}}]}
    def test_later_revision_and_future_observation_excluded(self):
        r=replay_audit(self.p,self.v);self.assertEqual(r['mismatch_count'],0)
        self.assertFalse(r['actual_publication_time_certification'])
    def test_corrupted_value_detected(self):
        self.p['rows'][0]['us_previous_dated_observations']['vix']['value']=20
        self.assertEqual(replay_audit(self.p,self.v)['mismatch_count'],1)
    def test_missing_vintage_is_not_backfilled(self):
        self.v['series']['vix']['bootstrap_date']='2024-01-05'
        o=self.p['rows'][0]['us_previous_dated_observations']['vix'];o.update(value=None,observed_date=None,time_gate_passed=False)
        self.assertEqual(replay_audit(self.p,self.v)['per_factor']['vix']['expected_missing'],1)
    def test_deleted_value_not_used(self):
        self.v['series']['vix']['changes'].append({'observed_date':'2024-01-01','vintage_date':'2024-01-02','value':None})
        self.assertEqual(replay_audit(self.p,self.v)['mismatch_count'],1)
    def test_duplicate_session_rejected(self):
        self.p['rows'].append(copy.deepcopy(self.p['rows'][0]))
        with self.assertRaises(ValueError):replay_audit(self.p,self.v)
