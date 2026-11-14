"""Independently refetch TAIFEX source HTML and compare raw SHA256.
No mismatch is silently corrected; run in bounded batches to respect upstream.
"""
import argparse,datetime as dt,hashlib,json,time,urllib.request
from pathlib import Path
from collect_taifex_three_year import extract
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
  if done.get(d,{}).get("status") in ("match","mismatch","content_mismatch","unparseable") or (done.get(d,{}).get("status")=="fetch_error" and done[d].get("attempts",0)>=2):continue
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
   if actual!=expected:
    try:
     parsed=extract(body,d,rec["source_url"])
     fields=("date","value","long_oi","short_oi")
     result["parsed_values_match"]=all(parsed[k]==rec[k] for k in fields)
     result["parsed_values"]={k:parsed[k] for k in fields}
     if not result["parsed_values_match"]:result["status"]="content_mismatch"
    except Exception as exc:
     result["status"]="unparseable"
     result["parse_error"]=str(exc)[:180]
  except Exception as exc:
   result={"status":"fetch_error","attempts":done.get(d,{}).get("attempts",0)+1,"error":type(exc).__name__,"source_url":rec["source_url"],"verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
  done[d]=result
  out.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  time.sleep(.35)
 total=len(records)
 counts={s:sum(x.get("status")==s for x in done.values()) for s in ("match","mismatch","content_mismatch","unparseable","fetch_error")}
 report={"schema_version":1,"dataset":"TAIFEX TXF source HTML","expected_records":total,"attempted_this_run":attempted,"checked":len(done),"counts":counts,"unverified":total-counts["match"],"pending_download":total-len(done),"semantic_matches_with_raw_hash_mismatch":sum(v.get("status")=="mismatch" and v.get("parsed_values_match") is True for v in done.values()),"all_raw_hashes_verified":counts["match"]==total and counts["mismatch"]==0,"limitations":["HTTP response bytes may change due to site templates, anti-bot or server-rendered current content; mismatch requires investigation, never automatic acceptance."]}
 (ROOT/"docs/taifex_raw_hash_recheck.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(report))
if __name__=="__main__":main()
