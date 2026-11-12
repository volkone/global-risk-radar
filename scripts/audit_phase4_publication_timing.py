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
    vintages=json.loads((ROOT/"storage/phase3_fred_pit_vintages.json").read_text(encoding="utf-8"))["series"]
    rows=source["rows"]
    assert len(rows)==718 and source["formal_backtest_authorized"] is False
    # Each H.10/NFCI time gate must choose the most recent ALREADY RELEASED
    # historical observation, not set the whole factor to None when a
    # newer-but-unreleased observation exists in the vintage snapshot.
    replay={}
    for name in ("fx","nfci"):
        stream=vintages[name]
        replay[name]={
            "bootstrap_date":stream["bootstrap_date"],
            "state":{v["date"]:v["value"] for v in stream["bootstrap"]},
            "changes":stream["changes"],
            "cursor":0
        }
    output=[]
    counts=collections.Counter()
    deferred=collections.Counter()
    fallback_used=collections.Counter()
    unavailable_after_filter=collections.Counter()
    uncertified=collections.Counter()
    invalid=[]
    examples=[]
    for i,row in enumerate(rows):
        date=row["date"]
        decision=dt.datetime.combine(dt.date.fromisoformat(date),dt.time(16,0),TW)
        factors={}
        for key in MODEL:
            original=row["us_previous_dated_observations"][key]
            previous_value=original["value"]
            previous_date=original["observed_date"]
            cutoff=original["asof_us_calendar_date"]
            if cutoff>=date:
                invalid.append({"date":date,"factor":key,"reason":"asof_not_prior"})
            chosen_value=previous_value
            chosen_date=previous_date
            chosen_age=original["age_calendar_days"]
            was_fallback=False
            if key in replay:
                stream=replay[key]
                if cutoff<stream["bootstrap_date"]:
                    chosen_value=None
                    chosen_date=None
                    chosen_age=None
                else:
                    while (stream["cursor"]<len(stream["changes"])
                           and stream["changes"][stream["cursor"]]["vintage_date"]<=cutoff):
                        event=stream["changes"][stream["cursor"]]
                        if event["value"] is None:
                            stream["state"].pop(event["observed_date"],None)
                        else:
                            stream["state"][event["observed_date"]]=event["value"]
                        stream["cursor"]+=1
                    available=[d for d in stream["state"] if d<=cutoff]
                    latest=max(available) if available else None
                    if latest!=previous_date:
                        invalid.append({"date":date,"factor":key,
                                        "reason":"replayed_vintage_disagrees_with_existing_PIT",
                                        "replayed":latest,"prior":previous_date})
                    eligible=[]
                    for observed in available:
                        earliest,_=source_eligibility(key,observed)
                        if earliest.astimezone(TW)<decision:
                            eligible.append(observed)
                    chosen_date=max(eligible) if eligible else None
                    chosen_age=(dt.date.fromisoformat(date)-dt.date.fromisoformat(chosen_date)).days if chosen_date else None
                    # Older weekly release is an honest as-of observation,
                    # but never silently use a too-old value.
                    chosen_value=(stream["state"][chosen_date] if chosen_date and
                                  chosen_age<=21 else None)
                    if latest and chosen_date!=latest:
                        deferred[key]+=1
                        was_fallback=chosen_value is not None
                        if was_fallback:
                            fallback_used[key]+=1
                        else:
                            unavailable_after_filter[key]+=1
                        if len(examples)<12:
                            earliest,_=source_eligibility(key,latest)
                            examples.append({"session":date,"factor":key,
                                             "newer_unreleased_observation_date":latest,
                                             "conservative_earliest_use_at_taipei":earliest.astimezone(TW).isoformat(),
                                             "selected_older_observation_date":chosen_date,
                                             "selected_older_observation_age_days":chosen_age})
            when,rule=source_eligibility(key,chosen_date) if chosen_date else (None,"historical_vintage_missing")
            if key not in replay and chosen_value is not None and when is not None:
                if when.astimezone(TW)>=decision:
                    chosen_value=None
                    deferred[key]+=1
                    unavailable_after_filter[key]+=1
            if key not in ("fx","nfci","us10y") and chosen_value is not None:
                uncertified[key]+=1
            if chosen_value is not None:
                counts[key]+=1
                if when is not None and when.astimezone(TW)>=decision:
                    invalid.append({"date":date,"factor":key,"reason":"selected_not_yet_release_eligible"})
            factors[key]={
                **original,
                "value":chosen_value,
                "observed_date":chosen_date,
                "age_calendar_days":chosen_age,
                "original_pit_value":previous_value,
                "original_pit_observed_date":previous_date,
                "used_older_published_observation":was_fallback,
                "publication_clock_rule":rule,
                "conservative_earliest_use_at_taipei":when.astimezone(TW).isoformat() if when else None,
                "decision_at_taipei":decision.isoformat(),
                "time_gate_passed":bool(chosen_value is not None),
                "actual_historical_release_timestamp_verified":False,
                "source_publication_time_certified":False
            }
        item={k:v for k,v in row.items() if k!="us_previous_dated_observations"}
        item["us_previous_dated_observations"]=factors
        output.append(item)
    assert not invalid,invalid[:8]
    assert all(factor["observed_date"] is None or factor["observed_date"] < r["date"]
               for r in output for factor in r["us_previous_dated_observations"].values())
    assert all(r["us_previous_dated_observations"]["fx"]["value"] is None or
               r["us_previous_dated_observations"]["fx"]["time_gate_passed"] for r in output)
    result={
        "schema_version":2,
        "window":source["window"],
        "rows":output,
        "source_pit_snapshot_sha256":hashlib.sha256(source_bytes).hexdigest(),
        "source_vintage_snapshot_sha256":hashlib.sha256(
            (ROOT/"storage/phase3_fred_pit_vintages.json").read_bytes()).hexdigest(),
        "method":"ALFRED reconstructed actual historical vintage + conservative publisher-time eligibility; select latest already release-eligible observation",
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
        "newer_observation_deferred_by_schedule_buffer":dict(deferred),
        "older_asof_release_eligible_observation_used":dict(fallback_used),
        "no_usable_older_observation_after_filter":dict(unavailable_after_filter),
        "not_source_time_certified_records":dict(uncertified),
        "examples":examples,
        "policy":{
            "decision_time":"16:00 Asia/Taipei on each Taiwan cash session",
            "h10":"Weekly Monday 16:15 US Eastern previous-week rates. Conservative eligible timestamp: next Thursday 16:15 ET, not the historical actual release.",
            "h15":"Business days 16:15 US Eastern; observation-date schedule proxy, subject to holidays and source posting checks.",
            "nfci":"Normally Wednesdays 08:30 US Eastern; conservative following Thursday 08:30 ET.",
            "hy_ig_vix":"ALFRED vintage as-of prior US calendar date but no independently verified source minute; not trading-certified.",
            "historical_last_known_value":"When most recent ALFRED observation is not yet scheduled release-eligible, select the most recent OLDER observed value available at the prior vintage, at most 21 calendar days old. Never backfill from future."
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
          "newer_deferred",dict(deferred),"older_fallback",dict(fallback_used),
          "unavailable",dict(unavailable_after_filter),flush=True)

if __name__=="__main__":
    main()
