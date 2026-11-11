"""Verify actual official daily TAIFEX TX foreign open-interest query and table."""
import urllib.request,urllib.parse,json,re,hashlib
from pathlib import Path
URL="https://www.taifex.com.tw/cht/3/futContractsDate"
PARAMS={"commodityId":"TX","doQuery":"1","queryDate":"2026/10/30","queryType":"1"}
def main():
 url=URL+"?"+urllib.parse.urlencode(PARAMS)
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.taifex.com.tw/cht/3/futContractsDate"})
 with urllib.request.urlopen(req,timeout=30) as resp:
  raw=resp.read(3_000_000);status=resp.status;typ=resp.headers.get("Content-Type")
 html=raw.decode("utf-8",errors="replace")
 fragments=[]
 for m in re.finditer("臺股期貨|台股期貨|外資|未平倉|2026/10/30",html):
  if len(fragments)<20:fragments.append(re.sub(r"\\s+"," ",html[max(0,m.start()-120):m.end()+250]))
 report={"url":url,"status":status,"content_type":typ,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"has_tx":"臺股期貨" in html or "台股期貨" in html,"has_foreign":"外資" in html,"has_date":"2026/10/30" in html,"fragments":fragments}
 p=Path(__file__).resolve().parents[1]/"docs/taifex_daily_query_probe.json"
 p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({k:v for k,v in report.items() if k!="fragments"},ensure_ascii=False))
if __name__=="__main__":main()
