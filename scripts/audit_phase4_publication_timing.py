"""Phase 4: enforce source publication-time *eligibility* on ALFRED vintage panel.

A historical data "observation date" or FRED vintage date is not a timestamp.
For selected sources official schedules permit a defensible earliest-use bound:
H.10: previous week's business-day rates, normally Monday 16:15 NY.
       We use following THURSDAY 16:15 NY as a stricter holiday buffer;
       this is a conservative scenario, NOT an actual historical release log.
H.15/DGS10: daily 16:15 NY on release/business date; source observation date
             is a proxy, not an independently certified per-date timestamp.
NFCI: Wednesday 08:30 NY (Thursday after a holiday); use following
      Thursday 08:30 NY as a buffered lower bound, NOT confirmed actual time.
VIX, HY and IG: no verified source-specific minute in this study, so keep
prior-dated ALFRED values for research only and DO NOT mark time certified.
All local decisions are after Taiwan cash market close, 16:00 Asia/Taipei.
PIT corrected research panel remains immutable. This output is separate.
"""
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
IN=ROOT/"storage/phase3_pit_joined_panel.json"
OUT=ROOT/"storage/phase4_publication_aware_panel.json"
REPORT=ROOT/"docs/phase4_publication_timing_audit.json"
TW=ZoneInfo("Asia/Taipei")
NY=ZoneInfo("America/New_York")
LINKS={
 "fx":"https://www.federalreserve.gov/releases/h10/",
 "us10y":"https://www.federalreserve.gov/releases/h15/",
 "nfci":"https://www.chicagofed.org/research/data/nfci/current-data",
 "alfred":"https://fred.stlouisfed.org/docs/api/fred/realtime_period.html"
}
MODEL=("fx","hy","ig","vix","us10y","nfci")

def after_friday(date,desired_weekday,hour,minute):
    """Next week's desired weekday (Monday=0, Thursday=3)."""
    d=dt.date.fromisoformat(date)
    fri=d+dt.timedelta(days=(4-d.weekday())%7)
    release=fri+dt.timedelta(days=3+desired_weekday)
    return dt.datetime.combine(release,dt.time(hour,minute),NY)

def source_eligibility(key, observed):
    if key=="fx":
        return after_friday(observed,3,16,15),"H10_following_Thursday_1615_ET_conservative_holiday_buffer"
    if key=="nfci":
        return after_friday(observed,3,8,30),"NFCI_following_Thursday_0830_ET_conservative_holiday_buffer"
    if key=="us10y":
        d=dt.date.fromisoformat(observed)
        return dt.datetime.combine(d,dt.time(16,15),NY),"H15_observation_date_1615_ET_proxy_not_verified_actual_release"
    return None,"source_specific_publication_clock_unverified"

def main():
    source_bytes=IN.read_bytes()
    source=json.loads(source_bytes)
    rows=source["rows"]
    assert len(rows)==718 and source["formal_backtest_authorized"] is False
    output=[]
    counts=collections.Counter()
    deferred=collections.Counter()
    rule_counts=collections.Counter()
    uncertified=collections.Counter()
    invalid=[]
    examples=[]
    for i,row in enumerate(rows):
        d=row["date"]
        decision=dt.datetime.fromisoformat(d+"T16:00:00").replace(tzinfo=TW)
        factors={}
        for key in MODEL:
            original=row["us_previous_dated_observations"][key]
            v=original["value"]
            date=original["observed_date"]
            cutoff=original["asof_us_calendar_date"]
            if cutoff>=d:
                invalid.append({"date":d,"factor":key,"reason":"asof_not_prior"})
            rule=None
            when=None
            permitted=False
            if v is not None and date is not None:
                when,rule=source_eligibility(key,date)
                permitted=when is None or when.astimezone(TW)<decision
                if not permitted:
                    deferred[key]+=1
                    if len(examples)<14:
                        examples.append({"session":d,"factor":key,
                                         "observation_date":date,
                                         "conservative_eligible_at_taipei":when.astimezone(TW).isoformat()})
            else:
                rule="historical_vintage_missing_or_stale"
            if when is None and v is not None:
                uncertified[key]+=1
            if permitted and v is not None:
                counts[key]+=1
            rule_counts[rule]+=1
            factors[key]={
                **original,
                "value":v if permitted else None,
                "original_pit_value":v,
                "publication_clock_rule":rule,
                "conservative_earliest_use_at_taipei":when.astimezone(TW).isoformat() if when else None,
                "decision_at_taipei":decision.isoformat(),
                "time_gate_passed":permitted if v is not None else False,
                "actual_historical_release_timestamp_verified":False,
                "source_publication_time_certified":False
            }
        item={k:v for k,v in row.items() if k!="us_previous_dated_observations"}
        item["us_previous_dated_observations"]=factors
        output.append(item)
    assert not invalid,invalid[:5]
    assert all(x["us_previous_dated_observations"]["fx"]["value"] is None
               or x["us_previous_dated_observations"]["fx"]["time_gate_passed"] for x in output)
    result={
        "schema_version":1,
        "window":source["window"],
        "rows":output,
        "source_pit_snapshot_sha256":hashlib.sha256(source_bytes).hexdigest(),
        "method":"ALFRED historical vintage plus conservative official publisher-time schedule eligibility",
        "intentionally_not_exact_historical_release_log":True,
        "formal_backtest_authorized":False,
        "live_threshold_changes_authorized":False
    }
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report={
        "status":"conservative_time_gate_research_panel_built",
        "sessions":len(output),
        "source_pit_sha256":result["source_pit_snapshot_sha256"],
        "output_sha256":hashlib.sha256(OUT.read_bytes()).hexdigest(),
        "factor_eligible_sessions":dict(counts),
        "deferred_by_official_schedule_buffer":dict(deferred),
        "not_source_time_certified_records":dict(uncertified),
        "examples":examples,
        "policy":{
            "decision_time":"16:00 Asia/Taipei on each Taiwan cash session",
            "h10":"Weekly Monday 16:15 US Eastern previous-week rates. Conservative eligible timestamp: next Thursday 16:15 ET, not the historical actual release.",
            "h15":"Business days 16:15 US Eastern; observation-date schedule proxy, subject to holidays and source posting checks.",
            "nfci":"Normally Wednesdays 08:30 US Eastern; conservative following Thursday 08:30 ET.",
            "hy_ig_vix":"ALFRED vintage as-of prior US calendar date but no independently verified source minute; not trading-certified."
        },
        "source_urls":LINKS,
        "actual_publication_timestamps_verified_for_all_718":False,
        "source_clock_gates_fully_certified":False,
        "data_revisions_independently_verified_for_all_718":False,
        "formal_full_model_backtest_authorized":False,
        "live_threshold_changes_authorized":False
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PHASE4_TIME_GATE",report["status"],"covered",dict(counts),
          "deferred",dict(deferred),"uncertified",dict(uncertified),flush=True)

if __name__=="__main__":
    main()
