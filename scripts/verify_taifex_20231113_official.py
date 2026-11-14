"""Import one independently acquired TAIFEX historical TXF record, fail closed.

Usage: python scripts/verify_taifex_20231113_official.py official.csv --date-col Date --product-col Product --investor-col Investor --long-col LongOI --short-col ShortOI --net-col NetOI
The source must be an unmodified official export; preserve the original separately.
"""
import argparse,csv,hashlib,json,pathlib,sys
DATE="2023-11-13"
def main():
 p=argparse.ArgumentParser()
 p.add_argument("file",type=pathlib.Path)
 for key in ("date","product","investor","long","short","net"):p.add_argument("--"+key+"-col",required=True)
 p.add_argument("--official-source-url",required=True)
 p.add_argument("--source-description",required=True)
 p.add_argument("--encoding",default="utf-8-sig")
 a=p.parse_args()
 raw=a.file.read_bytes()
 digest=hashlib.sha256(raw).hexdigest()
 with a.file.open(encoding=a.encoding,newline="") as f: rows=list(csv.DictReader(f))
 cols={key:getattr(a,key+"_col") for key in ("date","product","investor","long","short","net")}
 assert rows and all(v in rows[0] for v in cols.values()),"Missing official columns"
 normalized=lambda v:v.strip().replace("/","-")
 matches=[r for r in rows if normalized(r[cols["date"]])==DATE and r[cols["product"]].strip().upper() in ("TXF","TX","臺股期貨","台股期貨") and r[cols["investor"]].strip() in ("外資","外資及陸資","Foreign Investors","Foreign and Mainland Investors")]
 if len(matches)!=1:raise SystemExit("FAIL CLOSED: expected exactly one official TXF foreign investor record, got "+str(len(matches)))
 row=matches[0]
 def number(k):return int(row[cols[k]].replace(",","").strip())
 long,short,net=number("long"),number("short"),number("net")
 if long-short!=net:raise SystemExit("FAIL CLOSED: OI long-short does not equal net")
 output={"date":DATE,"contract":"TXF","investor":"foreign_and_mainland_investors","long_open_interest":long,"short_open_interest":short,"net_open_interest":net,"official_source_url":a.official_source_url,"source_description":a.source_description,"original_file_sha256":digest,"original_file_name":a.file.name,"verification":"official_export_user_supplied_not_independently_authenticated","provisional_values_match":{"long":long==38773,"short":short==35641,"net":net==3132},"full_model_backtest_authorized":False}
 dest=pathlib.Path("docs/taifex_20231113_official_candidate.json")
 dest.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(output,ensure_ascii=False,indent=2))
 print("Review original provenance before changing prebacktest gate.")
if __name__=="__main__":main()
