"""Independent ALFRED vintage-date evidence capture; bounded, authenticated, fail closed."""
import datetime as dt,hashlib,json,os,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SERIES={"fx":"DEXTAUS","hy":"BAMLH0A0HYM2","ig":"BAMLC0A0CM","vix":"VIXCLS","us10y":"DGS10","nfci":"NFCI"}
def main():
 key=os.getenv("FRED_API_KEY","").strip()
 if not key:raise SystemExit("FRED_API_KEY secret missing")
 out=ROOT/"storage/verification/alfred_vintage_evidence.json"
 out.parent.mkdir(parents=True,exist_ok=True)
 try:state=json.loads(out.read_text(encoding="utf-8"))
 except (FileNotFoundError,ValueError):state={"schema_version":1,"series":{}}
 for metric,series in SERIES.items():
  params=urllib.parse.urlencode({"series_id":series,"api_key":key,"file_type":"json","realtime_start":"2023-11-11","realtime_end":"2026-10-31","limit":10000})
  url="https://api.stlouisfed.org/fred/series/vintagedates?"+params
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"global-risk-radar-evidence/1.0"}),timeout=20) as r:raw=r.read()
   obj=json.loads(raw)
   if "error_code" in obj:raise ValueError("FRED API error")
   dates=obj.get("vintage_dates")
   if not isinstance(dates,list):raise ValueError("missing vintage_dates")
   state["series"][metric]={"series_id":series,"status":"downloaded","vintage_dates":dates,"raw_response_sha256":hashlib.sha256(raw).hexdigest(),"retrieved_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"api_endpoint":"fred/series/vintagedates","count":len(dates)}
  except Exception as e:
   state["series"][metric]={"series_id":series,"status":"fetch_error","error_type":type(e).__name__}
  out.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 summary={"series":{k:{"status":v["status"],"vintage_count":v.get("count"),"raw_response_sha256":v.get("raw_response_sha256")} for k,v in state["series"].items()},"independent_observation_value_comparison_complete":False,"minute_level_publication_time_certified":False,"note":"Vintage-date downloads do not validate historical values or publication minutes."}
 (ROOT/"docs/alfred_independent_evidence.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(summary))
if __name__=="__main__":main()
