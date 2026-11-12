"""Re-evaluate the EXACT previously inspected 70/30 research design on PIT-corrected data.

This is a post-hoc reanalysis. Even if descriptive performance looks better,
it is NOT evidence of an unseen holdout, formal calibration, causal predictability,
or a tradable profit strategy.
"""
import hashlib
import json
from pathlib import Path

from backtest_phase2_research import prepare
from audit_phase3_robustness import scorer, outcome, summarize, nonoverlap, block_bootstrap, rolling_regimes

ROOT=Path(__file__).resolve().parents[1]
PIT=ROOT/"storage/phase3_pit_joined_panel.json"
AUDIT=ROOT/"docs/phase3_pit_join_audit.json"
OLD=ROOT/"docs/phase2_risk_research_backtest.json"
OUT=ROOT/"docs/phase3_pit_research_retest.json"
HORIZONS={5:-3.0,20:-5.0}

def main():
    raw=PIT.read_bytes()
    obj=json.loads(raw)
    aud=json.loads(AUDIT.read_text(encoding="utf-8"))
    old=json.loads(OLD.read_text(encoding="utf-8"))
    sha=hashlib.sha256(raw).hexdigest()
    assert aud["new_pit_snapshot_sha256"]==sha
    assert not obj["formal_backtest_authorized"]
    assert not aud["full_model_backtest_authorized"]
    rows=obj["rows"]
    assert len(rows)==718
    dates=[x["date"] for x in rows]
    split=int(len(rows)*.70)
    feats=prepare(rows)
    variants={}
    for lag in (0,2):
        fitted=scorer(feats,split,lag)
        assert fitted is not None, "insufficient PIT training feature coverage"
        scores,threshold,ntrain=fitted
        results={}
        for h,cutoff in HORIZONS.items():
            cases=outcome(rows,scores,threshold,split,h,cutoff)
            core=summarize(cases)
            results[str(h)+"d"]={
                "warning_event_threshold_pct":cutoff,
                "metrics":core,
                "nonoverlap_grid":nonoverlap(cases,h),
                "calendar_quarter_breakdown":rolling_regimes(cases),
                "approximate_block_bootstrap":block_bootstrap(cases,h),
                "unchanged_original_phase2_metrics":old["holdout"][str(h)+"d"],
                "same_holdout_dates_not_independent_new_test":True
            }
        variants["signal_delay_"+str(lag)+"_taiwan_sessions"]={
            "train_observations":ntrain,
            "train_threshold_from_PIT_only":round(threshold,4),
            "holdout_range":[dates[split],dates[-1]],
            "results":results}
    report={
        "status":"research_only_posthoc_PIT_corrected",
        "method":"Same six-factor fixed-rule 70/30 chronological holdout, using historical ALFRED vintages",
        "pit_data_sha256":sha,
        "data_coverage":aud["field_coverage_count"],
        "PIT_vintage_comparison_validated_samples":aud["sampled_vintage_checks_valid"],
        "variants":variants,
        "cautions":[
            "The holdout was already inspected in Phase 2 and 3; this is not new out-of-sample verification.",
            "ALFRED calendar-date vintage availability is not source-specific intraday release time proof.",
            "Only three independent ALFRED as-of checkpoints per series were tested.",
            "S&P/VIX/H10/TWSE settlement and publishing times require additional provenance checks.",
            "NFCI not part of six-factor model despite being archived.",
            "Signals measured after Taiwan closing bell cannot be traded at the same closing price.",
            "Index levels and early warning events do not imply executable transaction returns.",
            "TXF contract roll, fees, spreads and slippage are not modeled.",
            "No live thresholds or production risk scores were modified."
        ],
        "full_model_backtest_authorized":False,
        "full_model_validated":False,
        "recommended_live_threshold":None}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PIT_RETEST",report["status"],flush=True)
    for k,v in variants.items():
        print(k,{h:x["metrics"] for h,x in v["results"].items()},flush=True)

if __name__=="__main__":
    main()
