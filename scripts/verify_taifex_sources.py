"""Independently re-fetch TAIFEX source HTML and verify recorded SHA256 and OI values.
Run in bounded batches; never alter the collected observations.
"""
import argparse
import datetime as dt
import urllib.error
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from collect_taifex_three_year import ROOT, extract, atomic_json

DATA=ROOT/"storage/taifex_backfill.json"
OUT=ROOT/"docs/taifex_source_verification.json"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=100)
    p.add_argument("--timeout",type=int,default=12)
    a=p.parse_args()
    if not 1<=a.limit<=100 or not 1<=a.timeout<=30:p.error("limit must be 1..100 and timeout 1..30")
    records=json.loads(DATA.read_text(encoding="utf-8"))["records"]
    prior=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    checked=prior.get("results",{})
    expected={r["date"]:r for r in records}
    # Results are invalidated when a recorded hash or OI value changes.
    for date in list(checked):
        if date not in expected or checked[date].get("record_fingerprint")!=fingerprint(expected[date]):
            del checked[date]
    now=dt.datetime.now(dt.timezone.utc)
    retry_after=prior.get("retry_after_utc")
    if retry_after:
        try:
            if now < dt.datetime.fromisoformat(retry_after):
                print("TAIFEX cooldown active until",retry_after,flush=True)
                return
        except ValueError:
            pass
    # Do not let a previously rate-limited date block all fresh dates.
    pending=[r for r in records if r["date"] not in checked]
    retry=[r for r in records if checked.get(r["date"],{}).get("status") in
           ("fetch_or_parse_error","rate_limited")]
    batch=(pending+retry)[:a.limit]
    cooldown=None
    for r in batch:
        date=r["date"]
        result={"status":"blocked","record_fingerprint":fingerprint(r)}
        try:
            req=urllib.request.Request(r["source_url"],headers={
                "User-Agent":"Mozilla/5.0","Referer":"https://www.taifex.com.tw/cht/3/futContractsDate"})
            with urllib.request.urlopen(req,timeout=a.timeout) as response:
                if response.status!=200:raise ValueError(f"HTTP {response.status}")
                raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError("response exceeds 2MB limit")
            actual_hash=hashlib.sha256(raw).hexdigest()
            result["actual_sha256"]=actual_hash
            result["expected_sha256"]=r["source_sha256"]
            parsed=extract(raw,date,r["source_url"])
            fields=("value","long_oi","short_oi","scope","unit","provider")
            differences={k:{"expected":r.get(k),"actual":parsed.get(k)}
                         for k in fields if r.get(k)!=parsed.get(k)}
            if differences:result["differences"]=differences
            if actual_hash!=r["source_sha256"]:
                result["status"]="hash_mismatch"
            elif differences:
                result["status"]="value_mismatch"
            else:
                result["status"]="pass"
        except urllib.error.HTTPError as exc:
            if exc.code==429:
                result["status"]="rate_limited"
                result["error"]="HTTP 429 Too Many Requests"
                cooldown=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=30)).isoformat()
            else:
                result["status"]="fetch_or_parse_error"
                result["error"]=f"HTTP {exc.code}: {str(exc)[:200]}"
        except Exception as exc:
            result["status"]="fetch_or_parse_error"
            result["error"]=f"{type(exc).__name__}: {str(exc)[:250]}"
        checked[date]=result
        save(checked,expected,cooldown)
        print(date,result["status"],flush=True)
        if cooldown:
            print("Rate limited; pausing new requests until",cooldown,flush=True)
            break
        time.sleep(2.0)
    report=save(checked,expected,cooldown)
    print("source verification",report["status"],report["counts"],flush=True)

def fingerprint(r):
    keys=("date","source_url","source_sha256","value","long_oi","short_oi","scope","unit","provider")
    return hashlib.sha256(json.dumps({k:r.get(k) for k in keys},ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def save(results,expected,retry_after_utc=None):
    counts={k:sum(v["status"]==k for v in results.values()) for k in
            ("pass","hash_mismatch","value_mismatch","fetch_or_parse_error","rate_limited")}
    complete=len(expected)==len(results) and counts["pass"]==len(expected)
    report={"status":"pass" if complete else "blocked",
            "total_records":len(expected),"checked_records":len(results),
            "retry_after_utc":retry_after_utc,
            "counts":counts,"source_html_hashes_recomputed":complete,
            "full_model_backtest_authorized":False,
            "note":"Source verification only; backtest authorization requires a separate quality gate.",
            "results":dict(sorted(results.items()))}
    atomic_json(OUT,report)
    return report

if __name__=="__main__":main()
