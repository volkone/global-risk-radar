"""Conservative, reproducible discovery of TAIFEX official closure notices.

Fetches the unfiltered official announcements listing, saves candidate links\nand discovers year-selection form controls for a future verified archive sweep.
Discovery is NOT proof of exhaustive archive coverage; never auto-unlocks gates.
"""
import datetime as dt
import hashlib
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"docs/taifex_notice_archive_scan.json"
BASE="https://www.taifex.com.tw/cht/11/announcement"
KEYWORDS=("颱風","休市","停止交易","停止上班","天然災害","暫停交易","交易日曆","交易日期","補班","交易所停止")
START=dt.date(2023,11,11)
END=dt.date(2026,10,31)

class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.href=None;self.label=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":
            self.href=dict(attrs).get("href");self.label=[]
    def handle_data(self,data):
        if self.href is not None:self.label.append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self.href is not None:
            self.links.append((self.href," ".join(" ".join(self.label).split())))
            self.href=None;self.label=[]


class Controls(HTMLParser):
    """Capture actual form and year-select controls without guessing API params."""
    def __init__(self):
        super().__init__();self.forms=[];self.selects=[];self.buttons=[];self.current=None
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=="form":self.forms.append({"action":d.get("action"),"method":d.get("method","GET")})
        if tag=="select":
            self.current={"name":d.get("name"),"id":d.get("id"),"options":[]}
            self.selects.append(self.current)
        if tag=="option" and self.current is not None:
            self.current["options"].append({"value":d.get("value"),"selected":"selected" in d})
        if tag in ("button","input") and (tag=="button" or d.get("type") in ("submit","button")):
            self.buttons.append({"tag":tag,"name":d.get("name"),"id":d.get("id"),"value":d.get("value")})
    def handle_endtag(self,tag):
        if tag=="select":self.current=None

def months():
    y,m=START.year,START.month
    while (y,m)<=(END.year,END.month):
        yield f"{y:04d}-{m:02d}"
        m+=1
        if m==13:y,m=y+1,1

def main():
    partitions=[]
    years=sorted({int(m[:4]) for m in months()})
    for year in years:
        url=BASE
        item={"year":year,"url":url,"request_method":"POST","query_year":str(year),"coverage_verified":False}
        try:
            data=urllib.parse.urlencode({"query_year":str(year)}).encode("ascii")
            req=urllib.request.Request(url,data=data,headers={"User-Agent":"Mozilla/5.0","Content-Type":"application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req,timeout=25) as res:
                raw=res.read(3_000_000)
                html=raw.decode("utf-8",errors="replace")
                parser=Links();parser.feed(html)
                controls=Controls();controls.feed(html)
                matches=[]
                for href,label in parser.links:
                    if any(k in label for k in KEYWORDS):
                        absolute=urllib.parse.urljoin(url,href)
                        if urllib.parse.urlparse(absolute).netloc=="www.taifex.com.tw":
                            matches.append({"title":label,"url":absolute})
                selected=[o["value"] for sel in controls.selects if sel["name"]=="query_year" for o in sel["options"] if o["selected"]]
                item.update(http_status=res.status,sha256=hashlib.sha256(raw).hexdigest(),selected_year=selected,year_filter_confirmed=(selected==[str(year)]),candidates=matches,form_controls={"forms":controls.forms,"selects":controls.selects,"buttons":controls.buttons})
        except Exception as exc:
            item["error"]=f"{type(exc).__name__}: {str(exc)[:200]}"
        partitions.append(item)
    # Year selection and matching HTML do not prove pagination completeness.
    verified_years=[x["year"] for x in partitions if x.get("year_filter_confirmed")]
    result={"window":[START.isoformat(),END.isoformat()],"keywords":KEYWORDS,"partitions":partitions,"partitions_total":len(list(months())),"listing_fetches":len(partitions),"years_requested":years,"years_filter_confirmed":verified_years,"months_pending_verification":list(months()),"partitions_coverage_verified":0,"full_notice_sweep_verified":False,"primary_evidence_complete":False,"independent_taifex_calendar_verified":False,"full_model_backtest_authorized":False,"limitations":"Year-specific POST requests are exploratory. Selected year and complete server-side pagination must be independently verified; do not infer full archive coverage."}
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Requested years {years}; selected-year confirmation {verified_years}; candidate notices {sum(len(x.get('candidates',[])) for x in partitions)}; archive coverage remains unverified")
if __name__=="__main__":main()
