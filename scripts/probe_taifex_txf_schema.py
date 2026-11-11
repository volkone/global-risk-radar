"""Inspect exact official TXF foreign row structure for a dated TAIFEX report."""
import urllib.request,urllib.parse,json
from html.parser import HTMLParser
from pathlib import Path
class Rows(HTMLParser):
 def __init__(self):super().__init__();self.tr=None;self.cell=None;self.rows=[]
 def handle_starttag(self,tag,attrs):
  if tag=="tr":self.tr=[]
  if tag in ("td","th") and self.tr is not None:self.cell=[]
 def handle_data(self,data):
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ("td","th") and self.cell is not None and self.tr is not None:self.tr.append(" ".join(" ".join(self.cell).split()));self.cell=None
  if tag=="tr" and self.tr is not None:self.rows.append(self.tr);self.tr=None
def main():
 params={"commodityId":"TXF","doQuery":"1","queryDate":"2026/10/30","queryType":"1"}
 url="https://www.taifex.com.tw/cht/3/futContractsDate?"+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
 with urllib.request.urlopen(req,timeout=30) as r:html=r.read(2_000_000).decode("utf-8",errors="replace")
 parser=Rows();parser.feed(html)
 interesting=[{"index":i,"cells":row} for i,row in enumerate(parser.rows) if any(x in " ".join(row) for x in ("臺股期貨","外資","未平倉餘額"))]
 out=Path(__file__).resolve().parents[1]/"docs/taifex_txf_table_schema.json"
 out.write_text(json.dumps({"url":url,"rows":interesting[:20],"total_table_rows":len(parser.rows)},ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(interesting[:5],ensure_ascii=False))
if __name__=="__main__":main()
