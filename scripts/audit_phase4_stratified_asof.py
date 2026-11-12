"""Independent, deterministic historical ALFRED as-of checkpoint verification.

Queries a new, non-optimized stratified sample of Taiwan trading sessions,
compares directly fetched ALFRED past-vintage levels with the reconstructed
PIT series, and reports missing historical vintages separately from errors.
Does NOT claim 718-session independent verification or certify release hours.
"""
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
INPUT=ROOT/"storage/phase3_pit_joined_panel.json"
VINTAGES=ROOT/"storage/phase3_fred_pit_vintages.json"
OUTPUT=ROOT/"docs/phase4_stratified_asof_audit.json"
POSITIONS=(40,88,133,179,223,266,310,353,398,441,487,534,580,622,665,708)
MAX_ATTEMPTS=114
DELAY=0.48
FACTOR_IDS={"fx":"DEXTAUS","hy":"BAMLH0A0HYM2","ig":"BAMLC0A0CM",
            "vix":"VIXCLS","us10y":"DGS10","nfci":"NFCI"}

def load(rel):
    return json.loads((ROOT/rel).read_text(encoding="utf-8"))

def asof_fetch(secret,series,cutoff):
    start=(dt.date.fromisoformat(cutoff)-dt.timedelta(days=38)).isoformat()
    params={"series_id":series,"api_key":secret,"file_type":"json",
            "realtime_start":cutoff,"realtime_end":cutoff,
            "observation_start":start,"observation_end":cutoff}
    url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":"GlobalRiskRadar PIT validation",
                                          "Accept":"application/json"})
    for attempt in range(2):
        time.sleep(DELAY+attempt*1.7)
        try:
            with urllib.request.urlopen(req,timeout=20) as res:
                assert res.status==200
                raw=res.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError("unexpected_large_ALFRED_response")
            j=json.loads(raw)
            if not isinstance(j.get("observations"),list):
                raise ValueError("unexpected_ALFRED_observation_schema")
            values={}
            for x in j["observations"]:
                d=x.get("date")
                val=x.get("value")
                if not d or d>cutoff or val in (".","",None):continue
                f=float(val)
                if not math.isfinite(f):raise ValueError("nonfinite_value")
                if d in values:raise ValueError("duplicate_asof_observation_date")
                values[d]=f
            latest=max(values) if values else None
            return {"latest_observed_date":latest,
                    "latest_value":values.get(latest),
                    "response_sha256":hashlib.sha256(raw).hexdigest(),
                    "observation_count":len(values)}
        except urllib.error.HTTPError as e:
            if e.code in (400,401,403,404) or attempt==1:
                raise RuntimeError("ALFRED_HTTP_"+str(e.code)) from None
        except (urllib.error.URLError,TimeoutError) as e:
            if attempt==1:raise RuntimeError("ALFRED_NETWORK_"+type(e).__name__) from None
    raise AssertionError("unreachable")

def main():
    pbytes=INPUT.read_bytes()
    pit=json.loads(pbytes)
    vintages=load("storage/phase3_fred_pit_vintages.json")["series"]
    rows=pit["rows"]
    assert len(rows)==718 and pit["formal_backtest_authorized"] is False
    key=os.getenv("FRED_API_KEY","").strip()
    if not key:
        raise RuntimeError("FRED_API_KEY_missing")
    checks=[]
    requests=0
    for i in POSITIONS:
        r=rows[i]
        for factor,series in FACTOR_IDS.items():
            reconstructed=r["us_previous_dated_observations"][factor]
            cutoff=reconstructed["asof_us_calendar_date"]
            date=r["date"]
            if cutoff<vintages[factor]["bootstrap_date"]:
                checks.append({"date":date,"factor":factor,
                               "status":"unverifiable_before_first_available_ALFRED_vintage",
                               "asof":cutoff})
                continue
            if requests>=MAX_ATTEMPTS:
                raise RuntimeError("checkpoint_request_budget_exhausted")
            requests+=1
            item={"date":date,"factor":factor,"series_id":series,"asof":cutoff,
                  "reconstructed_observed_date":reconstructed["observed_date"],
                  "reconstructed_value":reconstructed["value"],
                  "reconstructed_is_stale":reconstructed["stale"]}
            try:
                direct=asof_fetch(key,series,cutoff)
                item.update({"direct_latest_observed_date":direct["latest_observed_date"],
                             "direct_latest_value":direct["latest_value"],
                             "response_sha256":direct["response_sha256"]})
                actual_date=direct["latest_observed_date"]
                actual_value=direct["latest_value"]
                # Stale reconstructed data deliberately has null value;
                # compare direct raw level/date but retain a staleness indicator.
                ok_date=actual_date==reconstructed["observed_date"]
                ok_value=(reconstructed["value"] is None and reconstructed["stale"] and
                          actual_date is not None) or (
                          actual_value is None and reconstructed["value"] is None) or (
                          actual_value is not None and reconstructed["value"] is not None and
                          abs(actual_value-reconstructed["value"])<=max(1e-6,abs(actual_value)*1e-7))
                item["status"]="pass" if ok_date and ok_value else "reconstructed_asof_disagreement"
            except Exception as e:
                item["status"]="source_fetch_failed"
                item["error"]=type(e).__name__+":"+str(e)[:120]
            checks.append(item)
            print("ASOF_CHECK",date,factor,item["status"],flush=True)
    counts={status:sum(x["status"]==status for x in checks) for status in
            ("pass","reconstructed_asof_disagreement",
             "source_fetch_failed","unverifiable_before_first_available_ALFRED_vintage")}
    report={
        "status":"stratified_asof_sample_pass" if counts["reconstructed_asof_disagreement"]==0
                 and counts["source_fetch_failed"]==0 and counts["pass"]>0
                 else "stratified_asof_sample_blocked",
        "sample_strategy":"Fixed 16 positions distributed across 718 Taiwan sessions; 6 series per sampled session",
        "sampled_market_sessions":[rows[i]["date"] for i in POSITIONS],
        "potential_checks":len(POSITIONS)*len(FACTOR_IDS),
        "http_requests":requests,"request_cap":MAX_ATTEMPTS,
        "counts":counts,
        "checks":checks,
        "pit_panel_sha256":hashlib.sha256(pbytes).hexdigest(),
        "independent_asof_verified_for_every_session":False,
        "historical_exact_release_timestamps_verified":False,
        "full_model_backtest_authorized":False,
        "live_threshold_changes_authorized":False
    }
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PHASE4_ASOF",report["status"],counts,"requests",requests,flush=True)
    if report["status"]!="stratified_asof_sample_pass":
        raise SystemExit(2)

if __name__=="__main__":
    main()
