"""Freeze a prospectively testable, RESEARCH-ONLY six-factor warning experiment.

The original 2025-12 to 2026-10 holdout has been seen repeatedly and is
no longer an untouched confirmation sample. No historical 3-year observations
can be re-designated as new data. Pre-register only dates >= 2026-11-13.
No data fetch, no alert issuance, no PnL or live threshold changes.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

from backtest_phase2_research import prepare
from audit_phase3_robustness import scorer

ROOT=Path(__file__).resolve().parents[1]
PANEL=ROOT/"storage/phase4_publication_aware_panel.json"
SOURCE_AUDIT=ROOT/"docs/phase4_stratified_asof_audit.json"
TIME_AUDIT=ROOT/"docs/phase4_publication_timing_audit.json"
OUT=ROOT/"docs/phase4_frozen_prospective_protocol.json"
FEATURES=(
    "foreign_tx_short_pressure",
    "margin_deleveraging_20d",
    "institutional_net_selling_5d",
    "twd_depreciation_20d",
    "hy_oas_widening_20d",
    "prior_us_vix_level",
)
FIRST_UNSEEN_DATE="2026-11-13"
FREEZE_DECLARATION_DATE="2026-11-12"
LAG=2
PERCENTILE=0.8
EVENTS={"5d":-3.0,"20d":-5.0}

def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()

def main():
    raw=PANEL.read_bytes()
    p=json.loads(raw)
    ta=json.loads(TIME_AUDIT.read_text(encoding="utf-8"))
    sa=json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))
    assert ta["output_sha256"]==hashlib.sha256(raw).hexdigest()
    assert sa["status"]=="stratified_asof_sample_pass"
    assert sa["pit_panel_sha256"]==p["source_pit_snapshot_sha256"]
    assert not p["formal_backtest_authorized"] and not ta["source_clock_gates_fully_certified"]
    rows=p["rows"]
    assert len(rows)==718 and rows[-1]["date"]<FIRST_UNSEEN_DATE
    prepared=prepare(rows)
    fitted=scorer(prepared,len(rows),LAG)
    if fitted is None:
        raise RuntimeError("too_few_pre_forward_training_samples")
    _,threshold,count=fitted
    assert count>=450
    report={
        "status":"preregistered_research_protocol_awaiting_genuinely_unseen_future_market_data",
        "freeze_declaration_date_taipei":FREEZE_DECLARATION_DATE,
        "initial_candidate_data_cutoff":rows[-1]["date"],
        "first_prospective_session_not_used_in_research":FIRST_UNSEEN_DATE,
        "past_data_note":"All 2023-11-13 to 2026-10-30 records have been available to researchers; neither 70/30 holdout nor alternative chronological splits are untouched.",
        "experimental_target":"Warning probability for future TAIEX price-only drawdown; no executable TXF trading strategy.",
        "factor_weights":"Fixed equal weights across available factors, minimum 5 of 6",
        "model_features":list(FEATURES),
        "predictor_lookback_taiwan_sessions":20,
        "post_close_feature_action_lag_taiwan_sessions":LAG,
        "signal_quantile_calculation":"Current feature value percentile among pre-forward historical factor values; no re-estimation using future outcomes.",
        "alert_score_threshold_frozen_before_future_outcomes":round(threshold,5),
        "historical_score_count_used_to_freeze":count,
        "warning_events_taiwan_trading_days_worst_forward_close_drawdown_pct":EVENTS,
        "future_evaluation_plan":{
            "primary_metric":"precision versus unconditional risk-event rate by fixed horizon",
            "secondary_metrics":["alert_count","true_positive","false_positive","event_count",
                                 "recall","nonoverlap_event_precision","lead_time"],
            "minimum_fully_matured_nonoverlapping_events":30,
            "publication_control":"Every prediction must store observable source effective datetime, snapshot SHA-256 and collection timestamp BEFORE corresponding forward outcome exists.",
            "outcome_maturity":"Do not evaluate an alert until all 5 or 20 subsequent Taiwan trading sessions are complete.",
            "model_changes":"Version bump and separate forward cohort required; never retroactively alter recorded alerts.",
            "historical_retesting":"All previously viewed historical periods are exploratory diagnostics, not new out-of-sample confirmation.",
            "no_trading_pnl_claims":True
        },
        "source_clock_and_reliability_not_complete":True,
        "collect_new_records_automatically":False,
        "forward_prediction_engine_started":False,
        "new_unseen_outcome_count":0,
        "frozen_artifact_sha256":{
            "storage/phase4_publication_aware_panel.json":sha("storage/phase4_publication_aware_panel.json"),
            "storage/phase3_fred_pit_vintages.json":sha("storage/phase3_fred_pit_vintages.json"),
            "scripts/backtest_phase2_research.py":sha("scripts/backtest_phase2_research.py"),
            "scripts/audit_phase3_robustness.py":sha("scripts/audit_phase3_robustness.py"),
            "scripts/audit_phase4_publication_timing.py":sha("scripts/audit_phase4_publication_timing.py"),
        },
        "quality_gate_status":"BLOCKED",
        "blocking_reasons":[
            "No new forward prediction is available after 2026-11-12.",
            "HY/IG/VIX per-observation release hour has not been certified.",
            "ALFRED 94 sampled historical checks do not prove all 718 sessions independent.",
            "TAIFEX independent exceptional-closure evidence sweep remains incomplete.",
            "Transaction cost, contract roll and legally executable instrument are not specified."
        ],
        "formal_full_model_backtest_authorized":False,
        "live_threshold_changes_authorized":False
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("FROZEN_PROSPECTIVE_RESEARCH_PROTOCOL",
          "threshold",report["alert_score_threshold_frozen_before_future_outcomes"],
          "historical_scores",count,
          "first_unseen",FIRST_UNSEEN_DATE,
          "new_outcomes",0,flush=True)

if __name__=="__main__":
    main()
