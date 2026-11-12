"""Phase 5 forward-only research forecast and mature-outcome append-only ledger.

Never computes a retrospectively issued prediction. Requires first-seen source
snapshots for >=23 consecutive official Taiwan sessions AFTER 2026-11-13 and
uses the already frozen 2-session feature lag and threshold. Outcomes are
written only once the entire subsequent 5/20 trading-session window exists,
without changing the original prediction. No live alerts or trading calls.
"""
import argparse
import bisect
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from phase5_forward_capture import ROOT,SNAPSHOTS,canonical,sha,write_once,verify_frozen
from backtest_phase2_research import prepare,LOOKBACK

FORWARD=ROOT/"storage/prospective/forecasts"
OUTCOMES=ROOT/"storage/prospective/outcomes"
STATUS=ROOT/"docs/phase5_forward_status.json"
TZ=ZoneInfo("Asia/Taipei")
FIRST="2026-11-13"
REQUIRED=("taiex","margin","cash_inst","tx_oi","fx","hy","vix")
KEYS=("foreign_tx_short_pressure","margin_deleveraging_20d",
      "institutional_net_selling_5d","twd_depreciation_20d",
      "hy_oas_widening_20d","prior_us_vix_level")

def verified_snapshot(path):
    blob=path.read_bytes()
    j=json.loads(blob)
    d=j["session_date"]
    if j.get("snapshot_kind")!="prospective_first_seen" or j.get("status")!="complete":
        raise ValueError("nonqualifying_snapshot:"+d)
    if d < FIRST or path.name!=d+".json":
        raise ValueError("snapshot_invalid_cohort_or_name")
    if not all(k in j["sources"] for k in REQUIRED):
        raise ValueError("snapshot_missing_frozen_model_sources")
    start=dt.datetime.fromisoformat(j["started_at_utc"])
    end=dt.datetime.fromisoformat(j["completed_at_utc"])
    if start.utcoffset()!=dt.timedelta(0) or end.utcoffset()!=dt.timedelta(0) or end<start:
        raise ValueError("snapshot_collection_time_invalid")
    if start.astimezone(TZ).date().isoformat()!=d or end.astimezone(TZ).date().isoformat()!=d:
        raise ValueError("snapshot_not_first_seen_on_source_date")
    if not (end>=dt.datetime.fromisoformat(d+"T20:00:00+08:00")):
        raise ValueError("snapshot_taken_before_after_close_cutoff")
    if "previous_month_calendar" in j["sources"]:
        _,past=j["sources"]["previous_month_calendar"]["value"]
        target=(dt.date.fromisoformat(d[:7]+"-01")-dt.timedelta(days=1)).strftime("%Y-%m")
        if not past or any(p[:7]!=target for p in past):
            raise ValueError("previous_month_official_calendar_invalid")
    for k,obj in j["sources"].items():
        ts=dt.datetime.fromisoformat(obj["fetched_at_utc"])
        if ts<start or ts>end or len(obj["response_sha256"])!=64:
            raise ValueError("source_not_fetched_within_snapshot:"+k)
    price,month_dates=j["sources"]["taiex"]["value"]
    if not 1000<price<100000 or d not in month_dates or any(v>d for v in month_dates):
        raise ValueError("incorrect_market_date_or_price")
    for k in ("margin","cash_inst"):
        if j["sources"][k]["value"]["date"]!=d:
            raise ValueError("wrong_TWSE_session_date:"+k)
    o=j["sources"]["tx_oi"]["value"]
    if o["date"]!=d or o["long_oi"]-o["short_oi"]!=o["value"]:
        raise ValueError("incorrect_taifex_session_or_arithmetic")
    for k in ("fx","hy","vix"):
        if j["sources"][k]["value"]["observed_date"]>d:
            raise ValueError("future_dated_us_factor")
    return j,sha(blob)

def to_model_row(snap):
    src=snap["sources"]
    return {
        "date":snap["session_date"],
        "tx_oi_net_contracts":src["tx_oi"]["value"]["value"],
        "tx_oi_long_contracts":src["tx_oi"]["value"]["long_oi"],
        "tx_oi_short_contracts":src["tx_oi"]["value"]["short_oi"],
        "margin_balance_twd":src["margin"]["value"]["value"],
        "cash_institutional_net_twd":src["cash_inst"]["value"]["value"],
        "taiex_price_index_close":src["taiex"]["value"][0],
        "us_previous_dated_observations":{
            k:{"value":src[k]["value"]["value"],
               "observed_date":src[k]["value"]["observed_date"],
               "first_seen_at_utc":src[k]["fetched_at_utc"],
               "source_clock_certified":False}
            for k in ("fx","hy","vix")
        }
    }

def frozen_distributions():
    history=json.loads((ROOT/"storage/phase4_publication_aware_panel.json").read_text(encoding="utf-8"))["rows"]
    assert len(history)==718
    features=prepare(history)
    return {k:sorted(f[k] for f in features[LOOKBACK:] if f is not None and k in f)
            for k in KEYS}

def score(feat,distributions):
    if feat is None:return None
    p=[100*bisect.bisect_left(distributions[k],feat[k])/len(distributions[k])
       for k in KEYS if k in feat and distributions[k]]
    return round(sum(p)/len(p),5) if len(p)>=5 else None

def session_sequence(snapshots):
    expected=set()
    for snap in snapshots.values():
        for name in ("taiex","previous_month_calendar"):
            if name not in snap["sources"]:
                continue
            for date in snap["sources"][name]["value"][1]:
                if FIRST<=date<=snap["session_date"]:
                    expected.add(date)
    return sorted(expected)

def maturity(forecast_date,pred,snapshots,expected):
    if not isinstance(pred.get("created_at_utc"),str):
        raise ValueError("forecast_without_recorded_creation_time")
    start=dt.datetime.fromisoformat(pred["created_at_utc"])
    if start.utcoffset()!=dt.timedelta(0):
        raise ValueError("forecast_record_time_not_UTC")
    if forecast_date not in expected:return []
    anchor=expected.index(forecast_date)
    outputs=[]
    for horizon,cutoff in ((5,-3.0),(20,-5.0)):
        next_sessions=expected[anchor+1:anchor+1+horizon]
        if len(next_sessions)!=horizon or any(d not in snapshots for d in next_sessions):
            continue
        first_seen=[dt.datetime.fromisoformat(snapshots[d]["completed_at_utc"]) for d in next_sessions]
        if any(t<=start for t in first_seen):
            raise ValueError("future_target_observed_before_forecast")
        baseline=snapshots[forecast_date]["sources"]["taiex"]["value"][0]
        prices=[snapshots[d]["sources"]["taiex"]["value"][0] for d in next_sessions]
        worst=round(100*(min(prices)/baseline-1),5)
        finish=round(100*(prices[-1]/baseline-1),5)
        outcome={
            "status":"matured_prospective_research_outcome",
            "forecast_session":forecast_date,"horizon":horizon,
            "event_cutoff_pct":cutoff,"event_occurred":worst<=cutoff,
            "worst_forward_close_drawdown_pct":worst,
            "terminal_forward_price_return_pct":finish,
            "forecast_sha256":sha(canonical(pred)),
            "forward_snapshot_dates":next_sessions,
            "all_forward_snapshots_seen_after_forecast":True,
            "created_after_forward_window_completed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "does_not_imply_executable_investment_return":True,
            "formal_model_backtest_authorized":False
        }
        outputs.append((OUTCOMES/(forecast_date+"_"+str(horizon)+"d.json"),outcome))
    return outputs

def self_test(frozen):
    from audit_phase3_robustness import scorer
    original=json.loads((ROOT/"storage/phase4_publication_aware_panel.json").read_text(encoding="utf-8"))["rows"]
    fitted=scorer(prepare(original),len(original),2)
    assert fitted is not None
    assert round(fitted[1],5)==frozen["alert_score_threshold_frozen_before_future_outcomes"]
    assert len(frozen_distributions())==6
    assert score(None,frozen_distributions()) is None
    print("PHASE5_LEDGER_SELF_TEST pass - frozen percentile threshold matches and no retroactive prediction")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("selftest","record"),default="record")
    args=p.parse_args()
    frozen=verify_frozen()
    if args.mode=="selftest":
        self_test(frozen)
        return
    snapshots={}
    snap_hashes={}
    for path in sorted(SNAPSHOTS.glob("*.json")):
        snap,snap_hash=verified_snapshot(path)
        if snap["session_date"] in snapshots:
            raise ValueError("duplicate_first_seen_snapshot")
        if snap["frozen_protocol_sha256"]!=sha((ROOT/"docs/phase4_frozen_prospective_protocol.json").read_bytes()):
            raise ValueError("snapshot_different_frozen_protocol")
        snapshots[snap["session_date"]]=snap
        snap_hashes[snap["session_date"]]=snap_hash
    expected=session_sequence(snapshots)
    today=dt.datetime.now(TZ).date().isoformat()
    forecasts_created=0
    maturity_created=0
    status="waiting_for_first_prospective_snapshot"
    why="No canonical snapshot observed on or after cohort start"
    if snapshots:
        dates=sorted(snapshots)
        recent=dates[-23:]
        if len(recent)<23:
            status="waiting_for_23_consecutive_prospective_market_sessions"
            why=f"{len(recent)} first-seen sessions recorded; 23 required for 20-day lookback and 2-session lag"
        elif expected and [x for x in expected if recent[0]<=x<=recent[-1]]!=recent:
            status="missing_first_seen_sessions_in_signal_window"
            why="Missing daily snapshots within official observed market-session window; cannot retroactively fill"
        elif (len({d[:7] for d in recent})>1 and
              any(not any(
                    "previous_month_calendar" in snapshots[d]["sources"] and
                    snapshots[d]["sources"]["previous_month_calendar"]["value"][1][0][:7]==month
                    for d in recent if d[:7]>month)
                  for month in sorted({d[:7] for d in recent})[:-1])):
            status="missing_month_end_official_calendar_crosscheck"
            why="Cannot certify full cross-month Taiwan trading session sequence without next-month TWSE FMTQIK evidence"
        elif recent[-1]!=today:
            status="latest_snapshot_not_collected_today"
            why="Never issue a retrospective forecast"
        else:
            model_rows=[to_model_row(snapshots[d]) for d in recent]
            lag=frozen["post_close_feature_action_lag_taiwan_sessions"]
            signal_index=len(model_rows)-lag-1
            feat=prepare(model_rows)[signal_index]
            magnitude=score(feat,frozen_distributions())
            if magnitude is None:
                status="insufficient_frozen_factor_coverage"
                why="Less than 5 valid frozen-rule factors in eligible delayed-session feature"
            else:
                forecast_file=FORWARD/(today+".json")
                pred={
                    "kind":"prospective_research_prediction_not_live_alert",
                    "forecast_session":today,
                    "created_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                    "signal_observed_session":recent[signal_index],
                    "signal_lag_taiwan_sessions":lag,
                    "frozen_research_threshold":frozen["alert_score_threshold_frozen_before_future_outcomes"],
                    "score":magnitude,
                    "research_alert":magnitude>=frozen["alert_score_threshold_frozen_before_future_outcomes"],
                    "model_feature_values":feat,
                    "feature_source_snapshots_sha256":{d:snap_hashes[d] for d in recent},
                    "price_only_outcome_baseline":model_rows[-1]["taiex_price_index_close"],
                    "frozen_protocol_sha256":sha((ROOT/"docs/phase4_frozen_prospective_protocol.json").read_bytes()),
                    "source_release_minute_certified":False,
                    "model_formal_validated":False,
                    "not_an_executable_trade":True
                }
                if write_once(forecast_file,pred):
                    forecasts_created=1
                status="prospective_research_score_recorded_or_preserved"
                why="Score frozen before 5/20 future-session outcomes; never posted as live trading alert"
    # Outcome recording is always separate; must never rewrite first-seen alerts.
    existing={path.stem[:10]:path for path in FORWARD.glob("*.json")}
    for date,path in sorted(existing.items()):
        if date not in snapshots:
            raise ValueError("forecast_with_no_baseline_first_seen_snapshot")
        pred=json.loads(path.read_bytes())
        if pred["forecast_session"]!=date:
            raise ValueError("forecast_wrong_date")
        for opath,obj in maturity(date,pred,snapshots,expected):
            if write_once(opath,obj):
                maturity_created+=1
    summary={
        "status":status,"reason":why,"checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "frozen_protocol_sha256":sha((ROOT/"docs/phase4_frozen_prospective_protocol.json").read_bytes()),
        "prospective_immutable_snapshots":len(snapshots),
        "first_observed_session":min(snapshots) if snapshots else None,
        "last_observed_session":max(snapshots) if snapshots else None,
        "research_predictions_total":len(list(FORWARD.glob("*.json"))),
        "new_predictions_this_execution":forecasts_created,
        "research_outcome_files_total":len(list(OUTCOMES.glob("*.json"))),
        "new_matured_outcomes_this_execution":maturity_created,
        "all_previous_historical_sessions_are_exploratory":True,
        "live_threshold_changes_authorized":False,
        "formal_full_model_backtest_authorized":False
    }
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    STATUS.write_bytes(canonical(summary))
    print("PHASE5_LEDGER",status,
          "first_seen",len(snapshots),"research_scores",summary["research_predictions_total"],
          "matured_outcome_files",summary["research_outcome_files_total"],flush=True)

if __name__=="__main__":
    main()
