"""Bounded monthly official historical-notice query and conservative completeness audit.
A successful response never by itself proves the server returned all records.
"""
import datetime as dt, hashlib, json, re, time, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL="https://www.taifex.com.tw/cht/11/hisNews"
OUT=ROOT/"docs/taifex_notice_monthly_audit.json"
KEYWORDS=("颱風","休市","停止交易","停止上班","天然災害","暫停交易","停止交易日","交易日曆")
class Parser(HTMLParser):
 def __init__(self): super().__init__();self.links=[];self.href=None;self.buf=[];self.text=[]
 def handle_starttag(self,t,a):
  if t=="a":self.href=dict(a).get("href");self.buf=[]
 def handle_data(self,s):
  self.text.append(s)
  if self.href is not None:self.buf.append(s)
 def handle_endtag(self,t):
  if t=="a" and self.href is not None:self.links.append((self.href," ".join(" ".join(self.buf).split())));self.href=None
def months():
 y,m=2023,11
 while (y,m)<=(2026,10):
  first=dt.date(y,m,1)
  last=(dt.date(y+1,1,1) if m==12 else dt.date(y,m+1,1))-dt.timedelta(days=1)
  yield first,last
  y,m=(y+1,1) if m==12 else (y,m+1)
def main():
 report={"schema_version":1,"source":URL,"months":[],"all_months_queried":False,"pagination_exhaustive":False,"full_notice_sweep_verified":False,"full_model_backtest_authorized":False}
 for first,last in months():
  label=first.strftime("%Y-%m")
  data=urllib.parse.urlencode({"isQuery":"Y","queryStartDate":first.strftime("%Y/%m/%d"),"queryEndDate":last.strftime("%Y/%m/%d"),"newsType":"","queryKeyWord":""}).encode()
  entry={"month":label,"start":str(first),"end":str(last),"method":"POST","submitted_fields":["isQuery","queryStartDate","queryEndDate","newsType","queryKeyWord"],"complete":False}
  try:
   req=urllib.request.Request(URL,data=data,headers={"User-Agent":"Mozilla/5.0","Content-Type":"application/x-www-form-urlencoded","Referer":URL})
   with urllib.request.urlopen(req,timeout=30) as res: raw=res.read(4000000);entry["http_status"]=res.status
   html=raw.decode("utf-8",errors="replace");p=Parser();p.feed(html)
   notices=[{"title":title,"url":urllib.parse.urljoin(URL,href)} for href,title in p.links if "/newsDetail" in href or "newsDetail" in title]
   # Some TAIFEX notice rows are not ordinary anchor URLs. Preserve row text for diagnostics.
   rows=re.findall(r"<tr\\b[^>]*>.*?</tr>",html,re.I|re.S)
   table_rows=[re.sub(r"<[^>]+>"," ",row) for row in rows]
   table_rows=[" ".join(__import__("html").unescape(row).split()) for row in table_rows]
   dated_rows=[row for row in table_rows if re.search(r"20(?:23|24|25|26)[/\\-]\\d{1,2}[/\\-]\\d{1,2}",row)]
   notices=list({x["url"]:x for x in notices}.values())
   entry.update(response_sha256=hashlib.sha256(raw).hexdigest(),response_bytes=len(raw),notice_count=len(notices),notices=notices,dated_row_count=len(dated_rows),dated_row_samples=dated_rows[:12],known_closure_terms_in_response=[k for k in KEYWORDS if k in html],candidates=[x for x in notices if any(k in x["title"] for k in KEYWORDS)],pagination_hints=re.findall(r".{0,55}(?:totalPage|totalCount|pageSize|pageNo|currentPage|下一頁|末頁).{0,80}",html,re.I)[:15],date_query_echo_confirmed=(first.strftime("%Y/%m/%d") in html and last.strftime("%Y/%m/%d") in html))
   # Need a documented total count or proven page traversal to certify.
   entry["complete"]=False
   entry["extraction_suspect"]=not notices and not dated_rows
  except Exception as e:entry["error"]=type(e).__name__+": "+str(e)[:180]
  report["months"].append(entry)
  OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  print(label,entry.get("http_status"),entry.get("notice_count"),flush=True)
  time.sleep(2)
 report["all_months_queried"]=len(report["months"])==36 and all(x.get("http_status")==200 for x in report["months"])
 report["months_with_query_echo"]=sum(bool(x.get("date_query_echo_confirmed")) for x in report["months"])
 report["candidate_notices_total"]=sum(len(x.get("candidates",[])) for x in report["months"])
 report["blockers"]=["pagination_or_result_total_not_independently_proven","known_special_dates_require_reconciliation"]
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
