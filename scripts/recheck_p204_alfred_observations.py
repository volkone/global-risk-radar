"""Independent 18-sample ALFRED as-of value re-query. Never certifies intraday PIT."""
import datetime as dt,hashlib,json,os,time,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'docs/phase3_vintage_audit.json'
OUT=ROOT/'docs/p2_04_alfred_observation_recheck.json'
RAW=ROOT/'storage/verification/p2_04_alfred_observation_responses.json'
def main():
 key=os.environ.get('FRED_API_KEY','').strip()
 if not key:raise SystemExit('FRED_API_KEY missing')
 audit=json.loads(SRC.read_text(encoding='utf-8'))
 checks=audit['checks']
 results=[]
 for item in checks:
  series=item['series_id']; asof=item['asof_utc_calendar_date']; d=item['market_session']
  params=urllib.parse.urlencode({'series_id':series,'api_key':key,'file_type':'json','realtime_start':asof,'realtime_end':asof,'observation_start':'2023-10-01','observation_end':asof,'sort_order':'desc','limit':150})
  try:
   req=urllib.request.Request('https://api.stlouisfed.org/fred/series/observations?'+params,headers={'User-Agent':'global-risk-radar-P204-evidence/1.0'})
   with urllib.request.urlopen(req,timeout=25) as resp:raw=resp.read(1000000)
   obj=json.loads(raw)
   if obj.get('error_code'):raise ValueError('api_error')
   obs=[x for x in obj.get('observations',[]) if x.get('value') not in ('.',None)]
   if not obs:raise ValueError('no_observations')
   latest=max(obs,key=lambda x:x['date'])
   prior_date=item.get('latest_observation_available_asof')
   prior_value=item.get('latest_value_available_asof')
   matches=latest['date']==prior_date and abs(float(latest['value'])-float(prior_value))<1e-6
   results.append({'session':d,'factor':item['factor'],'series_id':series,'asof_date':asof,'latest_date':latest['date'],'latest_value':float(latest['value']),'previous_audit_latest_date':prior_date,'previous_audit_latest_value':prior_value,'matches_prior_audit':matches,'raw_response_sha256':hashlib.sha256(raw).hexdigest(),'retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'verified' if matches else 'mismatch'})
  except Exception as e:
   results.append({'session':d,'factor':item['factor'],'series_id':series,'asof_date':asof,'status':'fetch_error','error_type':type(e).__name__})
  RAW.parent.mkdir(parents=True,exist_ok=True)
  RAW.write_text(json.dumps({'schema_version':1,'results':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  time.sleep(0.2)
 good=sum(x['status']=='verified' for x in results)
 report={'schema_version':1,'status':'sample_recheck_pass' if good==len(checks) else 'sample_recheck_incomplete_or_mismatch','sample_count':len(checks),'verified':good,'mismatch':sum(x['status']=='mismatch' for x in results),'fetch_errors':sum(x['status']=='fetch_error' for x in results),'source_api':'https://api.stlouisfed.org/fred/series/observations','sample_evidence_file':'storage/verification/p2_04_alfred_observation_responses.json','results':results,'all_718_sessions_certified':False,'intraday_publication_certified':False,'production_authorized':False}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:report[k] for k in ('status','sample_count','verified','mismatch','fetch_errors')},ensure_ascii=False))
 if good!=len(checks):raise SystemExit('ALFRED evidence recheck incomplete or inconsistent')
if __name__=='__main__':main()
