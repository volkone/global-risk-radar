"""Phase 5: first-seen daily evidence for forward-only risk research.

Only the exact current Taiwan calendar date can become a prospective snapshot.
Every source is captured with fetch timestamps and response hashes. Missing,
late, malformed or historical responses are explicitly rejected. Probe mode
is read-only with respect to prospective samples. Never send live alerts.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from backfill_twse import parse_margin, parse_cash, parse_roc_date
from collect_taifex_three_year import extract as extract_tx

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Taipei")
US=ZoneInfo("America/New_York")
PROTOCOL=ROOT/"docs/phase4_frozen_prospective_protocol.json"
SNAPSHOTS=ROOT/"storage/prospective/snapshots"
ATTEMPTS=ROOT/"storage/prospective/attempts"
LATEST=ROOT/"docs/phase5_forward_capture_latest.json"
FRED={
    "fx":"DEXTAUS","hy":"BAMLH0A0HYM2","ig":"BAMLC0A0CM",
    "vix":"VIXCLS","us10y":"DGS10","nfci":"NFCI"
}
REQUIRED=("taiex","margin","cash_inst","tx_oi","fx","hy","vix")
MAX_REQUESTS=11

def utcnow():
    return dt.datetime.now(dt.timezone.utc)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(obj):
    return (json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")

def write_once(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open("xb") as f:
            f.write(canonical(obj))
        return True
    except FileExistsError:
        return False

def write_latest(obj):
    LATEST.parent.mkdir(parents=True,exist_ok=True)
    LATEST.write_bytes(canonical(obj))

def verify_frozen():
    frozen=json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert frozen["status"]=="preregistered_research_protocol_awaiting_genuinely_unseen_future_market_data"
    assert frozen["formal_full_model_backtest_authorized"] is False
    assert frozen["live_threshold_changes_authorized"] is False
    for file,expected in frozen["frozen_artifact_sha256"].items():
        assert sha((ROOT/file).read_bytes())==expected, "frozen_reference_mutated:"+file
    assert frozen["post_close_feature_action_lag_taiwan_sessions"]==2
    return frozen

def parse_fmtqik(raw,day):
    obj=json.loads(raw)
    fields=obj.get("fields",[])
    rows=obj.get("data",[])
    if not isinstance(fields,list) or not isinstance(rows,list):
        raise ValueError("FMTQIK_table_absent")
    dc=next((i for i,s in enumerate(fields) if str(s).strip()=="日期"),None)
    pc=next((i for i,s in enumerate(fields) if "發行量加權股價指數" in str(s)),None)
    if dc is None or pc is None:raise ValueError("FMTQIK_index_or_date_missing")
    sessions={}
    for row in rows:
        if not isinstance(row,list) or len(row)<=max(dc,pc):
            raise ValueError("FMTQIK_bad_row")
        d=parse_roc_date(str(row[dc]))
        if not d or d[:7]!=day[:7] or d in sessions:
            raise ValueError("FMTQIK_bad_or_duplicated_date")
        v=float(str(row[pc]).replace(",",""))
        if not math.isfinite(v) or not 1000<v<100000:
            raise ValueError("FMTQIK_price_invalid")
        sessions[d]=round(v,2)
    if not sessions:raise ValueError("FMTQIK_no_market_rows")
    if any(d>day for d in sessions):
        raise ValueError("FMTQIK_future_session_in_response")
    return sessions.get(day),sorted(sessions)

def parse_fred(raw,series,us_today):
    data=json.loads(raw)
    if not isinstance(data.get("observations"),list):
        raise ValueError("FRED_wrong_schema")
    values={}
    for entry in data["observations"]:
        day=entry.get("date")
        val=entry.get("value")
        if not day or val in (None,"","."):continue
        dt.date.fromisoformat(day)
        if day>us_today or day in values:
            raise ValueError("FRED_future_or_duplicate_observation")
        number=float(val)
        if not math.isfinite(number):raise ValueError("FRED_nonfinite")
        values[day]=number
    if not values:raise ValueError("FRED_no_observations")
    day=max(values)
    max_age=21 if series in ("DEXTAUS","NFCI") else 7
    age=(dt.date.fromisoformat(us_today)-dt.date.fromisoformat(day)).days
    if age>max_age:raise ValueError("FRED_observation_too_stale:"+str(age))
    return {"observed_date":day,"value":values[day],
            "age_us_calendar_days":age,"series_id":series,
            "source_clock_certified":False}

class Fetcher:
    def __init__(self):
        self.total=0
    def get(self,url,public_url):
        if self.total>=MAX_REQUESTS:raise RuntimeError("maximum_request_budget_exhausted")
        self.total+=1
        time.sleep(0.6)
        req=urllib.request.Request(url,headers={
            "User-Agent":"Mozilla/5.0 GlobalRiskRadar-PITResearch",
            "Accept":"application/json,text/html,*/*"})
        for attempt in (0,1):
            try:
                with urllib.request.urlopen(req,timeout=24) as resp:
                    if resp.status!=200:raise ValueError("HTTP_status_not_200")
                    raw=resp.read(1_500_001)
                if len(raw)>1_500_000:raise ValueError("source_response_over_1.5MB")
                return raw,{"source_url":public_url,"response_sha256":sha(raw),
                            "bytes":len(raw),"fetched_at_utc":utcnow().isoformat()}
            except Exception as exc:
                if attempt==1:raise
                time.sleep(1.5)
        raise AssertionError("unreachable")

def gather(day,started):
    results={}
    errors={}
    calls=Fetcher()
    us_today=utcnow().astimezone(US).date().isoformat()
    month=day.replace("-","")[:6]
    # TWSE current month's activity is the independently observed market-session list.
    tw_url="https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?"+urllib.parse.urlencode(
        {"response":"json","date":month+"01"})
    def collect(name,url,parse,public_url=None):
        try:
            raw,provenance=calls.get(url,public_url or url)
            val=parse(raw)
            results[name]={"value":val,**provenance}
        except Exception as exc:
            errors[name]=type(exc).__name__+":"+str(exc)[:160]
    collect("taiex",tw_url,lambda b: parse_fmtqik(b,day))
    # At month boundaries obtain the final prior-month trading-session list.
    # This detects missing last-of-month sessions even if no snapshot was
    # collected on the final business day. It is source evidence, not a
    # backdated prospective forecast or first-seen historical market data.
    if int(day[-2:])<=8:
        previous_end=dt.date.fromisoformat(day[:7]+"-01")-dt.timedelta(days=1)
        prior_day=previous_end.isoformat()
        prior_month=prior_day.replace("-","")[:6]
        previous_url="https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?"+urllib.parse.urlencode(
            {"response":"json","date":prior_month+"01"})
        collect("previous_month_calendar",previous_url,
                lambda blob: parse_fmtqik(blob,prior_day))
    datearg=day.replace("-","")
    margin_url="https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?"+urllib.parse.urlencode(
        {"date":datearg,"selectType":"ALL","response":"json"})
    collect("margin",margin_url,lambda b: check_twse_day(
        parse_margin(json.loads(b),day[:7]),day))
    cash_url="https://www.twse.com.tw/rwd/zh/fund/BFI82U?"+urllib.parse.urlencode(
        {"dayDate":datearg,"type":"day","response":"json"})
    collect("cash_inst",cash_url,lambda b: check_twse_day(
        parse_cash(json.loads(b),day[:7]),day))
    tx_url="https://www.taifex.com.tw/cht/3/futContractsDate?"+urllib.parse.urlencode(
        {"queryDate":day.replace("-","/"),"commodityId":"TXF","queryType":"1"})
    collect("tx_oi",tx_url,lambda b: extract_tx(b,day,tx_url))
    key=os.getenv("FRED_API_KEY","").strip()
    if not key:
        errors.update({"fred_"+k:"FRED_API_KEY_unconfigured" for k in FRED})
    else:
        beginning=(dt.date.fromisoformat(us_today)-dt.timedelta(days=33)).isoformat()
        for name,series in FRED.items():
            params={"series_id":series,"api_key":key,"file_type":"json",
                    "observation_start":beginning,"observation_end":us_today,
                    "realtime_start":us_today,"realtime_end":us_today}
            url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(params)
            collect(name,url,lambda b,s=series:parse_fred(b,s,us_today),
                    "https://fred.stlouisfed.org/series/"+series)
    # Reject a future price table / wrong reporting day. Holidays stay attempts,
    # not a fabricated trading-day record.
    status=("complete" if all(k in results for k in REQUIRED) and
            results["taiex"]["value"][0] is not None
            else "incomplete_or_not_trading_session")
    return {
        "status":status,"session_date":day,"started_at_utc":started.isoformat(),
        "completed_at_utc":utcnow().isoformat(),"us_calendar_date_at_collection":us_today,
        "sources":results,"errors":errors,"requests":calls.total,
        "required_sources":list(REQUIRED),
        "source_clock_certified_for_all_factors":False,
        "official_taifex_calendar_independently_signed_off":False,
        "no_alerts_or_trading_actions":True
    }

def check_twse_day(parsed,day):
    if len(parsed)!=1 or parsed[0]["date"]!=day:
        raise ValueError("TWSE_returned_unrequested_date")
    return parsed[0]

def self_test():
    sample={"fields":["日期","發行量加權股價指數"],
            "data":[["115/11/13","21,234.25"],["115/11/12","21,240.30"]]}
    price,days=parse_fmtqik(canonical(sample),"2026-11-13")
    assert price==21234.25 and days==["2026-11-12","2026-11-13"]
    assert parse_fmtqik(canonical(sample),"2026-11-14")[0] is None
    try:
        parse_fmtqik(canonical(sample),"2026-11-12")
        raise AssertionError("lookahead source date accepted")
    except ValueError as exc:
        assert "future_session" in str(exc)
    raw=canonical({"observations":[{"date":"2026-11-10","value":"32.1"},
                                    {"date":"2026-11-11","value":"."}]})
    assert parse_fred(raw,"DEXTAUS","2026-11-12")["observed_date"]=="2026-11-10"
    try:
        parse_fred(raw,"DEXTAUS","2026-11-09")
        raise AssertionError("future FRED observation accepted")
    except ValueError as exc:
        assert "future" in str(exc)
    assert verify_frozen()["first_prospective_session_not_used_in_research"]=="2026-11-13"
    print("PHASE5_SELF_TEST pass - source dates, future rejection, frozen SHA256")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("selftest","probe","capture"),required=True)
    args=p.parse_args()
    if args.mode=="selftest":
        self_test()
        return
    frozen=verify_frozen()
    started=utcnow()
    now=started.astimezone(TZ)
    date=now.date().isoformat()
    if args.mode=="capture" and (
        date<frozen["first_prospective_session_not_used_in_research"] or
        now.hour<20 or now.weekday()>=5):
        write_latest({"status":"not_eligible_for_capture",
                      "reason":"before cohort start, before local 20:00 or non-weekday",
                      "checked_at_utc":started.isoformat(),"date":date,
                      "prospective_snapshot_created":False})
        print("PHASE5_NOT_ELIGIBLE",date)
        return
    path=SNAPSHOTS/(date+".json")
    if args.mode=="capture" and path.exists():
        print("PHASE5_ALREADY_RECORDED",date,"immutable snapshot preserved")
        return
    evidence=gather(date,started)
    evidence["frozen_protocol_sha256"]=sha(PROTOCOL.read_bytes())
    evidence["github_run_id"]=os.getenv("GITHUB_RUN_ID","")
    evidence["data_first_seen_at"]=evidence["completed_at_utc"]
    if args.mode=="capture":
        if evidence["status"]=="complete":
            evidence["snapshot_kind"]="prospective_first_seen"
            evidence["formal_model_backtest_authorized"]=False
            evidence["alert_threshold_is_research_only"]=True
            created=write_once(path,evidence)
            evidence["canonical_snapshot_path"]=str(path.relative_to(ROOT)) if created else None
            evidence["status"]="prospective_snapshot_created" if created else "existing_snapshot_preserved"
        else:
            evidence["snapshot_kind"]="capture_attempt_not_prospective_training_data"
            attempt_id=os.getenv("GITHUB_RUN_ID","local")+"_"+os.getenv("GITHUB_RUN_ATTEMPT","1")
            path=ATTEMPTS/date/(attempt_id+".json")
            write_once(path,evidence)
            evidence["status"]="capture_incomplete_recorded_as_attempt"
    else:
        evidence["snapshot_kind"]="probe_only_never_prospective_data"
        evidence["status"]="probe_"+evidence["status"]
    summary={k:v for k,v in evidence.items() if k!="sources"}
    summary["captured_sources"]={k:{"observed_date":v["value"].get("observed_date")
          if isinstance(v["value"],dict) else date,
          "fetched_at_utc":v["fetched_at_utc"],
          "response_sha256":v["response_sha256"]} for k,v in evidence["sources"].items()}
    summary["prospective_snapshot_created"]=evidence["status"]=="prospective_snapshot_created"
    write_latest(summary)
    print("PHASE5_CAPTURE",summary["status"],date,
          "sources",len(evidence["sources"]),"errors",evidence["errors"],flush=True)

if __name__=="__main__":
    main()
