"""Rebuild full FRED factor availability as-of each Taiwan market session.

This uses ALFRED's real-time observations:
* output_type=1 provides a historical bootstrap snapshot at 2023-11-09.
* output_type=3 provides new/changed observations and their effective vintage dates.
* applying only vintages known by previous US calendar date gives point-in-time values.

Dates are not intraday timestamps; therefore no formal trading authorization.
Does not rewrite phase2 inputs, live data, old backtests or any gate.
"""
import collections
import datetime as dt
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
START="2023-11-11"
END="2026-10-31"
BOOTSTRAP_DATE="2023-11-09"
UPDATES_START="2023-11-10"
BOOTSTRAP_CANDIDATES=("2023-11-09","2024-01-15","2024-06-19","2025-01-15","2026-01-15")
OBS_START="2023-09-01"
FACTORS={
    "fx":"DEXTAUS","hy":"BAMLH0A0HYM2","ig":"BAMLC0A0CM",
    "vix":"VIXCLS","us10y":"DGS10","nfci":"NFCI"}
SAMPLES=("2024-06-20","2025-06-05","2026-10-02")
MAX_REQUESTS=42
MAX_RESPONSE_BYTES=5_000_000
PAGE_LIMIT=10000
HTTP_SLEEP_SECONDS=0.8
OUT=ROOT/"storage/phase3_fred_pit_vintages.json"
REPORT=ROOT/"docs/phase3_pit_source_audit.json"

def load(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,path)

class API:
    def __init__(self,key):
        if not key:
            raise RuntimeError("FRED_API_KEY_not_configured")
        self.key=key
        self.requests=0
    def fetch(self,series,mode,offset=0,bootstrap_date=BOOTSTRAP_DATE):
        if self.requests>=MAX_REQUESTS:
            raise RuntimeError("request_budget_exhausted")
        params={
            "series_id":series,
            "api_key":self.key,
            "file_type":"json",
            "output_type":mode,
            "observation_start":OBS_START,
            "observation_end":END,
            "limit":PAGE_LIMIT,
            "offset":offset
        }
        if mode==1:
            params["realtime_start"]=bootstrap_date
            params["realtime_end"]=bootstrap_date
        elif mode==3:
            params["realtime_start"]=(dt.date.fromisoformat(bootstrap_date)+dt.timedelta(days=1)).isoformat()
            params["realtime_end"]=END
        else:
            raise ValueError("unsupported_mode")
        url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"GlobalRiskRadar PIT source audit"})
        for attempt in range(3):
            self.requests+=1
            time.sleep(HTTP_SLEEP_SECONDS)
            try:
                with urllib.request.urlopen(req,timeout=40) as response:
                    if response.status!=200:
                        raise ValueError("unexpected_response_status")
                    raw=response.read(MAX_RESPONSE_BYTES+1)
                if len(raw)>MAX_RESPONSE_BYTES:
                    raise ValueError("source_response_exceeds_budget")
                obj=json.loads(raw)
                if not isinstance(obj,dict) or not isinstance(obj.get("observations"),list):
                    raise ValueError("malformed_FRED_response")
                if int(obj.get("output_type",-1))!=mode:
                    raise ValueError("incorrect_FRED_output_type")
                return obj,hashlib.sha256(raw).hexdigest()
            except urllib.error.HTTPError as exc:
                if exc.code in (400,401,403,404) or attempt==2:
                    body=exc.read(600).decode("utf-8",errors="replace").replace(self.key,"<redacted>")
                    raise RuntimeError("FRED_HTTP_"+str(exc.code)+"_series_"+series+"_mode_"+str(mode)+"_message_"+body[:260]) from None
            except (urllib.error.URLError,TimeoutError) as exc:
                if attempt==2:
                    raise RuntimeError("FRED_NETWORK_"+type(exc).__name__) from None
            if self.requests>=MAX_REQUESTS:
                raise RuntimeError("request_budget_exhausted")
            time.sleep(attempt+2)
        raise AssertionError("unreachable")

def collect_pages(api,series,mode,bootstrap_date=BOOTSTRAP_DATE):
    rows=[]
    source_hashes=[]
    offset=0
    total=None
    while True:
        obj,sha=api.fetch(series,mode,offset,bootstrap_date)
        source_hashes.append(sha)
        if total is None:
            total=int(obj.get("count",-1))
            if total<0:
                raise ValueError("missing_FRED_count")
        elif total!=int(obj.get("count",-1)):
            raise ValueError("FRED_count_changed_during_pagination")
        chunk=obj["observations"]
        if not chunk and offset<total:
            raise ValueError("empty_FRED_page_before_end")
        rows.extend(chunk)
        offset+=len(chunk)
        if offset>=total:
            break
        if len(chunk)<PAGE_LIMIT:
            raise ValueError("FRED_incomplete_page")
    if len(rows)!=total:
        raise ValueError("FRED_pagination_count_mismatch")
    return rows,source_hashes

def parsed_date(s):
    return dt.date.fromisoformat(s).isoformat()

def value(x):
    v=x.get("value")
    if v in (None,"","."):
        return None
    f=float(v)
    if not math.isfinite(f):
        raise ValueError("nonfinite_FRED_value")
    return f

def collect_one(api,name,series):
    # Some FRED series have no ALFRED vintage at the historical start.
    # Bootstrap at the first available later vintage; earlier sessions remain NULL.
    base=None
    bootstrap_date=None
    for candidate in BOOTSTRAP_CANDIDATES:
        try:
            base,base_hashes=collect_pages(api,series,1,candidate)
            bootstrap_date=candidate
            break
        except RuntimeError as exc:
            if "does not exist in ALFRED" not in str(exc):
                raise
            print("ALFRED_NOT_AVAILABLE_ON",series,candidate,flush=True)
    if base is None:
        raise RuntimeError("no_ALFRED_bootstrap_supported_for_"+series)
    changes,change_hashes=collect_pages(api,series,3,bootstrap_date)
    baseline={}
    for x in base:
        d=parsed_date(x["date"])
        if d>bootstrap_date:
            raise ValueError("bootstrap_observation_from_future")
        v=value(x)
        if v is not None:
            if d in baseline:
                raise ValueError("duplicate_bootstrap_date")
            baseline[d]=v
    # FRED JSON output_type=3 is a wide pivot: each observation row includes
    # a date plus series_id_YYYYMMDD columns for NEW or REVISED vintages.
    # It is NOT a list of records carrying realtime_start, as output_type=1 is.
    seen=set()
    events=[]
    prefix=series+"_"
    for x in changes:
        date=parsed_date(x["date"])
        columns=[(k,v) for k,v in x.items() if k.startswith(prefix)]
        if not columns:
            raise ValueError("missing_FRED_wide_vintage_columns")
        for col,raw_value in columns:
            stamp=col[len(prefix):]
            if len(stamp)!=8 or not stamp.isdigit():
                raise ValueError("invalid_FRED_vintage_column_"+col)
            vintage=dt.date(int(stamp[:4]),int(stamp[4:6]),int(stamp[6:])).isoformat()
            if vintage<=bootstrap_date or vintage>END or date>vintage:
                raise ValueError("invalid_vintage_date_or_observation")
            key=(vintage,date)
            if key in seen:
                raise ValueError("duplicate_FRED_vintage_observation")
            seen.add(key)
            events.append({"vintage_date":vintage,"observed_date":date,
                           "value":value({"value":raw_value})})
    events.sort(key=lambda x:(x["vintage_date"],x["observed_date"]))
    return {"series_id":series,"bootstrap_date":bootstrap_date,
            "bootstrap":[{"date":d,"value":baseline[d]} for d in sorted(baseline)],
            "changes":events,"source_response_sha256":{"bootstrap":base_hashes,"changes":change_hashes},
            "n_bootstrap":len(base),"n_changes":len(events)}

def construct(series,market_dates,verify_checks):
    state={x["date"]:x["value"] for x in series["bootstrap"]}
    changes=series["changes"]
    cursor=0
    results=[]
    mismatch=[]
    for market_session in market_dates:
        cutoff=(dt.date.fromisoformat(market_session)-dt.timedelta(days=1)).isoformat()
        if cutoff<series["bootstrap_date"]:
            results.append({"market_session":market_session,"asof_us_calendar_date":cutoff,
                            "observed_date":None,"age_calendar_days":None,
                            "value":None,"stale":False,
                            "missing_reason":"ALFRED_historical_vintage_not_available",
                            "source_method":"ALFRED_bootstrap_and_new_revised_observations"})
            continue
        while cursor<len(changes) and changes[cursor]["vintage_date"]<=cutoff:
            item=changes[cursor]
            date=item["observed_date"]
            if item["value"] is None:
                state.pop(date,None)
            else:
                state[date]=item["value"]
            cursor+=1
        eligible=[d for d in state if d<=cutoff]
        observed=max(eligible) if eligible else None
        age=((dt.date.fromisoformat(market_session)-dt.date.fromisoformat(observed)).days
             if observed else None)
        max_age=14 if series["series_id"] in ("NFCI","DEXTAUS") else 7
        result={"market_session":market_session,"asof_us_calendar_date":cutoff,
                "observed_date":observed,"age_calendar_days":age,
                "value":state[observed] if observed and age<=max_age else None,
                "stale":bool(observed and age>max_age),
                "source_method":"ALFRED_bootstrap_and_new_revised_observations"}
        results.append(result)
        key=(market_session,series["series_id"])
        if key in verify_checks:
            expected=verify_checks[key]
            if expected.get("http_status")!="ok":
                raise ValueError("existing_sample_audit_http_not_ok")
            rdate=expected.get("latest_observation_available_asof")
            rval=expected.get("latest_value_available_asof")
            ok=observed==rdate and ((observed is None and rval is None) or
                                     (rval is not None and abs(state[observed]-rval)<1e-5))
            if not ok:
                mismatch.append({"market_session":market_session,
                                 "series_id":series["series_id"],
                                 "computed_date":observed,"sampled_alfred_date":rdate,
                                 "computed_value":state.get(observed),
                                 "sampled_alfred_value":rval})
    return results,mismatch

def main():
    data=load("storage/phase2_joined_panel.json")
    checks=load("docs/phase3_vintage_audit.json")
    panel=data["rows"]
    dates=[r["date"] for r in panel]
    assert len(dates)==len(set(dates))==718
    checked={(r["market_session"],r["series_id"]):r for r in checks.get("checks",[])}
    assert len(checked)>=18, "required 18 prior independent as-of checks"
    api=API(os.getenv("FRED_API_KEY","").strip())
    existing=load("storage/phase3_fred_pit_vintages.json") if OUT.exists() else {"series":{}}
    completed=dict(existing.get("series",{}))
    reports={}
    for name,series_id in FACTORS.items():
        if name not in completed or completed[name].get("series_id")!=series_id:
            data_one=collect_one(api,name,series_id)
            constructed,mismatch=construct(data_one,dates,checked)
            if mismatch:
                reports[name]={"status":"blocked_sample_vintage_mismatch",
                               "mismatches":mismatch}
                print("PIT_SERIES_BLOCKED",name,"sample_mismatch",len(mismatch),flush=True)
                continue
            completed[name]=data_one
            save(OUT,{"schema_version":1,"window":[START,END],
                      "method":"FRED output_type=1 bootstrap plus output_type=3 new/revised vintage updates",
                      "series":completed,"publication_time_certified":False,
                      "full_model_backtest_authorized":False})
            reports[name]={"status":"validated_against_three_asof_samples",
                           "bootstrap":data_one["n_bootstrap"],"bootstrap_asof_date":data_one["bootstrap_date"],
                           "changes":data_one["n_changes"],
                           "valid_asof_dates":sum(r["value"] is not None for r in constructed)}
            print("PIT_SERIES_OK",name,
                  "updates",data_one["n_changes"],
                  "known",reports[name]["valid_asof_dates"],flush=True)
        else:
            constructed,mismatch=construct(completed[name],dates,checked)
            reports[name]={"status":"cached_validated" if not mismatch else "cached_mismatch",
                           "mismatches":mismatch,
                           "valid_asof_dates":sum(r["value"] is not None for r in constructed)}
    failures=[name for name in FACTORS if reports.get(name,{}).get("status") not in
              ("validated_against_three_asof_samples","cached_validated")]
    report={
        "status":"source_pit_collection_validated_sampled" if not failures else "blocked_partial_pit_collection",
        "window":[START,END],
        "comparison_method":"Every recovered 718-day series matched against existing independent ALFRED as-of samples (three per factor)",
        "series_status":reports,
        "api_requests_total":api.requests,
        "max_api_requests":MAX_REQUESTS,
        "missing_or_bad_series":failures,
        "limitations":[
            "Only 3 independent per-series date samples validated, though every series has vintage updates over full time window.",
            "ALFRED real-time dates are calendar dates, not source-specific intraday publication timestamps.",
            "Source H10, Treasury and weekly series publication behavior and holidays must be independently reviewed.",
            "Source data are not authorized for trading, TXF PnL or live risk recalibration."
        ],
        "full_model_backtest_authorized":False,
        "historical_pit_daily_panel_ready":not failures,
        "source_file_sha256":hashlib.sha256(OUT.read_bytes()).hexdigest() if OUT.exists() else None
    }
    save(REPORT,report)
    print("PIT_SOURCE_AUDIT",report["status"],"HTTP_requests",api.requests,"bad",failures,flush=True)
    if failures:
        raise SystemExit(2)

if __name__=="__main__":main()
