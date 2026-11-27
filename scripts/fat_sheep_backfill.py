"""Collect historical official MOPS tables as research evidence, not PIT certification."""
import hashlib, json, re, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone
from pathlib import Path
from io import StringIO
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/fat_sheep/history"
BASE="https://mopsov.twse.com.tw/mops/web/"
MISSING={"2881","2882","2884","2887","2892"}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    snap=json.loads((ROOT/"data/fat_sheep/holdings_2026-11-26.json").read_text())
    ids=set(snap["0050"]+snap["0051"])
    income={(y,4) for y in range(2021,2026)}|{(y,q) for y in range(2024,2027) for q in range(1,5) if (2024,3)<=(y,q)<=(2026,3)}
    jobs=[("income",y,q,"ajax_t163sb04") for y,q in sorted(income,reverse=True)]
    jobs += [("balance",y,4,"ajax_t163sb05") for y in range(2025,2019,-1)]
    jobs.insert(1,("balance",2026,3,"ajax_t163sb05"))
    jobs += [("dividend",y,0,"ajax_t05st09") for y in range(2025,2020,-1)]
    report={"formal_screen_ready":False,"pit_certified":False,"target_count":len(ids),"expected_requests":len(jobs),"results":[]}
    for kind,y,q,endpoint in jobs:
        name=f"{kind}_{y}_{q}"
        form={"encodeURIComponent":"1","step":"1","firstin":"1","off":"1","isQuery":"Y","TYPEK":"sii","year":str(y-1911),"season":str(q).zfill(2)}
        if kind=="dividend": form.update(YEAR=str(y-1911));form.pop("season")
        url=BASE+endpoint
        entry={"kind":kind,"year":y,"quarter":q,"url":url,"form":form,"status":"failed"}
        report["results"].append(entry)
        try:
            req=urllib.request.Request(url,data=urllib.parse.urlencode(form).encode(),headers={"User-Agent":"FatSheepResearch/1.0","Content-Type":"application/x-www-form-urlencoded","Referer":BASE+endpoint.removeprefix("ajax_")})
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read(20_000_001)
            if len(raw)>20_000_000: raise ValueError("oversized response")
            (OUT/(name+".html")).write_bytes(raw)
            entry.update(sha256=hashlib.sha256(raw).hexdigest(),fetched_at=datetime.now(timezone.utc).isoformat())
            html=raw.decode("utf-8",errors="replace")
            if any(s in html for s in ("查詢過於頻繁","您的查詢過於頻繁","請稍後再試")):
                report["stop_reason"]="server throttled"
                break
            tables=pd.read_html(StringIO(html),displayed_only=False)
            found=set(); selected=[]
            for t in tables:
                for row in t.itertuples(index=False,name=None):
                    codes={str(v).strip() for v in row[:2]}
                    codes={v.removesuffix(".0") for v in codes}
                    matches=codes & ids
                    if matches:
                        found.update(matches)
                        selected.append({"columns":[str(c) for c in t.columns],"values":[None if pd.isna(v) else str(v) for v in row]})
            if not found: raise ValueError("no matching stock rows")
            (OUT/(name+".rows.json")).write_text(json.dumps(selected,ensure_ascii=False),encoding="utf-8")
            entry.update(status="rows_received_unverified_period",matched=len(found),missing=sorted(ids-found),missing_financial_recovery=sorted(MISSING&found))
        except urllib.error.HTTPError as e:
            entry["error"]=str(e)
            if e.code==429: report["stop_reason"]="HTTP 429";break
        except Exception as e: entry["error"]=str(e)
        finally: time.sleep(5)
    (OUT/"audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    # Collection alone cannot establish filing dates, requested-period identity or accounting basis.
    return 0 if len(report["results"])==len(jobs) and all(r["status"]=="rows_received_unverified_period" and not r["missing"] for r in report["results"]) else 1

if __name__=="__main__": raise SystemExit(main())
