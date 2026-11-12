"""Critical integration checks; never modify the frozen forward protocol."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dashboard_scores import clean_rows, components, reconstruct, PANEL
from phase5_forward_ledger import KEYS, frozen_distributions, score
from phase5_forward_capture import verify_frozen
from backtest_phase2_research import prepare

class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=json.loads(PANEL.read_text())['rows']
        cls.distributions=frozen_distributions()

    def test_frozen_protocol_integrity(self):
        self.assertFalse(verify_frozen()['formal_full_model_backtest_authorized'])

    def test_history_lag_and_frozen_score_agree(self):
        records=reconstruct(self.rows,self.distributions,2)
        feats=prepare(clean_rows(self.rows))
        self.assertEqual(len(records),718)
        self.assertTrue(all(r['score'] is None for r in records[:22]))
        self.assertEqual(records[-1]['signal_date'],self.rows[-3]['date'])
        self.assertEqual(records[-1]['score'],score(feats[-3],self.distributions))
        self.assertAlmostEqual(sum(c['contribution'] or 0 for c in records[-1]['components']),records[-1]['score'],places=4)

    def test_missing_factors_withhold_score(self):
        rows=copy.deepcopy(self.rows[:30])
        for r in rows:
            r['margin_balance_twd']=None
            r['cash_institutional_net_twd']=None
            r['tx_oi_net_contracts']=None
        self.assertTrue(all(r['score'] is None for r in reconstruct(rows,self.distributions,2)))

    def test_future_stale_and_failed_clock_are_excluded(self):
        row=copy.deepcopy(self.rows[-1])
        row['us_previous_dated_observations']['fx']['observed_date']='2099-01-01'
        row['us_previous_dated_observations']['vix']['stale']=True
        row['us_previous_dated_observations']['hy']['time_gate_passed']=False
        fixed=clean_rows([row])[0]
        self.assertTrue(all(fixed['us_previous_dated_observations'][k]['value'] is None for k in ('fx','vix','hy')))
        self.assertIsNotNone(row['us_previous_dated_observations']['fx']['value'])

    def test_tx_arithmetic_and_nonfinite_inputs(self):
        row=copy.deepcopy(self.rows[-1]);row['tx_oi_net_contracts']=999
        row['margin_balance_twd']=math.inf
        fixed=clean_rows([row])[0]
        self.assertIsNone(fixed['tx_oi_net_contracts']);self.assertIsNone(fixed['margin_balance_twd'])

    def test_no_duplicate_sessions(self):
        with self.assertRaises(ValueError):clean_rows([self.rows[0],self.rows[0]])

    def test_missing_not_zero_risk(self):
        cs=components(None,self.distributions)
        self.assertTrue(all(c['signal'] is None and c['contribution'] is None for c in cs))

    def test_outcomes_never_affect_historical_scores(self):
        rows=copy.deepcopy(self.rows[:40])
        before=reconstruct(rows,self.distributions,2)
        for r in rows:r['taiex_price_index_close']=999999
        self.assertEqual(before,reconstruct(rows,self.distributions,2))

if __name__=='__main__':unittest.main()
