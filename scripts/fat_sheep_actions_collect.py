"""Collect official TWSE event discovery records. Never certify share basis from price data."""
import json, hashlib, re, time, calendar
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/fat_sheep/corporate_actions"
BASE="https://www.twse.com.tw/exchangeReport/"
AS_OF=date(2026,11,26)
FOCUS={"2542","2603","9904","9910","2881","2882","2887"}

def parse_day(s):
    m=re.fullmatch(r"\s*(\d{2,4})[年/\-](\d{1,2})[月/\-](\d{1,2})日?\s*",str(s))
    if not m: raise ValueError("unknown event date: "+str(s))
    y,mn,d=map(int,m.groups())
    return date(y+1911 if y<1911 else y,mn,d)

def parse_rows(payload,start,end,ids):
    if payload.get("stat")!="OK": raise ValueError("non-OK official response: "+str(payload.get("stat")))
    fields=payload.get("fields"); data=payload.get("data")
    if not isinstance(fields,list) or not isinstance(data,list): raise ValueError("unrecognized schema")
    keys=[str(k).strip() for k in fields]
    dkey=next((k for k in keys if k in ("資料日期","除權息日期","恢復買賣日期","日期")),None)
    ckey=next((k for k in keys if k in ("股票代號","證券代號")),None)
    if not dkey or not ckey: raise ValueError("required column missing")
    rows=[]; seen=set(); days=[]
    for row in data:
        if not isinstance(row,list) or len(row)!=len(keys): raise ValueError("row length mismatch")
        r=dict(zip(keys,row)); day=parse_day(r[dkey]); code=str(r[ckey]).strip()
        if not start<=day<=end: raise ValueError("response outside requested period")
        days.append(day)
        if code not in ids: continue
        signature=json.dumps(r,ensure_ascii=False,sort_keys=True)
        if signature in seen: raise ValueError("duplicate event row")
        seen.add(signature)
        rows.append({"code":code,"date":day.isoformat(),"raw":r,"event_factor_certified":False})
    return rows, len(data), sorted({d.isoformat() for d in days})

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    snap=json.loads((ROOT/"data/fat_sheep/holdings_2026-11-26.json").read_text())
    ids=set(snap["0050"]+snap["0051"])
    report={"as_of":str(AS_OF),"formal_ready":False,"event_coverage_certified":False,"share_basis_certified":False,"pit_certified":False,"requests":[]}
    events=[]
    jobs=[(kind,date(y,1,1),min(date(y,12,31),AS_OF)) for y in range(2021,2027) for kind in ("TWT49U","TWTAUU")]
    for kind,start,end in jobs:
        key=f"{kind}_{start.year}"
        query=urlencode({"response":"json","strDate":start.strftime("%Y%m%d"),"startDate":start.strftime("%Y%m%d"),"endDate":end.strftime("%Y%m%d")})
        url=BASE+kind+"?"+query
        record={"kind":kind,"start":str(start),"end":str(end),"url":url,"status":"failed"}
        report["requests"].append(record)
        try:
            with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=30) as response:
                raw=response.read(20_000_001)
            if len(raw)>20_000_000: raise ValueError("oversized")
            (OUT/(key+".json.raw")).write_bytes(raw)
            record.update(sha256=hashlib.sha256(raw).hexdigest(),fetched_at=datetime.now(timezone.utc).isoformat())
            payload=json.loads(raw)
            rows,n,days=parse_rows(payload,start,end,ids)
            for row in rows: row.update(source=key,source_sha256=record["sha256"])
            events.extend(rows)
            record.update(status="rows_received_range_checked",rows=n,matched=len(rows),first_day=days[0] if days else None,last_day=days[-1] if days else None,observed_dates=len(days),title=payload.get("title"),fields=payload.get("fields"))
        except HTTPError as e:
            record["error"]=str(e)
            if e.code==429:
                report["stop_reason"]="HTTP 429"
                break
        except (OSError,ValueError,TypeError) as e: record["error"]=str(e)
        finally:
            print(json.dumps(record,ensure_ascii=False),flush=True)
            (OUT/"audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
            time.sleep(5)
    report["requests_received"]=sum(r["status"]=="rows_received_range_checked" for r in report["requests"])
    report["events"]=len(events)
    report["focus_counts"]={c:sum(r["code"]==c for r in events) for c in sorted(FOCUS)}
    report["limitations"]=["Date bounds alone do not prove complete range coverage; server pagination and truncation must be audited.","No factor inferred from ex-right price.","Financial report publication dates, share-weighted EPS, merger comparability and official membership not certified."]
    (OUT/"events.json").write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding="utf8")
    (OUT/"audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if report["requests_received"]==len(jobs) else 1
if __name__=="__main__": raise SystemExit(main())
