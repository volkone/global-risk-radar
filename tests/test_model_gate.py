import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from model_gate import evaluate_gate, EVIDENCE
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
            obj.update(output_sha256='panel',source_panel_sha256='panel',frozen_protocol_sha256='protocol',matured_nonoverlapping_events={'5d':30,'20d':30})
            raw=json.dumps(obj).encode();(self.root/path).write_bytes(raw);hashes[path]=hashlib.sha256(raw).hexdigest()
        (self.root/'docs/production_model_authorization.json').write_text(json.dumps(dict(production_scoring_authorized=True,source_panel_sha256='panel',frozen_protocol_sha256='protocol',evidence_sha256=hashes)))
    def test_missing_evidence_blocks(self):
        self.assertEqual(self.evaluate()['status'],'BLOCKED')
    def test_all_verified_evidence_allows_score(self):
        self.certify_fixture();self.assertEqual(self.evaluate()['status'],'PASS')
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
