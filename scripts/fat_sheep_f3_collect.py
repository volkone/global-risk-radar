"""F3-R pilot: dated official market closes and two missing cumulative income periods.
Fixed current universe; no historical membership/PIT certification or trading signals.
"""
import json, math, hashlib, time, zipfile, re
from pathlib import Path
from datetime import date, timedelta, datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from io import StringIO
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/fat_sheep/f3_research"
ASOF=date(2026,11,26)
SNAP=ROOT/"f3_inputs/snapshot"
MOPS="https://mopsov.twse.com.tw/mops/web/ajax_t163sb04"
TWSE="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
def number(v):
    n=float(str(v).replace(",","").strip())
    if not math.isfinite(n) or n<=0: raise ValueError("nonpositive/invalid close")
    return n
def date_key(x):
    s=str(x).replace("/","").replace("-","")
    if len(s)==7 and s.isdigit(): s=str(int(s[:3])+1911)+s[3:]
    return datetime.strptime(s,"%Y%m%d").date()
def parse_quotes(j,day,ids):
    if j.get("stat")!="OK": raise ValueError("official non-OK: "+str(j.get("stat")))
    if date_key(j.get("date",""))!=day: raise ValueError("response date mismatch")
    tables=list(j.get("tables",[]))
    for k,v in j.items():
        if re.fullmatch(r"fields\d+",k):
            tables.append({"fields":v,"data":j.get("data"+k[6:])})
    candidates=[t for t in tables if {"證券代號","收盤價"}.issubset(set(t.get("fields",[])))]
    if len(candidates)!=1: raise ValueError("ambiguous/missing quote table")
    t=candidates[0]; fields=t["fields"]; rows=t.get("data")
    if not isinstance(rows,list) or not rows: raise ValueError("empty quotes")
    prices={}; missing_values=[]; seen=set()
    for row in rows:
        if len(row)!=len(fields): raise ValueError("invalid quote row length")
        a=dict(zip(fields,row)); code=str(a["證券代號"]).strip()
        if code not in ids: continue
        if code in seen: raise ValueError("duplicate security "+code)
        seen.add(code)
        try: prices[code]=number(a["收盤價"])
        except (TypeError,ValueError): missing_values.append(code)
    return prices, sorted(ids-set(prices)), len(rows), missing_values

def parse_income(raw,quarter,ids):
    try: html=raw.decode("utf8")
    except UnicodeDecodeError: html=raw.decode("cp950")
    from bs4 import BeautifulSoup
    head=BeautifulSoup(html,"lxml").get_text(" ",strip=True)[:100]
    if "上市公司第"+("一" if quarter==1 else "二")+"季資料" not in head:
        raise ValueError("quarter header mismatch")
    rows={}
    for t in pd.read_html(StringIO(html),displayed_only=False):
        names=[str(x).replace(" ","") for x in t.columns]
        if not any("公司代號"==n for n in names): continue
        if not any("基本每股盈餘" in n for n in names): continue
        ci=names.index("公司代號")
        for vals in t.itertuples(index=False,name=None):
            code=str(vals[ci]).strip().removesuffix(".0")
            if code not in ids: continue
            if code in rows: raise ValueError("duplicate financial row "+code)
            rows[code]={"columns":[str(c) for c in t.columns],"values":[None if pd.isna(v) else str(v) for v in vals]}
    if not rows: raise ValueError("no financial rows")
    return rows,head

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    snap=json.loads((ROOT/"data/fat_sheep/holdings_2026-11-26.json").read_text())
    ids=set(snap["0050"]+snap["0051"]); assert len(ids)==150
    target=ids|{"0050"}
    oldaudit=json.loads((SNAP/"audit.json").read_text())
    raw0=(SNAP/"prices.raw").read_bytes()
    if hashlib.sha256(raw0).hexdigest()!=oldaudit["sources"]["prices"]["sha256"]: raise ValueError("archived quote hash mismatch")
    old={r["Code"]:number(r["ClosingPrice"]) for r in json.loads(raw0) if r["Code"] in ids and date_key(r["Date"])==ASOF}
    if len(old)!=150: raise ValueError("archived pilot universe incomplete")
    report={"as_of":str(ASOF),"formal_ready":False,"historical_membership_certified":False,"pit_certified":False,"requests":[],"pilot_pass":False,"period":"2026-07-02/2026-11-26","sampling":"Thursday close, descriptive weekly panel"}
    panel={}; inputs={}
    def save():
        (OUT/"audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
        (OUT/"prices.json").write_text(json.dumps(panel,ensure_ascii=False,indent=2),encoding="utf8")
    dates=[]; d=date(2026,7,2)
    while d<=ASOF: dates.append(d);d+=timedelta(days=7)
    jobs=[("price",ASOF)]+[("income",q) for q in (1,2)]+[("price",d) for d in dates if d!=ASOF]
    for kind,value in jobs:
        label=str(value); entry={"kind":kind,"period":label,"status":"failed"}
        report["requests"].append(entry)
        try:
            if kind=="price":
                url=TWSE+"?"+urlencode({"date":value.strftime("%Y%m%d"),"type":"ALLBUT0999","response":"json"})
                data=None
            else:
                url=MOPS
                data=urlencode({"encodeURIComponent":"1","step":"1","firstin":"1","off":"1","isQuery":"Y","TYPEK":"sii","year":"113","season":str(value).zfill(2)}).encode()
            entry["url"]=url
            if data: entry["request_body"]=data.decode()
            req=Request(url,data=data,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/html,*/*","Referer":MOPS.removeprefix("ajax_").replace("ajax_","")})
            with urlopen(req,timeout=35) as resp: raw=resp.read(20_000_001)
            if len(raw)>20_000_000: raise ValueError("oversized response")
            filename=f"{kind}_{label}.raw"; (OUT/filename).write_bytes(raw)
            entry.update(sha256=hashlib.sha256(raw).hexdigest(),fetched_at=datetime.now(timezone.utc).isoformat(),raw_file=filename)
            if kind=="price":
                p,missing,n,bad=parse_quotes(json.loads(raw),value,target)
                entry.update(rows=n,matched=len(p),missing=missing,invalid_closes=bad)
                if value==ASOF:
                    diffs={i:[old[i],p.get(i)] for i in ids if p.get(i)!=old[i]}
                    entry["archive_differences"]=diffs
                    if diffs or "0050" not in p: raise ValueError("pilot cross-check failed")
                    report["pilot_pass"]=True
                panel[label]=p
                entry["status"]="received"
            else:
                rows,head=parse_income(raw,value,ids)
                entry.update(status="received_unverified_period",matched=len(rows),missing=sorted(ids-set(rows)),header=head)
                (OUT/f"income_2024_{value}.rows.json").write_text(json.dumps(list(rows.values()),ensure_ascii=False,indent=2),encoding="utf8")
        except HTTPError as e:
            entry["error"]=str(e)
            if e.code==429: report["stop_reason"]="HTTP 429"; break
        except (ValueError,TypeError,KeyError,OSError) as e: entry["error"]=str(e)
        finally:
            print(json.dumps(entry,ensure_ascii=False),flush=True);save();time.sleep(5)
        if not report["pilot_pass"]:
            report["stop_reason"]="pilot failed";break
    report.update(requests_planned=len(jobs),received=sum(r["status"].startswith("received") for r in report["requests"]),quote_dates=len(panel),quote_rows=sum(map(len,panel.values())),limitations=["Fixed November 2026 universe has survivorship/look-ahead bias.","Missing or non-OK dates are not assumed holidays; no forward filling.","Financial query period and filing/revision timing remain unverified.","Weekly prices are raw closes; corporate action adjusted returns and disaster labels not certified."])
    save();print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if report["pilot_pass"] and report["received"]==len(jobs) else 1
if __name__=="__main__": raise SystemExit(main())
