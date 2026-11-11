"""Collect official TAIFEX TXF foreign open interest for available three-year window.

Uses the verified dated official query (not the unrelated HTML download endpoint).
Stores extracted official rows with source URL and response SHA256. Never invents
observations and never treats an HTML error page as an accepted observation.
"""
import csv,datetime as dt,hashlib,json,time,urllib.parse,urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
START="2023-11-11"
END="2026-10-31"
URL="https://www.taifex.com.tw/cht/3/futContractsDate"
OUT=ROOT/"storage/taifex_backfill.json"
REPORT=ROOT/"docs/taifex_collection_report.json"
class Table(HTMLParser):
 def __init__(self):super().__init__();self.tr=None;self.cell=None;self.rows=[]
 def handle_starttag(self,tag,attrs):
  if tag=="tr":self.tr=[]
  if tag in ("td","th") and self.tr is not None:self.cell=[]
 def handle_data(self,data):
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ("td","th") and self.cell is not None and self.tr is not None:self.tr.append(" ".join(" ".join(self.cell).split()));self.cell=None
  if tag=="tr" and self.tr is not None:self.rows.append(self.tr);self.tr=None

def extract(raw,date,url):
 html=raw.decode("utf-8",errors="replace")
 if date.replace("-","/") not in html:raise ValueError("requested date absent in official response")
 p=Table();p.feed(html)
 matches=[]
 for i,row in enumerate(p.rows):
  if len(row)>=15 and row[1].strip() in ("臺股期貨","台股期貨") and row[2].strip()=="自營商":
   for nxt in p.rows[i+1:i+4]:
    if len(nxt)==13 and nxt[0].strip() in ("外資","外資及陸資"):
     matches.append(nxt)
 if len(matches)!=1:raise ValueError(f"expected one TXF foreign row, found {len(matches)}")
 r=matches[0]
 long_oi,short_oi,net=(int(r[i].replace(",","")) for i in (7,9,11))
 if min(long_oi,short_oi)<0 or long_oi-short_oi!=net:raise ValueError("OI identity mismatch")
 return {"metric_id":"inst.futures","date":date,"value":net,"long_oi":long_oi,"short_oi":short_oi,"unit":"contracts","scope":"TX臺股期貨;外資及陸資;未平倉淨額","provider":"TAIFEX","source_url":url,"source_sha256":hashlib.sha256(raw).hexdigest()}

def main():
 with (ROOT/"storage/official_calendar/trading_days.csv").open(encoding="utf-8-sig",newline="") as f:
  days=sorted(r["date"] for r in csv.DictReader(f) if r["is_trading_day"]=="1" and START<=r["date"]<=END)
 existing=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"records":[]}
 accepted={r["date"]:r for r in existing.get("records",[]) if r.get("metric_id")=="inst.futures"}
 errors=[]
 for index,date in enumerate(days):
  if date in accepted:continue
  params={"commodityId":"TXF","doQuery":"1","queryDate":date.replace("-","/"),"queryType":"1"}
  url=URL+"?"+urllib.parse.urlencode(params)
  for attempt in range(3):
   try:
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":URL})
    with urllib.request.urlopen(req,timeout=30) as resp:raw=resp.read(2_000_000)
    row=extract(raw,date,url)
    accepted[date]=row
    break
   except Exception as exc:
    if attempt==2:errors.append({"date":date,"reason":type(exc).__name__+":"+str(exc)[:140]})
    else:time.sleep(1.5*(attempt+1))
  if index%40==0:print("progress",index,"/",len(days),"accepted",len(accepted),"errors",len(errors),flush=True)
  time.sleep(0.25)
 payload={"schema_version":1,"records":sorted(accepted.values(),key=lambda x:x["date"]),"source":"TAIFEX official dated futContractsDate query; TXF foreign OI","status":"collected_pending_independent_futures_calendar_audit"}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
 report={"window":[START,END],"twse_reference_sessions":len(days),"official_taifex_rows":len(accepted),"missing_reference_dates":sorted(set(days)-set(accepted)),"errors":errors,"independent_taifex_calendar_verified":False}
 REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 print("completed",len(accepted),"/",len(days),"errors",len(errors))
if __name__=="__main__":main()
