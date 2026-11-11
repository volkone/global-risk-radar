"""Independent final TWSE panel quality gate; no inference or silent repair."""
import csv
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
METRICS={"margin.margin","inst.cash_inst"}
START,END="2023-11-01","2026-10-31"

def validate(history,calendar,manifest):
    records=history.get("records",[])
    months=manifest.get("months",{})
    if len(months)!=36 or any(not x.get("source_url","").startswith("https://www.twse.com.tw/") for x in months.values()):
        raise ValueError("official 36-month provenance incomplete")
    sessions=set()
    dates=set()
    for row in calendar:
        day=dt.date.fromisoformat(row["date"])
        key=day.isoformat()
        if key in dates: raise ValueError("duplicate calendar date")
        dates.add(key)
        if row["is_trading_day"] not in ("0","1"):raise ValueError("invalid calendar flag")
        if row["is_trading_day"]=="1": sessions.add(key)
    expected={(dt.date.fromisoformat(START)+dt.timedelta(days=i)).isoformat() for i in range((dt.date.fromisoformat(END)-dt.date.fromisoformat(START)).days+1)}
    if dates!=expected:raise ValueError("calendar coverage not exact")
    if len(sessions)!=sum(x["session_count"] for x in months.values()):
        raise ValueError("calendar/manifest session count mismatch")
    seen=set()
    problems=[]
    counts=Counter()
    for r in records:
        metric,date=r.get("metric_id"),r.get("date")
        if metric not in METRICS or not START<=str(date)<=END:continue
        key=(metric,date)
        if key in seen:problems.append(f"duplicate {key}")
        seen.add(key)
        counts[metric]+=1
        if date not in sessions:problems.append(f"off-session {key}")
        if r.get("provider")!="TWSE" or r.get("unit")!="TWD" or r.get("scope")!="TWSE上市市場":
            problems.append(f"scope/provider/unit {key}")
        value=r.get("value")
        if isinstance(value,bool) or not isinstance(value,int) or (metric=="margin.margin" and value<=0):
            problems.append(f"invalid value {key}")
        url=r.get("source_url","")
        if not url.startswith("https://www.twse.com.tw/") or date.replace("-","") not in url:
            problems.append(f"source/date provenance {key}")
    for metric in sorted(METRICS):
        missing=sorted(sessions-{d for m,d in seen if m==metric})
        if missing:problems.append(f"{metric}: {len(missing)} missing: {missing[:10]}")
    return {"status":"pass" if not problems else "blocked","period":[START,END],"official_sessions":len(sessions),"metric_counts":dict(counts),"observations":sum(counts.values()),"problems":problems,"taifex_imported":False,"full_model_backtest_authorized":False}

def main():
    history_path=ROOT/"storage/twse_backfill.json"
    cal_path=ROOT/"storage/official_calendar/trading_days.csv"
    manifest_path=ROOT/"storage/official_calendar/source_manifest.json"
    with cal_path.open(encoding="utf-8-sig",newline="") as f:calendar=list(csv.DictReader(f))
    history=json.loads(history_path.read_text(encoding="utf-8"))
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    result=validate(history,calendar,manifest)
    result["sha256"]={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (history_path,cal_path,manifest_path)}
    out=ROOT/"docs/twse_final_quality_gate.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("TWSE quality gate:",result["status"],"observations:",result["observations"],"problems:",result["problems"][:5])
    if result["status"]!="pass":raise SystemExit(1)
if __name__=="__main__":main()
