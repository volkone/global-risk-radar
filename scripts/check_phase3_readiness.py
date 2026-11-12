"""Independent Phase 3 readiness gate. Never self-authorizes formal backtests.

Runs only after the ALFRED point-in-time sample and sensitivity diagnostics.
This report is explicit about prior observed test results and release-timing
uncertainties; green GitHub Actions does not mean green model validity.
"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs/phase3_readiness_gate.json"

def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))

def main():
    original=read("docs/phase2_risk_research_backtest.json")
    joined=read("docs/phase2_join_audit.json")
    vintage=read("docs/phase3_vintage_audit.json")
    robust=read("docs/phase3_robustness_audit.json")
    evidence=read("docs/taifex_prebacktest_gate.json")
    panel=(ROOT/"storage/phase2_joined_panel.json").read_bytes()
    sha=hashlib.sha256(panel).hexdigest()
    assert joined["snapshot_sha256"]==sha==original["data_sha256"]==vintage["data_sha256"]==robust["data_sha256"]
    assert original["full_model_backtest_authorized"] is False
    assert joined["full_model_backtest_authorized"] is False
    assert vintage["full_model_backtest_authorized"] is False
    assert robust["full_model_backtest_authorized"] is False
    base=robust["variants"]["baseline_daily_fx_observation_date_only|train_70pct|signal_lag_0_tx_sessions"]
    stress=robust["variants"]["h10_fx_observation_at_least_10_calendar_days_old|train_70pct|signal_lag_2_tx_sessions"]
    summary={}
    for h in ("5d","20d"):
        x=base["horizons"][h]["summary"]
        y=stress["horizons"][h]["summary"]
        bootstrap=base["horizons"][h].get("approximate_block_bootstrap",{})
        summary[h]={
            "phase2_baseline":x,
            "fx_h10_and_two_tx_session_delay_stress":y,
            "alert_precision_change_stress_minus_baseline":(
                round(y["precision"]-x["precision"],4)
                if x["precision"] is not None and y["precision"] is not None else None),
            "approx_lift_interval":bootstrap.get("precision_minus_base_approx_95pct_interval"),
            "nonoverlap_offset_count":len(base["horizons"][h].get("nonoverlap_all_phase_offsets",[])),
            "holdout_quarters":base["horizons"][h].get("quarterly",{}),
        }
    blockers=[
        "all_718_fred_observations_not_point_in_time_vintage_certified",
        "intraday_publication_times_and_us_holidays_not_integrated",
        "phase2_holdout_previously_inspected_post_hoc_tests_not_independent_confirmation",
        "multi_regime_fresh_walk_forward_validation_not_completed",
        "full_taifex_calendar_primary_evidence_not_signed_off",
        "full_model_and_tradable_instrument_cost_contract_not_approved"
    ]
    if vintage["errors_count"] or vintage["status"]=="probe_incomplete_api_or_http":
        blockers.insert(0,"sampled_alfred_vintage_probe_incomplete")
    if vintage["violations_count"]>0:
        blockers.insert(0,"sampled_panel_uses_observations_unavailable_or_revised_asof")
    report={
        "status":"BLOCKED_RESEARCH_DIAGNOSTICS_COMPLETED",
        "phase":3,"data_sha256":sha,
        "source_sample_audit":{
            "status":vintage["status"],"sample_count":vintage["series_sample_size"],
            "violations":vintage["violations_count"],"errors":vintage["errors_count"],
            "per_factor_violations":vintage["by_factor_violations"]
        },
        "stability_summary":summary,
        "important_observation":"If as-of vintage checks find absent or revised panel observations, the phase-2 alert precision cannot be treated as point-in-time performance.",
        "blockers":blockers,
        "future_requirements":[
            "Create real publication-timestamp/calendar-aware PIT panel from audited ALFRED vintages or first-seen timestamps.",
            "Freeze research hypothesis, feature weights, threshold, horizon and execution restrictions BEFORE collecting a fresh holdout.",
            "Expand historical periods/rolling time splits or reserve genuinely unseen new data and quantify nonoverlap event count.",
            "Separately document TAIFEX market calendar evidence and TXF executable contract/roll/costs if studying trade PnL.",
            "Only a separate explicit quality gate can authorize production model validation and live threshold changes."
        ],
        "full_model_backtest_authorized":False,
        "live_threshold_changes_authorized":False
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PHASE3_GATE",report["status"],"source_violations",
          vintage["violations_count"],"source_errors",vintage["errors_count"],
          "blockers",len(blockers))

if __name__=="__main__":main()
