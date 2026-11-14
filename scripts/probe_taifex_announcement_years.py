"""Bounded independent verification of TAIFEX announcements by official year selector.
Never interpret an HTTP 200 or an empty result as proof of archive completeness.
"""
import json, re, urllib.request, urllib.parse, hashlib
from html.parser import HTMLParser
from pathlib import Path
BASE="https://www.taifex.com.tw/cht/11/announcement"
OUT=Path(__file__).resolve().parents[1]/"docs/taifex_announcement_year_probe.json"
class Reader(HTMLParser):
 def __init__(self):
  super().__init__();self.forms=[];self.form=None;self.select=None;self.options=[];self.anchor=None;self.links=[];self.text=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=="form":self.form={"action":a.get("action"),"method":a.get("method"),"fields":[]};self.forms.append(self.form)
  if tag=="select":self.select=a.get("name");self.options.append({"name":self.select,"values":[]})
  if tag=="option" and self.select:self.options[-1]["values"].append(a.get("value"))
  if tag=="input" and self.form is not None:self.form["fields"].append({"name":a.get("name"),"value":a.get("value"),"type":a.get("type")})
  if tag=="a":self.anchor={"href":a.get("href"),"parts":[]}
 def handle_data(self,data):
  if self.anchor:self.anchor["parts"].append(data)
  self.text.append(data)
 def handle_endtag(self,tag):
  if tag=="a" and self.anchor:
   h=self.anchor["href"] or "";title=" ".join(" ".join(self.anchor["parts"]).split())
   if "newsDetail" in h:self.links.append({"url":urllib.parse.urljoin(BASE,h),"title":title})
   self.anchor=None
  if tag=="select":self.select=None
  if tag=="form":self.form=None
def query(url,method="GET",fields=None):
 data=urllib.parse.urlencode(fields).encode() if fields is not None and method=="POST" else None
 if fields is not None and method=="GET":url+="?"+urllib.parse.urlencode(fields)
 req=urllib.request.Request(url,data=data,headers={"User-Agent":"Mozilla/5.0","Content-Type":"application/x-www-form-urlencoded"})
 with urllib.request.urlopen(req,timeout=35) as response:raw=response.read(4000000);status=response.status
 parser=Reader();parser.feed(raw.decode("utf-8","replace"))
 return {"status":status,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"forms":parser.forms,"selects":parser.options,"links":parser.links,"date_cells":re.findall(r"<td[^>]*>\\s*(20(?:23|24|25|26)/\\d{2}/\\d{2})\\s*</td>",raw.decode("utf-8","replace"),re.I),"raw":raw.decode("utf-8","replace")}
def compact(x):
 return {k:v for k,v in x.items() if k!="raw" and k!="links"}|{"link_count":len(x["links"]),"link_samples":x["links"][:5],"date_count":len(x["date_cells"]),"date_samples":x["date_cells"][:5]}
def main():
 base=query(BASE)
 # Inspect actual selector name and action before submitting any requests.
 year_selects=[s for s in base["selects"] if any(str(v) in ("2023","2024","2025","2026") for v in s["values"])]
 result={"source":BASE,"base":compact(base),"year_select_candidates":year_selects,"year_queries":[],"known_notice_2026_10_22_found":any("薔琵" in x["title"] and "休市" in x["title"] for x in base["links"]),"verified_archive_complete":False}
 if year_selects:
  sel=year_selects[0]
  form=next((f for f in base["forms"] if f["action"] is not None),None)
  for year in ("2024","2026"):
   if year not in sel["values"]:continue
   fields={sel["name"]:year}
   if form:
    fields.update({f["name"]:f["value"] or "" for f in form["fields"] if f["name"] and f["type"]=="hidden"})
   target=urllib.parse.urljoin(BASE,form["action"]) if form else BASE
   method=(form["method"] or "GET").upper() if form else "GET"
   response=query(target,method,fields)
   result["year_queries"].append({"year":year,"method":method,"fields":fields,"result":compact(response),"year_match":bool(response["date_cells"]) and all(d.startswith(year+"/") for d in response["date_cells"]),"different_from_base":response["sha256"]!=base["sha256"]})
 result["selector_working"]=any(q["year_match"] and q["different_from_base"] and q["result"]["link_count"]>0 for q in result["year_queries"])
 result["selector_verified"]=result["selector_working"] and any(q["year"]=="2024" and q["year_match"] for q in result["year_queries"])
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"base_links":len(base["links"]),"known_notice":result["known_notice_2026_10_22_found"],"selector_working":result["selector_working"],"year_queries":len(result["year_queries"])},ensure_ascii=False))
if __name__=="__main__":main()
