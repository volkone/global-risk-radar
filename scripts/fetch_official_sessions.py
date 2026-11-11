"""Derive actual historical TWSE sessions from official monthly FMTQIK reports.

This is an independent official trading activity source, not the two historical
margin/institutional datasets under audit. Reject unexpected dates and schemas.
"""
import csv
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"storage"/"official_calendar"
BASE="https://www.twse.com.tw/rwd/zh/indicesReport/FMTQIK"

def fetch_month(year,month):
    url=BASE+"?"+urllib.parse.urlencode({"response":"json","date":f"{year:04d}{month:02d}01"})
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as response:
        payload=json.load(response)
    if not isinstance(payload,dict) or not isinstance(payload.get("data"),list):
        raise ValueError(f"{year}-{month:02d}: missing official FMTQIK data")
    fields=payload.get("fields",[])
    if not fields or "日期" not in str(fields[0]):
        raise ValueError(f"{year}-{month:02d}: unexpected FMTQIK fields {fields}")
    sessions=set()
    for row in payload["data"]:
        raw=str(row[0]).strip()
        parts=raw.split("/")
        if len(parts)!=3:
            raise ValueError(f"invalid trading date {raw}")
        y,m,d=map(int,parts)
        if y<1911:y+=1911
        day=dt.date(y,m,d)
        if day.year!=year or day.month!=month or day.weekday()>4:
            raise ValueError(f"unexpected session {day} in {year}-{month:02d}")
        if day in sessions:
            raise ValueError(f"duplicate session {day}")
        sessions.add(day)
    if not 10<=len(sessions)<=23:
        raise ValueError(f"{year}-{month:02d}: implausible session count {len(sessions)}")
    return url,sessions

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    all_sessions=set()
    manifest={}
    for year in range(2023,2027):
        for month in range(1,13):
            if (year,month)<(2023,11) or (year,month)>(2026,10):
                continue
            url,sessions=fetch_month(year,month)
            all_sessions.update(sessions)
            manifest[f"{year}-{month:02d}"]={"source_url":url,"session_count":len(sessions)}
            print(f"{year}-{month:02d}: {len(sessions)} verified market sessions",flush=True)
            time.sleep(1.2)
    start,end=dt.date(2023,11,1),dt.date(2026,10,31)
    with (OUT/"trading_days.csv").open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["date","is_trading_day"])
        writer.writeheader()
        day=start
        while day<=end:
            writer.writerow({"date":day.isoformat(),"is_trading_day":int(day in all_sessions)})
            day+=dt.timedelta(days=1)
    (OUT/"source_manifest.json").write_text(json.dumps({"method":"TWSE official monthly FMTQIK trading activity","months":manifest},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Verified {len(all_sessions)} independent official sessions")
if __name__=="__main__":
    main()
