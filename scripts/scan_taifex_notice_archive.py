"""Conservative, reproducible discovery of TAIFEX official closure notices.

Searches an official announcements listing by month, saving candidate links.
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

def months():
    y,m=START.year,START.month
    while (y,m)<=(END.year,END.month):
        yield f"{y:04d}-{m:02d}"
        m+=1
        if m==13:y,m=y+1,1

def main():
    # The TAIFEX announcement page may require form submission or JavaScript.
    # Month labels are audit partitions, NOT verified server-side date filters.
    partitions=[]
    for month in ["unfiltered_listing"]:
        url=BASE
        item={"month":month,"url":url,"filter_applied":False,"coverage_verified":False}
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=20) as res:
                raw=res.read(2_000_000)
                html=raw.decode("utf-8",errors="replace")
                parser=Links();parser.feed(html)
                matches=[]
                for href,label in parser.links:
                    if any(k in label for k in KEYWORDS):
                        absolute=urllib.parse.urljoin(url,href)
                        if urllib.parse.urlparse(absolute).netloc=="www.taifex.com.tw":
                            matches.append({"title":label,"url":absolute})
                item.update(http_status=res.status,sha256=hashlib.sha256(raw).hexdigest(),candidates=matches)
        except Exception as exc:
            item["error"]=f"{type(exc).__name__}: {str(exc)[:200]}"
        partitions.append(item)
    # Never mark a month complete unless date-scoped server-side filtering
    # and full pagination have been independently verified.
    result={"window":[START.isoformat(),END.isoformat()],"keywords":KEYWORDS,"partitions":partitions,"partitions_total":len(list(months())),"listing_fetches":len(partitions),"months_pending_verification":list(months()),"partitions_coverage_verified":0,"full_notice_sweep_verified":False,"primary_evidence_complete":False,"independent_taifex_calendar_verified":False,"full_model_backtest_authorized":False,"limitations":"The listing is not proven to be month-filtered or exhaustive; repeated responses must not be counted as independent month coverage."}
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Scanned {len(partitions)} provisional partitions; verified coverage 0; candidates {sum(len(x.get('candidates',[])) for x in partitions)}")
if __name__=="__main__":main()
