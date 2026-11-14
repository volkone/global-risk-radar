"""Read-only P0/P1/P2 readiness diagnostics; never grants model authorization."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(p):
    f=ROOT/p
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
def evaluate():
    scores=load("docs/scores.json") or {}
    quality=load("docs/quality.json") or {}
    source=load("docs/taifex_source_verification.json") or {}
    coverage=load("docs/taifex_coverage_audit.json") or {}
    calendar=load("docs/taifex_prebacktest_gate.json") or {}
    timing=load("docs/phase4_publication_timing_audit.json") or {}
    replay=load("docs/pit_full_replay_audit.json") or {}
    official=load("docs/official_source_evidence_2026_11_14.json") or {}
    g=scores.get("global",{})
    missing=[{"metric":x.get("metric"),"weight":x.get("weight"),"reason":x.get("reason"),
              "quality":(quality.get("metrics",{}).get(x.get("metric")) or {}).get("quality"),
              "quality_errors":(quality.get("metrics",{}).get(x.get("metric")) or {}).get("errors",[])}
             for x in g.get("components",[]) if not x.get("eligible")]
    p1={"source_records_verified":source.get("counts",{}).get("pass"),
        "source_total":source.get("total_records"),
        "source_verification_pass":source.get("status")=="pass" and source.get("counts",{}).get("pass")==source.get("total_records"),
        "twse_join_audit_pass":coverage.get("status")=="pass",
        "calendar_crosscheck_pass":coverage.get("futures_calendar_independently_verified") is True,
        "independent_taifex_calendar_certified":calendar.get("independent_taifex_calendar_verified") is True,
        "full_notice_sweep_verified":calendar.get("full_notice_sweep_verified") is True,
        "primary_evidence_complete":calendar.get("primary_evidence_complete") is True}
    required_p1=("source_verification_pass","twse_join_audit_pass","calendar_crosscheck_pass","independent_taifex_calendar_certified","full_notice_sweep_verified","primary_evidence_complete")
    p1["complete"]=all(p1[k] is True for k in required_p1)
    p1["unmet_checks"]=[k for k in required_p1 if p1[k] is not True]
    p2={"conservative_time_gate_panel_built":timing.get("status")=="conservative_time_gate_research_panel_built",
        "actual_publication_timestamps_verified":timing.get("actual_publication_timestamps_verified_for_all_718") is True,
        "revisions_independently_verified":timing.get("data_revisions_independently_verified_for_all_718") is True,
        "internal_replay_pass":replay.get("status")=="internal_replay_pass",
        "independent_source_query_validation":replay.get("independent_source_query_validation") is True}
    p2["complete"]=all(p2.values())
    p2["unmet_checks"]=[k for k,v in p2.items() if k!="complete" and v is not True]
    return {"schema_version":1,"purpose":"P0/P1/P2 independent diagnostics; not production approval",
            "p0":{"global_coverage":g.get("coverage"),"minimum_coverage":g.get("min_coverage"),
                  "score":g.get("score"),"missing_components":missing,
                  "complete":g.get("status")=="provisional" and g.get("score") is not None},
            "p1":p1,"p2":p2,"evidence_gaps":{
                "p0":[{"metric":x["metric"],"issue":x["quality_errors"],"required_evidence":"fresh source observation" if x["metric"]=="nfci" else "verified market-breadth source and calibrated signal"} for x in missing],
                "p1":[{"check":x,"evidence_file":"docs/taifex_prebacktest_gate.json"} for x in p1["unmet_checks"]],
                "p2":[{"check":x,"evidence_file":"docs/phase4_publication_timing_audit.json" if x!="independent_source_query_validation" else "docs/pit_full_replay_audit.json"} for x in p2["unmet_checks"]]},
            "official_primary_source_index":{"path":"docs/official_source_evidence_2026_11_14.json","available":bool(official),"taifex_rule_confirmed":official.get("taifex",{}).get("contract_specification",{}).get("status")=="official_rule_confirmed","special_closure_notice_confirmed":official.get("taifex",{}).get("special_closure_example",{}).get("status")=="official_notice_confirmed","alfred_api_documentation_available":bool(official.get("alfred",{}).get("vintage_dates_api"))},
            "formal_backtest_authorized":False,
            "notes":["Crosschecking TWSE sessions is not the same as independently certifying TAIFEX notices.",
                     "Conservative release-time proxies and internal vintage replay do not prove actual publication timestamps.",
                     "No missing or paid metric is imputed."]}
def main():
    report=evaluate()
    out=ROOT/"docs/p012_readiness.json"
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("P0/P1/P2:",{k:report[k]["complete"] for k in ("p0","p1","p2")})
if __name__=="__main__":main()
