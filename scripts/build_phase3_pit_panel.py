"""Build 718-row historical ALFRED-vintage-aware research panel, never overwrite Phase 2.

PIT as-of = previous US calendar date for a Taiwan close signal.
This uses ALFRED real-time periods, not latest FRED retrospective history.
NFCI remains excluded from model scores until weekly timing is certified.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

from collect_phase3_pit_fred import construct, FACTORS

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"storage/phase2_joined_panel.json"
VINTAGES=ROOT/"storage/phase3_fred_pit_vintages.json"
OUT=ROOT/"storage/phase3_pit_joined_panel.json"
AUDIT=ROOT/"docs/phase3_pit_join_audit.json"

def load(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))

def main():
    stage2=load("storage/phase2_joined_panel.json")
    vintages=load("storage/phase3_fred_pit_vintages.json")
    source_audit=load("docs/phase3_pit_source_audit.json")
    checkpoint=load("docs/phase3_vintage_audit.json")
    assert source_audit["status"]=="source_pit_collection_validated_sampled"
    assert source_audit["historical_pit_daily_panel_ready"] is True
    assert vintages["full_model_backtest_authorized"] is False
    rows=stage2["rows"]
    assert len(rows)==718
    dates=[x["date"] for x in rows]
    checks={(r["market_session"],r["series_id"]):r for r in checkpoint["checks"]}
    reconstructed={}
    for key, series in FACTORS.items():
        assert key in vintages["series"] and vintages["series"][key]["series_id"]==series
        vals,mismatch=construct(vintages["series"][key],dates,checks)
        assert not mismatch, f"ALFRED sample mismatch for {key}"
        reconstructed[key]=vals
    new=[]
    coverage={k:0 for k in FACTORS}
    altered={k:0 for k in FACTORS}
    stale={k:0 for k in FACTORS}
    for i,r in enumerate(rows):
        fixed={}
        for key in FACTORS:
            observed=reconstructed[key][i]
            if observed["value"] is not None:
                coverage[key]+=1
            if observed["stale"]:
                stale[key]+=1
            original=r["us_previous_dated_observations"].get(key,{})
            if (original.get("value")!=observed["value"] or
                    original.get("observed_date")!=observed["observed_date"]):
                altered[key]+=1
            fixed[key]=observed
            if observed["value"] is not None:
                assert observed["observed_date"]<=observed["asof_us_calendar_date"]
                assert observed["asof_us_calendar_date"]<r["date"]
        entry={k:v for k,v in r.items() if k!="us_previous_dated_observations"}
        entry["us_previous_dated_observations"]=fixed
        entry["pit_model"]="ALFRED effective-realtime-date vintage <= previous US calendar day"
        entry["time_limitations"]={
            "tw_daily_features":"available after market close, next TW session earliest",
            "us_factor_day":"previous US calendar date for Taiwan end-of-day decision",
            "fred_vintage_day_is_intraday_time_proof":False}
        new.append(entry)
    obj={
        "schema_version":2,"window":stage2["window"],"rows":new,
        "original_stage2_sha256":hashlib.sha256(BASE.read_bytes()).hexdigest(),
        "vintage_data_sha256":hashlib.sha256(VINTAGES.read_bytes()).hexdigest(),
        "realtime_method":"ALFRED immutable revision history as-of prior US calendar date",
        "pit_revisions_applied":True,
        "intraday_release_times_fully_certified":False,
        "twse_tx_observation_publication_time_certified":False,
        "formal_backtest_authorized":False,
        "live_threshold_changes_authorized":False
    }
    OUT.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report={
        "status":"pit_joined_research_panel_ready",
        "sessions":len(new),"field_coverage_count":coverage,
        "changed_vs_previous_latest_history":altered,
        "stale_unusable_count":stale,
        "original_stage2_sha256":obj["original_stage2_sha256"],
        "vintage_data_sha256":obj["vintage_data_sha256"],
        "new_pit_snapshot_sha256":hashlib.sha256(OUT.read_bytes()).hexdigest(),
        "sampled_vintage_checks_valid":len(checks),
        "p0_gap_no_prior_history":{k:len(new)-coverage[k] for k in FACTORS},
        "publication_qualification":[
            "ALFRED vintage effective calendar date is historical availability, not exact intraday timestamp",
            "Using as-of previous US calendar date is conservative for Taiwan market close but source timestamp still subject to review",
            "TWSE/TAIFEX end-of-day observations are not traded at the same close",
            "NFCI vintage included for research inventory only; not part of six-factor signal",
            "No FX forward-fill from later vintages or later observations",
            "Do not interpret 718 matched rows as 718 economically independent event samples"
        ],
        "full_model_backtest_authorized":False,
        "live_threshold_changes_authorized":False}
    AUDIT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PIT_PANEL",len(new),"coverage",coverage,"changed_vs_phase2",altered,flush=True)

if __name__=="__main__":main()
