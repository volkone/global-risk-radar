"""Check that each TAIFEX evidence URL resolves to actual content.

This is a transport/integrity check, NOT a semantic validation of notices,
nor an exhaustive closure sweep. It must never unlock the backtest gate.
"""
import datetime as dt
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"docs/taifex_calendar_evidence.json"
OUTPUT=ROOT/"docs/taifex_evidence_url_check.json"

def main():
    evidence=json.loads(EVIDENCE.read_text(encoding="utf-8"))
    annual=evidence.get("annual_calendar",{}).get("sources",[])
    special=evidence.get("special_dates",[])
    entries=[{"kind":"annual","label":str(x.get("year")),"url":x.get("official_url","")} for x in annual]
    entries += [{"kind":"special","label":",".join(x.get("dates",[])),"url":x.get("official_url","")} for x in special]
    seen={}
    for x in entries:
        url=x["url"]
        if url in seen:continue
        result={"url":url,"status":"error"}
        if not url.startswith("https://www.taifex.com.tw/"):
            result["error"]="URL outside allowed official TAIFEX origin"
        else:
            try:
                request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; TAIFEX-evidence-audit/1.0)"})
                with urllib.request.urlopen(request,timeout=20) as response:
                    raw=response.read(5_000_001)
                    result.update(http_status=response.status,content_type=response.headers.get("Content-Type",""),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),status="ok" if response.status==200 and len(raw)>100 and len(raw)<=5_000_000 else "invalid")
            except Exception as exc:
                result["error"]=f"{type(exc).__name__}: {str(exc)[:250]}"
        seen[url]=result
    report={"checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"unique_urls":len(seen),"ok":sum(x["status"]=="ok" for x in seen.values()),"failed":sum(x["status"]!="ok" for x in seen.values()),"checks":list(seen.values()),"semantic_notice_verification":False,"full_notice_sweep_verified":False,"independent_taifex_calendar_verified":False,"full_model_backtest_authorized":False,"note":"A successful HTTP response does not prove document content, applicability to each session, or archive-wide completeness."}
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Evidence URL check: {report['ok']}/{report['unique_urls']} accessible")
    for x in report["checks"]:
        if x["status"]!="ok":print("ERROR",x["url"],x.get("error",x["status"]))
    if report["failed"]:raise SystemExit(1)

if __name__=="__main__":main()
