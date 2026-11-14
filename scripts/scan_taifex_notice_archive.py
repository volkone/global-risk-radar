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
HISTORICAL_ARCHIVE="https://www.taifex.com.tw/cht/11/hisNews"
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
        super().__init__();self.forms=[];self.selects=[];self.buttons=[];self.inputs=[];self.current=None
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=="form":self.forms.append({"action":d.get("action"),"method":d.get("method","GET")})
        if tag=="input":self.inputs.append({"name":d.get("name"),"id":d.get("id"),"type":d.get("type"),"value":d.get("value")})
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
                official_notice_links=[]
                for href,label in parser.links:
                    absolute=urllib.parse.urljoin(url,href)
                    parsed=urllib.parse.urlparse(absolute)
                    if parsed.netloc=="www.taifex.com.tw" and ("/cht/11/newsDetail" in parsed.path or "/enl/eng11/newsDetail" in parsed.path or "/file/taifex/CHINESE/11/attach/" in parsed.path):
                        official_notice_links.append({"title":label,"url":absolute})
                official_notice_links=list({x["url"]:x for x in official_notice_links}.values())
                # Only page controls tied to the announcement form count; unrelated site carousel links do not.
                page_controls=[{"name":i.get("name"),"value":i.get("value")} for i in controls.inputs if i.get("name") and re.search(r"page|offset|start|rows",i["name"],re.I)]
                selected=[o["value"] for sel in controls.selects if sel["name"]=="query_year" for o in sel["options"] if o["selected"]]
                pagination_links=[{"label":label,"url":urllib.parse.urljoin(url,href)} for href,label in parser.links if re.search(r"(下一頁|上一頁|末頁|首頁|next|prev|page|分頁|^[0-9]{1,3}$)",label,re.I) or re.search(r"(page|offset|start|pagination)",href,re.I)]
                item.update(official_notice_links=official_notice_links,official_notice_link_count=len(official_notice_links),announcement_page_controls=page_controls,pagination_links=pagination_links[:100],html_pagination_hints=re.findall(r".{0,65}(?:totalPage|totalCount|pageSize|currentPage|query_year|pagination|pageNo).{0,100}",html,re.I)[:35],http_status=res.status,sha256=hashlib.sha256(raw).hexdigest(),selected_year=selected,year_filter_confirmed=(selected==[str(year)]),candidates=matches,form_controls={"forms":controls.forms,"selects":controls.selects,"buttons":controls.buttons,"inputs":controls.inputs})
        except Exception as exc:
            item["error"]=f"{type(exc).__name__}: {str(exc)[:200]}"
        partitions.append(item)
    # Independently inspect the official historical-news search interface.
    # A successful page fetch does NOT certify that its search results are exhaustive.
    archive_interface={"url":HISTORICAL_ARCHIVE,"coverage_verified":False}
    try:
        req=urllib.request.Request(HISTORICAL_ARCHIVE,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=25) as res:
            raw=res.read(3_000_000)
            html=raw.decode("utf-8",errors="replace")
            controls=Controls();controls.feed(html)
            archive_interface.update(http_status=res.status,sha256=hashlib.sha256(raw).hexdigest(),form_controls={"forms":controls.forms,"selects":controls.selects,"buttons":controls.buttons,"inputs":controls.inputs},pagination_hints=re.findall(r".{0,60}(?:totalPage|totalCount|pageSize|currentPage|pagination|pageNo).{0,90}",html,re.I)[:30])
    except Exception as exc:
        archive_interface["error"]=f"{type(exc).__name__}: {str(exc)[:200]}"
    # Year selection and matching HTML do not prove pagination completeness.
    verified_years=[x["year"] for x in partitions if x.get("year_filter_confirmed")]
    result={"window":[START.isoformat(),END.isoformat()],"historical_archive_interface":archive_interface,"keywords":KEYWORDS,"partitions":partitions,"partitions_total":len(list(months())),"listing_fetches":len(partitions),"years_requested":years,"years_filter_confirmed":verified_years,"months_pending_verification":list(months()),"partitions_coverage_verified":0,"full_notice_sweep_verified":False,"primary_evidence_complete":False,"independent_taifex_calendar_verified":False,"full_model_backtest_authorized":False,"limitations":"Year-specific POST requests are exploratory. No announcement-specific pagination controls have been proven; generic website carousel and page links are not evidence of archive pagination. Do not infer full archive coverage."}
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Requested years {years}; selected-year confirmation {verified_years}; candidate notices {sum(len(x.get('candidates',[])) for x in partitions)}; archive coverage remains unverified")
if __name__=="__main__":main()
