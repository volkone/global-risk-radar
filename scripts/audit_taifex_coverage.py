"""TAIFEX TX foreign open-interest panel audit. Fail closed on incomplete history."""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
START="2023-11-11"
END="2026-11-11"

def audit(records, calendar_dates):
    errors=[]
    seen=set()
    observed=set()
    for r in records:
        date=r.get("date")
        if r.get("metric_id")!="inst.futures":
            errors.append("unexpected metric")
            continue
        try:
            parsed=dt.date.fromisoformat(date)
            if parsed.isoformat()!=date:raise ValueError()
        except (ValueError,TypeError):
            errors.append(f"invalid date {date}")
            continue
        if not START<=date<=END:
            errors.append(f"out-of-range date {date}")
        if date in seen:errors.append(f"duplicate {date}")
        seen.add(date)
        observed.add(date)
        long_oi,short_oi,net=r.get("long_oi"),r.get("short_oi"),r.get("value")
        if any(type(v) is not int for v in (long_oi,short_oi,net)) or (type(long_oi) is int and long_oi<0) or (type(short_oi) is int and short_oi<0) or (all(type(v) is int for v in (long_oi,short_oi,net)) and long_oi-short_oi!=net):
            errors.append(f"OI identity invalid {date}")
        if r.get("provider")!="TAIFEX" or r.get("unit")!="contracts":
            errors.append(f"provenance/unit invalid {date}")
    # TWSE is only a comparison reference, NOT a futures exchange calendar.
    common=observed & calendar_dates
    twse_without_futures=sorted(calendar_dates-observed)
    futures_without_twse=sorted(observed-calendar_dates)
    if not records:errors.append("TAIFEX history not imported")
    errors.append("independent TAIFEX trading-session calendar not yet verified")
    if twse_without_futures:errors.append(f"TWSE dates without futures observation: {len(twse_without_futures)}; requires independent futures-session classification")
    if futures_without_twse:errors.append(f"futures-only dates: {len(futures_without_twse)}; do not discard without exchange-calendar verification")
    return {"status":"pass" if not errors else "blocked","range":[START,END],"taifex_observations":len(records),"twse_sessions":len(calendar_dates),"joined_dates":len(common),"twse_dates_without_futures":twse_without_futures,"futures_dates_without_twse":futures_without_twse,"errors":errors,"futures_calendar_independently_verified":False,"full_model_backtest_authorized":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",type=Path,default=ROOT/"storage/taifex_backfill.json")
    p.add_argument("--calendar",type=Path,default=ROOT/"storage/official_calendar/trading_days.csv")
    p.add_argument("--output",type=Path,default=ROOT/"docs/taifex_coverage_audit.json")
    a=p.parse_args()
    records=json.loads(a.data.read_text(encoding="utf-8")).get("records",[]) if a.data.exists() else []
    with a.calendar.open(encoding="utf-8-sig",newline="") as f:
        dates={r["date"] for r in csv.DictReader(f) if r["is_trading_day"]=="1" and START<=r["date"]<=END}
    result=audit(records,dates)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("TAIFEX audit:",result["status"],"rows:",len(records),"missing TWSE joins:",len(result["twse_dates_without_futures"]))
    if result["status"]!="pass":raise SystemExit(1)
if __name__=="__main__":main()
