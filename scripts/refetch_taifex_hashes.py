"""Independent TAIFEX TXF source re-download, raw SHA and parsed value audit.
Preserve raw hash differences; never silently accept changed source values.
"""
import argparse
import datetime as dt
import hashlib
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from collect_taifex_three_year import extract

ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--limit",type=int,default=10)
 p.add_argument("--pause",type=float,default=3.0)
 p.add_argument("--timeout",type=int,default=12)
 p.add_argument("--retry-after-hours",type=float,default=24.0)
 a=p.parse_args()
 if not 1<=a.limit<=20 or a.pause<2:raise SystemExit("limit must be 1..20 and pause >=2s")
 records=json.loads((ROOT/"storage/taifex_backfill.json").read_text(encoding="utf-8"))["records"]
 out=ROOT/"storage/verification/taifex_sha256_recheck.json"
 out.parent.mkdir(parents=True,exist_ok=True)
 try:state=json.loads(out.read_text(encoding="utf-8"))
 except FileNotFoundError:state={"schema_version":2,"records":{}}
 # A corrupt existing ledger is a hard failure: never discard verification evidence.
 state["schema_version"]=2
 done=state["records"]
 attempted=0
 for rec in records:
  d=rec["date"]
  previous=done.get(d,{})
  if previous.get("status")=="match" and previous.get("actual_sha256")==rec["source_sha256"] and previous.get("parsed_values_match") is not False:
   if previous.get("parsed_values_match") is not False:
    previous["parsed_values_match"]=True
   previous["verification_basis"]="raw_sha256_exact_match"
   continue
  if previous.get("parsed_values_match") is True and previous.get("status") in ("match","mismatch"):
   continue
  if previous.get("status")=="rate_limited":
   last=dt.datetime.fromisoformat(previous["verified_at_utc"])
   if (dt.datetime.now(dt.timezone.utc)-last).total_seconds()<a.retry_after_hours*3600:
    continue
  if previous.get("status")=="fetch_error" and previous.get("error")=="ValueError":continue  # investigate source date before retry
  if previous.get("error_detail","").startswith("HTTP Error 429"):
   last=dt.datetime.fromisoformat(previous["verified_at_utc"])
   if (dt.datetime.now(dt.timezone.utc)-last).total_seconds()<a.retry_after_hours*3600:
    continue
  if attempted>=a.limit:break
  attempted+=1
  try:
   req=urllib.request.Request(rec["source_url"],headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.taifex.com.tw/cht/3/futContractsDate"})
   with urllib.request.urlopen(req,timeout=a.timeout) as res:
    body=res.read(2_000_000)
    status=res.status
   actual=hashlib.sha256(body).hexdigest()
   expected=rec["source_sha256"]
   parsed=extract(body,d,rec["source_url"])
   fields=("date","long_oi","short_oi","value","scope","unit")
   matches=all(parsed.get(k)==rec.get(k) for k in fields)
   result={"status":"match" if actual==expected else "mismatch",
           "parsed_values_match":matches,
           "verification_basis":"raw_sha256_exact_match" if actual==expected else "independent_parsed_row_comparison",
           "parsed":{k:parsed.get(k) for k in fields},
           "expected_values":{k:rec.get(k) for k in fields},
           "expected_sha256":expected,"actual_sha256":actual,
           "http_status":status,"bytes":len(body),"source_url":rec["source_url"],
           "verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
  except urllib.error.HTTPError as exc:
   if exc.code==429:
    done[d]={"status":"rate_limited","http_status":429,"source_url":rec["source_url"],"verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
    out.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Official source rate limit 429: stopping batch without retry",flush=True)
    break
   result={"status":"fetch_error","parsed_values_match":False,"error":"HTTPError","error_detail":str(exc)[:160],"source_url":rec["source_url"],"verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
  except Exception as exc:
   result={"status":"fetch_error","parsed_values_match":False,"error":type(exc).__name__,"error_detail":str(exc)[:160],"source_url":rec["source_url"],"verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
  done[d]=result
  out.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  if attempted%5==0:print("Checked",attempted,"this run",flush=True)
  time.sleep(a.pause)
 total=len(records)
 counts={s:sum(x.get("status")==s for x in done.values()) for s in ("match","mismatch","fetch_error","rate_limited")}
 semantic=sum(x.get("parsed_values_match") is True for x in done.values())
 report={"schema_version":2,"dataset":"TAIFEX TXF official historical source HTML",
         "expected_records":total,"attempted_this_run":attempted,"checked":len(done),
         "counts":counts,"semantic_values_verified":semantic,"semantic_values_unverified":total-semantic,
         "raw_hash_mismatch_dates":[d for d,x in done.items() if x.get("status")=="mismatch"],
         "discrepancy_dates":[d for d,x in done.items() if x.get("status")=="mismatch" or (x.get("status")=="match" and x.get("parsed_values_match") is False)],
         "unverified_dates":[d for d,x in done.items() if x.get("status") in ("fetch_error","rate_limited")],
         "all_raw_hashes_verified":counts["match"]==total and counts["mismatch"]==0,
         "all_values_independently_verified":semantic==total,
         "source_rate_limited":counts["rate_limited"]>0,
         "retries_paused_until_manual_review":counts["rate_limited"]>0,
         "limitations":["Raw HTML SHA mismatch is not equivalent to a data mismatch.","Original HTML bytes were not archived; precise HTML diff is not possible without them."]}
 (ROOT/"docs/taifex_raw_hash_recheck.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
