"""Phase 3 post-hoc stress tests of the Phase 2 research signal.

This is NOT a new untouched holdout: the earlier 70/30 result has already been
observed. Delay variants, non-overlap grids, block bootstrap and alternate splits
are diagnostics, not out-of-sample confirmation or model selection.

H.10 currency rate observations are published in weekly batches (Monday 16:15 ET
of the following week); using a date-stamped daily value at Taiwan close can
introduce lookahead. A 10-calendar-day observation lag is an intentionally
conservative scenario, not a verified publication calendar.
"""
import bisect
import collections
import datetime as dt
import hashlib
import json
import math
import random
from pathlib import Path

from backtest_phase2_research import prepare, numeric, LOOKBACK

ROOT=Path(__file__).resolve().parents[1]
PANEL=ROOT/"storage/phase2_joined_panel.json"
FACTORS=ROOT/"storage/historical_fred_factors.json"
OUT=ROOT/"docs/phase3_robustness_audit.json"
HORIZONS={5:-3.0,20:-5.0}
KEYS=("foreign_tx_short_pressure","margin_deleveraging_20d",
      "institutional_net_selling_5d","twd_depreciation_20d",
      "hy_oas_widening_20d","prior_us_vix_level")
SPLITS=(0.6,0.7,0.8)
LAGS=(0,1,2,3)
Q=0.80

def percentile(v, values):
    return 100.0*bisect.bisect_left(values,v)/len(values)

def scorer(feats,split,lag):
    train_distributions={
        k:sorted(f[k] for f in feats[LOOKBACK:split] if f is not None and k in f)
        for k in KEYS
    }
    if any(len(x)<120 for x in train_distributions.values()):
        return None
    scores=[]
    for i in range(len(feats)):
        feat=feats[i-lag] if i>=lag else None
        if feat is None:
            scores.append(None)
            continue
        values=[percentile(feat[k],train_distributions[k]) for k in KEYS if k in feat]
        scores.append(sum(values)/len(values) if len(values)>=5 else None)
    train=sorted(x for x in scores[LOOKBACK+lag:split] if x is not None)
    if len(train)<120:
        return None
    threshold=train[min(len(train)-1,int(len(train)*Q))]
    return scores,threshold,len(train)

def prepare_h10_conservative(rows, fx_history):
    dates=sorted(x["date"] for x in fx_history)
    vals={x["date"]:x["value"] for x in fx_history}
    new=[]
    for row in rows:
        date=row["date"]
        cutoff=(dt.date.fromisoformat(date)-dt.timedelta(days=10)).isoformat()
        idx=bisect.bisect_right(dates,cutoff)-1
        newrow=dict(row)
        fs=dict(row["us_previous_dated_observations"])
        if idx>=0:
            d=dates[idx]
            fs["fx"]={"value":vals[d],"observed_date":d,
                      "age_calendar_days":(dt.date.fromisoformat(date)-
                                           dt.date.fromisoformat(d)).days,
                      "missing_reason":None}
        else:
            fs["fx"]={"value":None,"observed_date":None,
                      "age_calendar_days":None,"missing_reason":"no_old_enough_fx_observation"}
        newrow["us_previous_dated_observations"]=fs
        new.append(newrow)
    return new

def outcome(rows, scores, threshold, split, horizon, cutoff):
    cases=[]
    for i in range(split,len(rows)-horizon):
        if scores[i] is None:
            continue
        close=rows[i]["taiex_price_index_close"]
        future=[x.get("taiex_price_index_close") for x in rows[i+1:i+horizon+1]]
        if not numeric(close) or close<=0 or any(not numeric(x) or x<=0 for x in future):
            continue
        worst=100*(min(future)/close-1)
        cases.append({"index":i,"date":rows[i]["date"],
                      "alert":scores[i]>=threshold,"event":worst<=cutoff,
                      "worst_drawdown_pct":worst})
    return cases

def summarize(cases):
    alerted=[x for x in cases if x["alert"]]
    evented=[x for x in cases if x["event"]]
    hits=sum(x["event"] for x in alerted)
    precision=hits/len(alerted) if alerted else None
    base=len(evented)/len(cases) if cases else None
    return {"n":len(cases),"alert_n":len(alerted),"event_n":len(evented),
            "alert_event_n":hits,"precision":round(precision,4) if precision is not None else None,
            "base_rate":round(base,4) if base is not None else None,
            "precision_minus_base":round(precision-base,4) if precision is not None and base is not None else None}

def quarter(date):
    return date[:4]+"-Q"+str((int(date[5:7])-1)//3+1)

def nonoverlap(cases,h):
    byindex={x["index"]:x for x in cases}
    if not cases:
        return []
    start=min(byindex)
    grid=[]
    for offset in range(h):
        subset=[r for idx,r in byindex.items() if (idx-start)%h==offset]
        grid.append({"offset":offset,**summarize(subset),
                     "warning":"Samples on this grid have disjoint h-session future windows; grid selection is not optimized."})
    return grid

def block_bootstrap(cases,h,reps=600,seed=20261112):
    rng=random.Random(seed+h)
    n=len(cases)
    if n<30:
        return None
    lifts=[]
    precisions=[]
    for _ in range(reps):
        sampled=[]
        while len(sampled)<n:
            start=rng.randrange(n)
            for k in range(h):
                sampled.append(cases[(start+k)%n])
                if len(sampled)>=n:
                    break
        alerted=[x for x in sampled if x["alert"]]
        if len(alerted)<5:
            continue
        precision=sum(x["event"] for x in alerted)/len(alerted)
        base=sum(x["event"] for x in sampled)/n
        precisions.append(precision)
        lifts.append(precision-base)
    def interval(values):
        if len(values)<100:
            return None
        values.sort()
        return [round(values[int((len(values)-1)*.025)],4),
                round(values[int((len(values)-1)*.975)],4)]
    return {"method":"deterministic_moving_block_bootstrap",
            "block_size_sessions":h,"replicates_attempted":reps,
            "valid_replicates":len(precisions),
            "precision_approx_95pct_interval":interval(precisions),
            "precision_minus_base_approx_95pct_interval":interval(lifts),
            "warning":"Exploratory approximate intervals only; limited single-period time series, overlapping outcomes, regime nonstationarity, and prior result inspection prevent confirmatory inference."}

def rolling_regimes(cases):
    out={}
    for q in sorted({quarter(x["date"]) for x in cases}):
        subset=[x for x in cases if quarter(x["date"])==q]
        out[q]={"summary":summarize(subset),"minimum_alert_count_for_interpretation":8,
                "enough_alerts":sum(x["alert"] for x in subset)>=8}
    return out

def main():
    data=PANEL.read_bytes()
    panel=json.loads(data)
    rows=panel["rows"]
    assert len(rows)==718 and panel["formal_backtest_authorized"] is False
    fred=json.loads(FACTORS.read_text(encoding="utf-8"))["series"]
    conservative=prepare_h10_conservative(rows,fred["fx"]["history"])
    signal_sets={
        "baseline_daily_fx_observation_date_only":prepare(rows),
        "h10_fx_observation_at_least_10_calendar_days_old":prepare(conservative)
    }
    results={}
    for source,feats in signal_sets.items():
        for split_fraction in SPLITS:
            split=int(len(rows)*split_fraction)
            for lag in LAGS:
                if source.startswith("baseline") and split_fraction!=0.7 and lag not in (0,2):
                    continue
                if source.startswith("h10") and split_fraction!=0.7 and lag not in (0,2):
                    continue
                valid=scorer(feats,split,lag)
                key=f"{source}|train_{round(split_fraction*100)}pct|signal_lag_{lag}_tx_sessions"
                if valid is None:
                    results[key]={"status":"insufficient_train_features"}
                    continue
                scores,threshold,ntrain=valid
                horizon_results={}
                for h,cutoff in HORIZONS.items():
                    cases=outcome(rows,scores,threshold,split,h,cutoff)
                    record={"cutoff_pct":cutoff,"summary":summarize(cases),
                            "holdout_window":[rows[split]["date"],rows[-h-1]["date"]]}
                    if split_fraction==0.7 and lag in (0,2):
                        record["quarterly"]=rolling_regimes(cases)
                        record["nonoverlap_all_phase_offsets"]=nonoverlap(cases,h)
                        record["approximate_block_bootstrap"]=block_bootstrap(cases,h)
                    horizon_results[f"{h}d"]=record
                results[key]={"status":"descriptive_not_confirmatory",
                              "training_count":ntrain,
                              "threshold_from_train_only":round(threshold,4),
                              "horizons":horizon_results}
    baseline=results["baseline_daily_fx_observation_date_only|train_70pct|signal_lag_0_tx_sessions"]
    assert baseline["horizons"]["5d"]["summary"]["n"]==211
    assert baseline["horizons"]["20d"]["summary"]["n"]==196
    assert baseline["horizons"]["5d"]["summary"]["precision"]==0.431
    assert baseline["horizons"]["20d"]["summary"]["precision"]==0.5714
    report={
        "status":"post_hoc_sensitivity_complete",
        "kind":"after_original_holdout_was_viewed_not_fresh_holdout",
        "data_sha256":hashlib.sha256(data).hexdigest(),
        "sources":[
            {"label":"FRED ALFRED realtime semantics",
             "url":"https://fred.stlouisfed.org/docs/api/fred/realtime_period.html"},
            {"label":"Federal Reserve H10 weekly release rule",
             "url":"https://www.federalreserve.gov/releases/h10/"},
            {"label":"Chicago Fed NFCI Wednesday release schedule",
             "url":"https://www.chicagofed.org/research/data/nfci/current-data"}
        ],
        "assumptions":{
            "tx_twse_end_of_day_signals":"lag 0 means signal computed after t close; earliest hypothetical action is t+1, not t close",
            "lag_experiments_tx_sessions":list(LAGS),
            "h10_10_calendar_day_lag":"Conservative observation-date cutoff, NOT an exact US holiday-aware published vintage",
            "monthly_fx_lookback_sessions":LOOKBACK,
            "sampling_holdout_splits":[round(x,2) for x in SPLITS],
            "sample_overlap":"Five- and 20-session forward outcome windows overlap unless explicitly selected on nonoverlap grid",
            "quarter_segments":"Holdout spans mainly 2026; quarter diagnostics are not multi-cycle generalization",
            "score_weights":"Equal fixed unoptimized illustrative factors",
            "transaction_costs":"not applicable to this warning-only diagnostic; no executable trading strategy",
            "release_time_source_verification":"pending ALFRED probe plus primary release timestamp review"
        },
        "variants":results,
        "interpretation_warnings":[
            "Do not select a favorite lag or split from these results: all variants are post-hoc.",
            "FRED source observation date is not a publication date.",
            "FRED historical vintage as-of date can differ from latest downloaded history.",
            "Approximate bootstrap intervals are descriptive, not formal model certification.",
            "H10 FX 10-day observation cutoff is a stress test, not a proven source publication lag.",
            "No economic PnL, executable TXF price/roll, or finalized model calibration."
        ],
        "full_model_backtest_authorized":False,
        "live_threshold_changes_authorized":False
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PHASE3_ROBUSTNESS",report["status"],"variants",len(results))
    for key in (
        "baseline_daily_fx_observation_date_only|train_70pct|signal_lag_0_tx_sessions",
        "baseline_daily_fx_observation_date_only|train_70pct|signal_lag_2_tx_sessions",
        "h10_fx_observation_at_least_10_calendar_days_old|train_70pct|signal_lag_0_tx_sessions",
        "h10_fx_observation_at_least_10_calendar_days_old|train_70pct|signal_lag_2_tx_sessions"
    ):
        x=results[key]
        print(key,{h:v["summary"] for h,v in x["horizons"].items()},flush=True)

if __name__=="__main__":main()
