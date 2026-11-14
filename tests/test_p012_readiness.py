"""Unit tests for conservative P0/P1/P2 gate semantics."""
import unittest
from unittest.mock import patch
from scripts import audit_p012_readiness as audit

class ReadinessTests(unittest.TestCase):
    def test_missing_evidence_never_authorizes(self):
        with patch.object(audit, "load", return_value=None):
            report=audit.evaluate()
        self.assertFalse(report["p0"]["complete"])
        self.assertFalse(report["p1"]["complete"])
        self.assertFalse(report["p2"]["complete"])
        self.assertFalse(report["formal_backtest_authorized"])
        self.assertIn("independent_taifex_calendar_certified",report["p1"]["unmet_checks"])
    def test_718_source_pass_is_not_calendar_certification(self):
        data={
          "docs/taifex_source_verification.json":{"status":"pass","total_records":718,"counts":{"pass":718}},
          "docs/taifex_coverage_audit.json":{"status":"pass","futures_calendar_independently_verified":True},
          "docs/taifex_prebacktest_gate.json":{"independent_taifex_calendar_verified":False,
              "full_notice_sweep_verified":False,"primary_evidence_complete":False},
        }
        with patch.object(audit,"load",side_effect=lambda p:data.get(p)):
            report=audit.evaluate()
        self.assertTrue(report["p1"]["source_verification_pass"])
        self.assertFalse(report["p1"]["complete"])
    def test_conservative_timing_is_not_publication_proof(self):
        data={"docs/phase4_publication_timing_audit.json":{"status":"conservative_time_gate_research_panel_built",
              "actual_publication_timestamps_verified_for_all_718":False,
              "data_revisions_independently_verified_for_all_718":False},
              "docs/pit_full_replay_audit.json":{"status":"internal_replay_pass",
              "independent_source_query_validation":False}}
        with patch.object(audit,"load",side_effect=lambda p:data.get(p)):
            report=audit.evaluate()
        self.assertTrue(report["p2"]["internal_replay_pass"])
        self.assertFalse(report["p2"]["complete"])

if __name__=="__main__":unittest.main()
