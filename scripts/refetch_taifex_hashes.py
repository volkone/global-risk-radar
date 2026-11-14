"""Independent TAIFEX TXF source re-download, raw SHA and parsed value audit.
Preserve raw hash differences; never silently accept changed source values.
"""
import argparse
import datetime as dt
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from collect_taifex_three_year import extract

ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--limit",type=int,default=718)
 p.add_argument("--timeout",type=int,default=12)
 a=p.parse_args()
 if not 1<=a.limit<=718:raise SystemExit("limit must be 1..718")
 records=json.loads((ROOT/"storage/taifex_backfill.json").read_text(encoding="utf-8"))["records"]
 out=ROOT/"storage/verification/taifex_sha256_recheck.json"
 out.parent.mkdir(parents=True,exist_ok=True)
 try:state=json.loads(out.read_text(encoding="utf-8"))
 except (FileNotFoundError,ValueError):state={"schema_version":2,"records":{}}
 state["schema_version"]=2
 done=state["records"]
 attempted=0
 for rec in records:
  d=rec["date"]
  previous=done.get(d,{})
  if previous.get("status")=="match" and previous.get("actual_sha256")==rec["source_sha256"]:
   previous["parsed_values_match"]=True
   previous["verification_basis"]="raw_sha256_exact_match"
   continue
  if previous.get("parsed_values_match") is True and previous.get("status") in ("match","mismatch"):
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
  except Exception as exc:
   result={"status":"fetch_error","parsed_values_match":False,"error":type(exc).__name__,"error_detail":str(exc)[:160],"source_url":rec["source_url"],"verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
  done[d]=result
  out.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  if attempted%25==0:print("Checked",attempted,"this run",flush=True)
  time.sleep(.12)
 total=len(records)
 counts={s:sum(x.get("status")==s for x in done.values()) for s in ("match","mismatch","fetch_error")}
 semantic=sum(x.get("parsed_values_match") is True for x in done.values())
 report={"schema_version":2,"dataset":"TAIFEX TXF official historical source HTML",
         "expected_records":total,"attempted_this_run":attempted,"checked":len(done),
         "counts":counts,"semantic_values_verified":semantic,"semantic_values_unverified":total-semantic,
         "raw_hash_mismatch_dates":[d for d,x in done.items() if x.get("status")=="mismatch"],
         "discrepancy_dates":[d for d,x in done.items() if x.get("parsed_values_match") is False],
         "all_raw_hashes_verified":counts["match"]==total and counts["mismatch"]==0,
         "all_values_independently_verified":semantic==total,
         "limitations":["Raw HTML SHA mismatch is not equivalent to a data mismatch.","Original HTML bytes were not archived; precise HTML diff is not possible without them."]}
 (ROOT/"docs/taifex_raw_hash_recheck.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
