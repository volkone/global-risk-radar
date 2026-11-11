"""Inspect official TAIFEX download button handler and referenced JS without guessing API routes."""
import json,re,urllib.request
from html.parser import HTMLParser
from pathlib import Path
class Inspector(HTMLParser):
 def __init__(self):super().__init__();self.forms=[];self.form=None;self.scripts=[];self.buttons=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=="form":self.form={"attributes":a,"controls":[]};self.forms.append(self.form)
  if tag=="script" and a.get("src"):self.scripts.append(a["src"])
  if tag in ("input","button","select"):
   entry={"tag":tag,**a}
   if self.form is not None:self.form["controls"].append(entry)
   if tag in ("input","button"):self.buttons.append(entry)
 def handle_endtag(self,tag):
  if tag=="form":self.form=None
def main():
 u="https://www.taifex.com.tw/cht/3/futContractsDateView"
 req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
 with urllib.request.urlopen(req,timeout=30) as r:html=r.read(2_000_000).decode("utf-8",errors="replace")
 p=Inspector();p.feed(html)
 excerpts=[]
 for m in list(re.finditer("下載|download|Download|excel|Excel|futContractsDate",html)):
  excerpt=html[max(0,m.start()-350):min(len(html),m.end()+400)]
  if len(excerpts)<35:excerpts.append(re.sub(r"\\s+"," ",excerpt))
 report={"forms":p.forms,"buttons":p.buttons,"script_srcs":p.scripts,"relevant_html_excerpts":excerpts}
 out=Path(__file__).resolve().parents[1]/"docs/taifex_download_handler_inspection.json"
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 print("forms",len(p.forms),"buttons",len(p.buttons),"scripts",len(p.scripts),"excerpts",len(excerpts))
if __name__=="__main__":main()
