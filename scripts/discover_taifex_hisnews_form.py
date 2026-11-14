"""Inspect the actual TAIFEX historical-news form and pagination controls.

This is a discovery probe, not proof of archive completeness.
"""
import json,re,urllib.request
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL="https://www.taifex.com.tw/cht/11/hisNews"
class Inspector(HTMLParser):
 def __init__(self):super().__init__();self.forms=[];self.current=None;self.links=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=="form":self.current={"action":a.get("action"),"method":a.get("method"),"controls":[]};self.forms.append(self.current)
  elif tag in ("input","select","button") and self.current is not None:self.current["controls"].append({"tag":tag,"name":a.get("name"),"id":a.get("id"),"type":a.get("type"),"value":a.get("value"),"onclick":a.get("onclick")})
  elif tag=="a":self.links.append({"href":a.get("href"),"onclick":a.get("onclick")})
 def handle_endtag(self,tag):
  if tag=="form":self.current=None
def main():
 req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0"})
 with urllib.request.urlopen(req,timeout=40) as r:raw=r.read(3000000);status=r.status
 html=raw.decode("utf-8","replace");p=Inspector();p.feed(html)
 markers=("page","分頁","下一頁","查詢","date","query","news","start","end","total","類別")
 controls=[{"form_action":f["action"],"form_method":f["method"],"controls":f["controls"]} for f in p.forms]
 links=[x for x in p.links if any(m in str(x).lower() for m in ("page","next","hisnews","javascript"))][:40]
 scripts=re.findall(r"<script[^>]+src=['\"]([^'\"]+)",html,re.I)
 result={"url":URL,"http_status":status,"bytes":len(raw),"forms":controls,"candidate_links":links,"script_sources":scripts,"pagination_contexts":[html[max(0,m.start()-100):m.start()+200] for m in list(re.finditer(r"pageSize|pageNo|totalPage|下一頁|查詢日期|query_date|query_year",html,re.I))[:20]],"archive_complete":False,"note":"Discovery only: do not infer pagination from ignored parameters"}
 out=ROOT/"docs/taifex_hisnews_form_discovery.json";out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"status":status,"forms":controls,"script_sources":scripts,"candidate_links":links[:10]},ensure_ascii=False))
if __name__=="__main__":main()
