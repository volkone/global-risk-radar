"""Verify TAIFEX official Excel endpoint with a single bounded historical request."""
import json,urllib.parse,urllib.request,hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL="https://www.taifex.com.tw/cht/3/futContractsDateExcel"
PARAMS={"queryStartDate":"2026/10/30","queryEndDate":"2026/10/30","commodityId":"TX"}
def main():
    results=[]
    for method in ("GET","POST"):
        encoded=urllib.parse.urlencode(PARAMS)
        url=URL+("?"+encoded if method=="GET" else "")
        req=urllib.request.Request(url,data=encoded.encode() if method=="POST" else None,headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.taifex.com.tw/cht/3/futContractsDateView","Content-Type":"application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req,timeout=30) as resp:
                raw=resp.read(2_000_000)
                typ=resp.headers.get("Content-Type","")
                status=resp.status
            preview=raw[:240].decode("utf-8",errors="replace").replace("\n"," ")
            has_tx=any(x in raw for x in ("臺股期貨".encode(),"台股期貨".encode()))
            has_foreign="外資".encode() in raw
            looks_excel=raw[:4]==b"PK\\x03\\x04" or raw[:8]==bytes.fromhex("D0CF11E0A1B11AE1")
            result={"method":method,"status":status,"content_type":typ,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"contains_tx":has_tx,"contains_foreign":has_foreign,"excel_signature":looks_excel,"preview":preview[:160]}
            if status==200 and has_tx and has_foreign:
                p=ROOT/"storage/taifex_raw"
                p.mkdir(parents=True,exist_ok=True)
                filename=f"official_tx_20261030_{method.lower()}.html"
                (p/filename).write_bytes(raw)
                result["saved"]=str((p/filename).relative_to(ROOT))
            results.append(result)
        except Exception as e:results.append({"method":method,"error":type(e).__name__+":"+str(e)[:180]})
    out=ROOT/"docs/taifex_download_request_test.json"
    out.write_text(json.dumps({"endpoint":URL,"params":PARAMS,"results":results,"full_history_imported":False},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(results,ensure_ascii=False))
if __name__=="__main__":main()
