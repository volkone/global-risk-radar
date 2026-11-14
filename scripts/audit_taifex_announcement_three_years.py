"""Collect bounded official announcement candidates, reconcile known closures; fail closed."""
import datetime as dt, hashlib, json, re, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL="https://www.taifex.com.tw/cht/11/announcement"
OUT=ROOT/"docs/taifex_announcement_three_year_audit.json"
EVIDENCE=ROOT/"docs/taifex_calendar_evidence.json"
YEARS=(2023,2024,2025,2026)
class Rows(HTMLParser):
 def __init__(self):super().__init__();self.row=None;self.cell=None;self.anchor=None;self.rows=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=="tr":self.row=[]
  if tag=="td" and self.row is not None:self.cell={"parts":[],"links":[]}
  if tag=="a" and self.cell is not None:self.anchor={"href":a.get("href",""),"parts":[]}
 def handle_data(self,data):
  if self.cell is not None:self.cell["parts"].append(data)
  if self.anchor is not None:self.anchor["parts"].append(data)
 def handle_endtag(self,tag):
  if tag=="a" and self.anchor is not None:
   self.cell["links"].append({"url":urllib.parse.urljoin(URL,self.anchor["href"]),"title":" ".join(" ".join(self.anchor["parts"]).split())});self.anchor=None
  if tag=="td" and self.cell is not None:self.row.append(self.cell);self.cell=None
  if tag=="tr" and self.row is not None:self.rows.append(self.row);self.row=None
def request(year,mode,extra=None):
 fields={"query_year":str(year)}
 fields.update(extra or {})
 if mode=="post":data=urllib.parse.urlencode(fields).encode();url=URL
 else:data=None;url=URL+"?"+urllib.parse.urlencode(fields)
 req=urllib.request.Request(url,data=data,headers={"User-Agent":"Mozilla/5.0","Content-Type":"application/x-www-form-urlencoded"})
 with urllib.request.urlopen(req,timeout=40) as response:raw=response.read(5000000);status=response.status
 parser=Rows();parser.feed(raw.decode("utf-8","replace"))
 records=[]
 # Archive pagination metadata is diagnostic until total pages and navigation are proven.
 html=raw.decode("utf-8","replace")
 pagination={"page_parameters":sorted(set(re.findall(r'(?:pageNo|pageNum|pageIndex|pageSize|currentPage|totalPage|totalCount|page=)',html,re.I))),"pagination_contexts":[html[max(0,m.start()-140):m.start()+180] for m in list(re.finditer(r'(?:下一頁|末頁|總筆數|共\\s*\d+\\s*頁|pageNo|pageNum|pageIndex|totalPage)',html,re.I))[:12]]}
 for row in parser.rows:
  if len(row)<2:continue
  date=" ".join(" ".join(row[0]["parts"]).split())
  if not re.fullmatch(r"20\d{2}/\d{1,2}/\d{1,2}",date):continue
  title=" ".join(" ".join(row[1]["parts"]).split())
  links=row[1]["links"]
  if title:records.append({"published":date.replace("/","-"),"title":title,"url":links[0]["url"] if links else None})
 return {"method":mode,"year":year,"http_status":status,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"record_count":len(records),"records":records,"pagination":pagination,"year_match":bool(records) and all(x["published"].startswith(str(year)+"-") for x in records)}
def main():
 evidence=json.loads(EVIDENCE.read_text(encoding="utf-8"))
 report={"source":URL,"scope":["2023-11-11","2026-10-31"],"years":[],"special_date_reconciliation":[],"full_notice_sweep_verified":False,"full_model_backtest_authorized":False}
 allrecords={}
 for year in YEARS:
  attempts=[]
  for mode in ("post","get"):
   try:attempts.append(request(year,mode))
   except Exception as e:attempts.append({"method":mode,"year":year,"error":str(e)[:200]})
  usable=next((x for x in attempts if x.get("year_match")),None)
  report["years"].append({"year":year,"attempts":[{k:v for k,v in a.items() if k!="records"} for a in attempts],"selected_method":usable["method"] if usable else None,"verified_year_filter":bool(usable),"record_count":usable["record_count"] if usable else 0})
  allrecords[year]=usable["records"] if usable else []
  print(year,report["years"][-1]["verified_year_filter"],report["years"][-1]["record_count"],flush=True)
 report["records"]=[x for year in YEARS for x in allrecords[year] if "2023-11-11"<=x["published"]<="2026-10-31"]
 for entry in evidence["special_dates"]:
  dates=entry["dates"]
  official=entry.get("official_url","")
  matches=[x for x in report["records"] if any(d.replace("-","/") in x["title"] or d in x["title"] for d in dates) or (official and x["url"] and urllib.parse.parse_qs(urllib.parse.urlparse(x["url"]).query).get("idx")==urllib.parse.parse_qs(urllib.parse.urlparse(official).query).get("idx") and "idx=" in official)]
  report["special_date_reconciliation"].append({"dates":dates,"reason":entry["reason"],"known_official_url":official,"matching_archive_records":matches[:12],"matched":bool(matches),"note":"A missing match does not negate separately verified official primary evidence"})
 # Probe pagination parameters conservatively. A different response alone does not establish traversal.
 report["pagination_probes"]=[]
 for year in YEARS:
  baseline=next((a for a in report["years"] if a["year"]==year),None)
  if not baseline or not baseline["verified_year_filter"]:continue
  for fields in ({"pageSize":"10"},{"pageSize":"10","pageNo":"2"},{"pageSize":"10","pageNum":"2"},{"pageSize":"10","page":"2"}):
   try:
    q=request(year,"post",fields)
    report["pagination_probes"].append({"year":year,"fields":fields,"status":q["http_status"],"record_count":q["record_count"],"year_match":q["year_match"],"sha256":q["sha256"],"first_urls":[x["url"] for x in q["records"][:3]]})
   except Exception as e:report["pagination_probes"].append({"year":year,"fields":fields,"error":str(e)[:200]})
 # Repeated hashes prove these guessed parameters are ignored, not that the archive is exhausted.
 report["pagination_probe_distinct_pages"]=[]
 for year in YEARS:
  probes=[x for x in report["pagination_probes"] if x["year"]==year and x.get("sha256")]
  distinct=len(set(x["sha256"] for x in probes))
  report["pagination_probe_distinct_pages"].append({"year":year,"distinct_response_hashes":distinct,"parameter_probe_effective":distinct>1})
 report["pagination_verified"]=False
 report["pagination_traversal_status"]="blocked_no_verified_navigation_or_total_count"
 report["source_scope_warning"]="The annual announcement listing is not independently established as the complete historical news archive."
 report["all_year_filters_verified"]=all(x["verified_year_filter"] for x in report["years"])
 # Distinguish a notice absent from the listing from independently verified primary evidence.
 report["primary_evidence_reconciliation"]=[{"dates":e["dates"],"status":e.get("status"),"official_url":e.get("official_url"),"primary_evidence_already_verified":e.get("status") in ("verified_primary","previously_verified_primary","verified_direct_page")} for e in evidence["special_dates"]]
 report["special_date_evidence_summary"]={"total_groups":len(report["primary_evidence_reconciliation"]),"primary_evidence_previously_verified":sum(x["primary_evidence_already_verified"] for x in report["primary_evidence_reconciliation"]),"listing_matched":sum(x["matched"] for x in report["special_date_reconciliation"]),"independent_archive_exhaustiveness_verified":False}
 report["unmatched_special_dates"]=[x["dates"] for x in report["special_date_reconciliation"] if not x["matched"]]
 report["blockers"]=["historical_year_filters_not_all_verified"] if not report["all_year_filters_verified"] else []
 report["blockers"]+=["archive_pagination_and_total_not_proven","independent_official_txf_2023_11_13_pending"]
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
