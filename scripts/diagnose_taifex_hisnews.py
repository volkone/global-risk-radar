"""Inspect TAIFEX historical news query form and response without claiming completeness."""
import json, re, urllib.request, urllib.parse, hashlib
from html.parser import HTMLParser
from pathlib import Path
URL="https://www.taifex.com.tw/cht/11/hisNews"
OUT=Path(__file__).resolve().parents[1]/"docs/taifex_hisnews_diagnostic.json"
class Form(HTMLParser):
 def __init__(self): super().__init__();self.active=False;self.fields=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=="form" and a.get("id")=="uForm":self.active=True;self.action=a.get("action");self.method=a.get("method")
  if self.active and tag in ("input","select","button"):self.fields.append({"tag":tag,"name":a.get("name"),"type":a.get("type"),"value":a.get("value")})
 def handle_endtag(self,tag):
  if tag=="form":self.active=False
def get(req):
 with urllib.request.urlopen(req,timeout=35) as r:return r.status,r.read(3000000)
def context(t,pattern,limit=5):
 return [re.sub(r"\\s+"," ",t[max(0,m.start()-240):m.end()+380])[:650] for m in list(re.finditer(pattern,t,re.I))[:limit]]
def main():
 status,raw=get(urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0"}))
 t=raw.decode("utf-8","replace");f=Form();f.feed(t)
 payload={"isQuery":"Y","queryStartDate":"2024/07/01","queryEndDate":"2024/07/31","newsType":"","queryKeyWord":""}
 req=urllib.request.Request(URL,data=urllib.parse.urlencode(payload).encode(),headers={"User-Agent":"Mozilla/5.0","Referer":URL,"Content-Type":"application/x-www-form-urlencoded"})
 ps,pr=get(req);pt=pr.decode("utf-8","replace")
 # Independently compare the official announcements listing, not just the historical search form.
 announcement_url="https://www.taifex.com.tw/cht/11/announcement"
 ann_status,ann_raw=get(urllib.request.Request(announcement_url,headers={"User-Agent":"Mozilla/5.0"}))
 ann=ann_raw.decode("utf-8","replace")
 announcement_probe={"url":announcement_url,"http_status":ann_status,"bytes":len(ann_raw),"sha256":hashlib.sha256(ann_raw).hexdigest(),"date_contexts":context(ann,r"20(?:23|24|25|26)[/-]\\d{1,2}[/-]\\d{1,2}",6),"announcement_links":context(ann,r"announcementDetail|newsDetail|公告日期|公告標題",8),"table_count":len(re.findall(r"<table\\b",ann,re.I))}
 result={"announcement_probe":announcement_probe,"source":URL,"get_status":status,"post_status":ps,"form":{"action":getattr(f,"action",None),"method":getattr(f,"method",None),"fields":f.fields},"query":payload,"post_sha256":hashlib.sha256(pr).hexdigest(),"post_bytes":len(pr),"post_title_context":context(pt,r"<title[^>]*>"),"post_results_context":context(pt,r"pagesize|查無資料|查詢結果|查詢無資料|共\\s*\\d+\\s*筆|newsDetail|公告日期",8),"post_form_context":context(pt,r"queryStartDate|queryEndDate|newsType|queryKeyWord",8),"post_table_count":len(re.findall(r"<table\\b",pt,re.I)),"post_script_srcs":re.findall(r"<script[^>]+src=[\\\"']([^\\\"']+)",pt,re.I)[-25:],"post_has_2024_07_notice_text":bool(re.search(r"2024[/\\-]0?7[/\\-]\\d{1,2}.{0,200}(?:颱風|停止交易|休市)",pt,re.S))}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
 print(json.dumps({"get":status,"post":ps,"fields":len(f.fields),"tables":result["post_table_count"],"results_contexts":len(result["post_results_context"])},ensure_ascii=False))
if __name__=="__main__":main()
