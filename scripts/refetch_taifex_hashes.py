"""Independently refetch TAIFEX source HTML and compare raw SHA256.
No mismatch is silently corrected; run in bounded batches to respect upstream.
"""
import argparse,datetime as dt,hashlib,json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--limit",type=int,default=20)
 p.add_argument("--timeout",type=int,default=12)
 a=p.parse_args()
 if not 1<=a.limit<=30:raise SystemExit("limit must be 1..30")
 records=json.loads((ROOT/"storage/taifex_backfill.json").read_text(encoding="utf-8"))["records"]
 out=ROOT/"storage/verification/taifex_sha256_recheck.json"
 out.parent.mkdir(parents=True,exist_ok=True)
 try:state=json.loads(out.read_text(encoding="utf-8"))
 except (FileNotFoundError,ValueError):state={"schema_version":1,"records":{}}
 done=state["records"]
 attempted=0
 for rec in records:
  d=rec["date"]
  if done.get(d,{}).get("status")=="match":continue
  if attempted>=a.limit:break
  attempted+=1
  try:
   req=urllib.request.Request(rec["source_url"],headers={"User-Agent":"Mozilla/5.0 (historical evidence verification)","Accept":"text/html,*/*"})
   with urllib.request.urlopen(req,timeout=a.timeout) as res:
    body=res.read()
    status=res.status
   actual=hashlib.sha256(body).hexdigest()
   expected=rec["source_sha256"]
   result={"status":"match" if actual==expected else "mismatch","expected_sha256":expected,"actual_sha256":actual,"http_status":status,"bytes":len(body),"source_url":rec["source_url"],"verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
  except Exception as exc:
   result={"status":"fetch_error","error":type(exc).__name__,"source_url":rec["source_url"],"verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
  done[d]=result
  out.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  time.sleep(.35)
 total=len(records)
 counts={s:sum(x.get("status")==s for x in done.values()) for s in ("match","mismatch","fetch_error")}
 report={"schema_version":1,"dataset":"TAIFEX TXF source HTML","expected_records":total,"attempted_this_run":attempted,"checked":len(done),"counts":counts,"unverified":total-counts["match"],"all_raw_hashes_verified":counts["match"]==total and counts["mismatch"]==0,"limitations":["HTTP response bytes may change due to site templates, anti-bot or server-rendered current content; mismatch requires investigation, never automatic acceptance."]}
 (ROOT/"docs/taifex_raw_hash_recheck.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(report))
if __name__=="__main__":main()
