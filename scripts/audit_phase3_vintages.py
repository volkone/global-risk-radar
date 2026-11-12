"""Phase 3 bounded ALFRED *as-of* vintage audit of the Phase 2 joined research panel.

A panel row's source observation date is NOT publication evidence. For each
sampled Taiwan market session, query the series as it was known on the
PREVIOUS calendar day via realtime_start=realtime_end. Fail closed on
missing API access, HTTP errors, revisions and late-arriving observations.
No API credentials, request URLs containing credentials, or raw responses
are written to reports.
"""
import datetime as dt
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PANEL=ROOT/"storage/phase2_joined_panel.json"
FACTORS=ROOT/"storage/historical_fred_factors.json"
OUT=ROOT/"docs/phase3_vintage_audit.json"
NAMES=("fx","hy","ig","vix","us10y","nfci")
SAMPLE_POSITIONS=(145,375,700)
REQUEST_DELAY=0.8
MAX_HTTP_REQUESTS=len(NAMES)*len(SAMPLE_POSITIONS)

def fetch_api(series_id,asof):
    key=os.environ["FRED_API_KEY"].strip()
    start=(dt.date.fromisoformat(asof)-dt.timedelta(days=35)).isoformat()
    args={
        "series_id":series_id,"api_key":key,"file_type":"json",
        "realtime_start":asof,"realtime_end":asof,
        "observation_start":start,"observation_end":asof
    }
    url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(args)
    time.sleep(REQUEST_DELAY)
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=25) as response:
        data=response.read(800_001)
    if len(data)>800_000:
        raise ValueError("response_size_over_limit")
    parsed=json.loads(data)
    if parsed.get("error_code"):
        raise ValueError("api_error_code_"+str(parsed["error_code"]))
    result={}
    for item in parsed.get("observations",[]):
        if item.get("value") not in (".","",None):
            result[item["date"]]=float(item["value"])
    return result

def main():
    pbytes=PANEL.read_bytes()
    panel=json.loads(pbytes)
    history=json.loads(FACTORS.read_text(encoding="utf-8"))["series"]
    rows=panel["rows"]
    assert len(rows)==718
    targets=[rows[i] for i in SAMPLE_POSITIONS]
    key=os.getenv("FRED_API_KEY","").strip()
    checks=[]
    if key:
        for target in targets:
            session=target["date"]
            asof=(dt.date.fromisoformat(session)-dt.timedelta(days=1)).isoformat()
            for name in NAMES:
                series_id=history[name]["series_id"]
                if name=="nfci":
                    # No NFCI signal was joined in Phase 2; probe only for release-lag evidence.
                    candidate=None
                    values={x["date"]:x["value"] for x in history[name]["history"]}
                    preceding=[d for d in values if d<session]
                    if preceding:
                        latest=max(preceding)
                        candidate={"observed_date":latest,"value":values[latest]}
                else:
                    candidate=target["us_previous_dated_observations"][name]
                srcdate=candidate["observed_date"] if candidate else None
                srcvalue=candidate["value"] if candidate else None
                row={"market_session":session,"asof_utc_calendar_date":asof,
                     "series_id":series_id,"factor":name,
                     "panel_candidate_observed_date":srcdate,
                     "panel_candidate_value":srcvalue,
                     "method":"FRED_ALFRED_realtime_start_equals_end",
                     "evidence_scope":"historical_calendar_date_only_not_exact_publish_time"}
                try:
                    asof_values=fetch_api(series_id,asof)
                    latest=max(asof_values) if asof_values else None
                    comparable=srcdate is not None and srcvalue is not None
                    present=comparable and srcdate in asof_values
                    equal=present and abs(asof_values[srcdate]-srcvalue) <= max(1e-6,abs(srcvalue)*1e-6)
                    row.update(http_status="ok",
                               latest_observation_available_asof=latest,
                               latest_value_available_asof=asof_values.get(latest) if latest else None,
                               candidate_observation_exists_asof=present if comparable else None,
                               candidate_value_equal_asof=equal if comparable else None,
                               violates_asof=(not present or not equal) if comparable else None)
                except Exception as exc:
                    row.update(http_status="error",error=type(exc).__name__+":"+str(exc)[:140],
                               candidate_observation_exists_asof=None,
                               candidate_value_equal_asof=None,violates_asof=None)
                checks.append(row)
                print("ALFRED_CHECK",session,name,row["http_status"],
                      "violates_asof",row["violates_asof"],flush=True)
    failures=[r for r in checks if r["violates_asof"] is True]
    errors=[r for r in checks if r["http_status"]!="ok"]
    result={"status":("probe_complete_with_violations" if failures else
                       "probe_complete_no_sampled_violations" if key and not errors else
                       "probe_incomplete_api_or_http"),
            "data_sha256":hashlib.sha256(pbytes).hexdigest(),
            "series_sample_size":len(checks),"max_http_requests":MAX_HTTP_REQUESTS,
            "dates_checked":[x["date"] for x in targets],
            "method":"FRED/ALFRED as-of previous calendar day relative to Taiwan market session",
            "violations_count":len(failures),"errors_count":len(errors),
            "by_factor_violations":{n:sum(r["factor"]==n for r in failures) for n in NAMES},
            "checks":checks,
            "important_limitations":[
                "Three sampled sessions per series are NOT a certification of all 718 sessions.",
                "FRED/ALFRED realtime date records do not certify intraday release timestamps.",
                "FRED vintage differences can reflect publication delay or subsequent revisions.",
                "NFCI was not used in the Phase 2 score; it is audited only for possible future model use.",
                "One check could omit current observations due to a historical data-service scope limitation.",
                "No model authorization from this probe."
            ],
            "full_model_backtest_authorized":False,"point_in_time_fully_verified":False,
            "live_threshold_changes_authorized":False}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("ALFRED_AUDIT",result["status"],"violations",len(failures),"errors",len(errors))

if __name__=="__main__":main()
