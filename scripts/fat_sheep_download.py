"""Download official current snapshots; never certify historical PIT from snapshots."""
import json, hashlib, time, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/fat_sheep/download"
BASE="https://openapi.twse.com.tw/v1/"
SOURCES={"companies":"opendata/t187ap03_L","prices":"exchangeReport/STOCK_DAY_ALL","valuation":"exchangeReport/BWIBBU_ALL","dividends":"opendata/t187ap45_L"}
for kind in ("ci","basi","fh","ins","bd","mim"):
    SOURCES["income_"+kind]="opendata/t187ap06_L_"+kind
    SOURCES["balance_"+kind]="opendata/t187ap07_L_"+kind

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    snapshot=json.loads((ROOT/"data/fat_sheep/holdings_2026-11-26.json").read_text())
    ids=set(snapshot["0050"]+snapshot["0051"])
    report={"snapshot_date":snapshot["as_of"],"membership_certified":False,"target_count":len(ids),"sources":{},"formal_screen_ready":False,"historical_pit_ready":False}
    coverage={i:[] for i in sorted(ids)}
    date_errors={}
    duplicates={}
    def iso_day(value):
        s=str(value).strip().replace("/","").replace("-","")
        if len(s)==7 and s.isdigit(): s=str(int(s[:3])+1911)+s[3:]
        return datetime.strptime(s,"%Y%m%d").date().isoformat()
    for key,path in SOURCES.items():
        url=BASE+path
        entry={"url":url,"status":"failed"}
        report["sources"][key]=entry
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"FatSheepResearch/1.0","Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=25) as response:
                raw=response.read(30_000_001)
            if len(raw)>30_000_000: raise ValueError("response too large")
            (OUT/(key+".raw")).write_bytes(raw)
            entry.update(sha256=hashlib.sha256(raw).hexdigest(),fetched_at=datetime.now(timezone.utc).isoformat())
            rows=json.loads(raw)
            if not isinstance(rows,list) or not rows or not all(isinstance(r,dict) for r in rows): raise ValueError("empty or invalid rows")
            matched=set()
            counts=Counter()
            dates=Counter()
            bad_dates=[]
            for r in rows:
                code=str(r.get("公司代號",r.get("證券代號",r.get("Code",r.get("股票代號",""))))).strip()
                if code in ids:
                    matched.add(code)
                    counts[code]+=1
                    if key in ("prices","valuation"):
                        try: day=iso_day(r.get("Date",""))
                        except ValueError: day="invalid"
                        dates[day]+=1
                        if day!=snapshot["as_of"]: bad_dates.append(code)
            if key in ("prices","valuation"):
                entry["matched_dates"]=dict(dates)
                date_errors[key]=sorted(set(bad_dates))
            if key!="dividends":
                duplicates[key]=sorted(code for code,n in counts.items() if n>1)
            for code in matched: coverage[code].append(key)
            entry.update(status="snapshot_received",rows=len(rows),matched=len(matched),fields=sorted(set().union(*(r.keys() for r in rows))))
        except urllib.error.HTTPError as e:
            entry["error"]=str(e)
            if e.code==429:
                report["stopped"]="rate_limit"
                break
        except (OSError,ValueError) as e: entry["error"]=str(e)
        finally: time.sleep(2)
    report["coverage"]=coverage
    report["date_errors"]=date_errors
    report["duplicates"]=duplicates
    report["missing_by_group"]={
        group:[i for i,keys in coverage.items() if not any(k.startswith(prefix) for k in keys)]
        for group,prefix in (("companies","companies"),("prices","prices"),("valuation","valuation"),("dividends","dividends"),("income","income_"),("balance","balance_"))
    }
    report["cross_category_overlap"]={
        prefix:[i for i,keys in coverage.items() if sum(k.startswith(prefix) for k in keys)>1]
        for prefix in ("income_","balance_")
    }
    report["transport_complete"]=len(report["sources"])==len(SOURCES) and all(v["status"]=="snapshot_received" for v in report["sources"].values())
    report["snapshot_checks_passed"]=report["transport_complete"] and len(ids)==150 and not any(report["missing_by_group"].values()) and not any(date_errors.values()) and not any(duplicates.values()) and not any(report["cross_category_overlap"].values())
    report["blockers"]=["official index membership not certified","historical five-year and eight-quarter records not certified","publication dates and share basis not certified","snapshot dates and financial values need validation"]
    (OUT/"audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="coverage"},ensure_ascii=False))
    return 0 if report["snapshot_checks_passed"] else 1
if __name__=="__main__": raise SystemExit(main())
