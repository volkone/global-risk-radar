import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from model_gate import evaluate_gate, EVIDENCE, FACTORS, PANEL as PANEL_KEY, VINTAGES, SCOPE_EVIDENCE
from dashboard_scores import calibration_report, reconstruct, PANEL
from phase5_forward_capture import verify_frozen
from phase5_forward_ledger import frozen_distributions

class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'docs').mkdir()
        self.pred={'status':'prospective_research','date':'2026-11-13','score':50}
    def evaluate(self,pred=None):
        return evaluate_gate(self.root,'panel','protocol',self.pred if pred is None else pred,'2026-11-13')
    def certify_fixture(self):
        hashes={}
        for key,(path,fields) in EVIDENCE.items():
            obj={f:True for f in fields}
            obj.update(output_sha256='panel',source_panel_sha256='panel',frozen_protocol_sha256='protocol')
            if key == 'publication':
                obj.update(source_vintage_sha256='vintage', series={
                    k: dict(differences_after_exclusion=0, panel_value_differences=[],
                            panel_values_checked=718, panel_missing_values=0) for k in FACTORS
                })
            if key == 'validation':
                obj.update(validation_mode='historical_expanding_window', excluded_dates=['2023-11-13'],
                           horizons={h: {'metrics': dict(n=30,alert_n=10,event_n=12,alert_event_n=6)}
                                     for h in ('5d','20d')})
            raw=json.dumps(obj).encode();(self.root/path).write_bytes(raw);hashes[path]=hashlib.sha256(raw).hexdigest()
        scope=json.dumps(dict(panel_sha256='panel',raw_vintages_sha256='vintage',sessions=718,
                              replay_positions=4308,replay_mismatches_after_exclusion=0)).encode()
        (self.root/SCOPE_EVIDENCE).write_bytes(scope)
        hashes[SCOPE_EVIDENCE]=hashlib.sha256(scope).hexdigest()
        (self.root/'docs/pit_full_replay_audit.json').write_text(json.dumps(dict(
            status='internal_replay_pass',sessions=718,checks=4308,mismatch_count=0,
            input_sha256={PANEL_KEY:'panel',VINTAGES:'vintage'},
            per_factor={k:dict(matched_values=718,expected_missing=0) for k in FACTORS})))
        (self.root/'docs/production_model_authorization.json').write_text(json.dumps(dict(production_scoring_authorized=True,source_panel_sha256='panel',frozen_protocol_sha256='protocol',evidence_sha256=hashes)))
    def test_missing_evidence_blocks(self):
        self.assertEqual(self.evaluate()['status'],'BLOCKED')
    def test_all_verified_evidence_allows_score(self):
        self.certify_fixture();self.assertEqual(self.evaluate()['status'],'PASS')
    def test_changed_replay_input_blocks_numeric_certification(self):
        self.certify_fixture()
        path=self.root/'docs/pit_full_replay_audit.json'
        report=json.loads(path.read_text())
        report['input_sha256'][VINTAGES]='different'
        path.write_text(json.dumps(report))
        self.assertFalse(self.evaluate()['checks'][0]['passed'])

    def test_historical_metrics_must_exceed_base_rate(self):
        self.certify_fixture()
        path=self.root/EVIDENCE['validation'][0]
        report=json.loads(path.read_text())
        report['horizons']['20d']['metrics']['alert_event_n']=4
        path.write_text(json.dumps(report))
        self.assertFalse(self.evaluate()['checks'][2]['passed'])

    def test_changed_evidence_requires_new_authorization(self):
        self.certify_fixture()
        p=self.root/EVIDENCE['calendar'][0];p.write_text(p.read_text()+' ')
        self.assertEqual(self.evaluate()['status'],'BLOCKED')
    def test_old_or_reconstructed_score_cannot_be_promoted(self):
        self.certify_fixture()
        for changes in ({'date':'2026-11-12'},{'status':'historical_reconstruction'},{'score':float('nan')},{'score':True}):
            self.assertEqual(self.evaluate(dict(self.pred,**changes))['status'],'BLOCKED')
    def test_research_calibration_matches_dashboard(self):
        panel=json.loads(PANEL.read_text());frozen=verify_frozen()
        rows=reconstruct(panel['rows'],frozen_distributions(),2)
        report=calibration_report(panel,'test',frozen,rows)
        self.assertEqual(report['historical_sessions'],718)
        self.assertEqual(report['valid_historical_scores'],696)
        self.assertEqual(report['latest_research'],rows[-1])
        self.assertTrue(all(v['transformed_observations']>600 for v in report['signals'].values()))
