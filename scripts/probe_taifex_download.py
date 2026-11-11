"""Probe official TAIFEX download page, record actual form fields, no invented endpoint."""
import json
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

class FormInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms=[]
        self.current=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="form":
            self.current={"action":a.get("action"),"method":a.get("method","GET"),"fields":[]}
            self.forms.append(self.current)
        if self.current is not None and tag in ("input","select","button"):
            self.current["fields"].append({"tag":tag,"name":a.get("name"),"type":a.get("type"),"value":a.get("value")})
    def handle_endtag(self,tag):
        if tag=="form":self.current=None

def main():
    url="https://www.taifex.com.tw/cht/3/futContractsDateView"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; research-quality-audit/1.0)"})
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read(2_000_000)
            status=response.status
            content_type=response.headers.get("Content-Type","")
        html=raw.decode("utf-8",errors="replace")
        parser=FormInspector()
        parser.feed(html)
        forms=[f for f in parser.forms if any(x["name"] and ("date" in x["name"].lower() or "commodity" in x["name"].lower()) for x in f["fields"])]
        report={"status":"form_inspected" if forms else "form_schema_unverified","url":url,"http_status":status,"content_type":content_type,"candidate_forms":forms,"records_imported":0}
    except Exception as e:
        report={"status":"fetch_failed","url":url,"error":type(e).__name__+": "+str(e)[:200],"records_imported":0}
    p=Path(__file__).resolve().parents[1]/"docs/taifex_download_probe.json"
    p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("TAIFEX probe:",report["status"],"forms:",len(report.get("candidate_forms",[])))
if __name__=="__main__":main()
