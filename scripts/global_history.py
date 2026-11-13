"""Descriptive global prototype reconstruction, separate from issued scores/PIT."""
import bisect
import datetime as dt
import hashlib
import json
import math
import os
import urllib.parse
import urllib.request
from pathlib import Path
from scores import score_group
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'storage/historical_nasdaq100.json'
OUT=ROOT/'docs/global_history.json'

def parse_observations(obj):
    points=[];seen=set()
    for row in obj['observations']:
        date=row['date'];dt.date.fromisoformat(date)
        if date in seen:raise ValueError('duplicate_index_date')
        seen.add(date)
        if row.get('value') in (None,'.',''):continue
        value=float(row['value'])
        if not math.isfinite(value) or value<=0:raise ValueError('invalid_index_price')
        points.append({'date':date,'value':value})
    if points!=sorted(points,key=lambda x:x['date']):raise ValueError('unsorted_index_dates')
    return points

def collect():
    if ARCHIVE.exists():return
    key=os.environ.get('FRED_API_KEY','').strip()
    if not key:raise ValueError('FRED_API_KEY_required_for_initial_index_archive')
    params={'series_id':'NASDAQ100','api_key':key,'file_type':'json',
            'observation_start':'2022-11-01','observation_end':'2026-10-30'}
    url='https://api.stlouisfed.org/fred/series/observations?'+urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url,timeout=30) as r:raw=r.read(2000000)
    except Exception as exc:
        raise RuntimeError('FRED_index_request_failed:'+type(exc).__name__) from None
    points=parse_observations(json.loads(raw))
    if not points or points[0]['date']>'2022-11-10' or points[-1]['date']!='2026-10-30':raise ValueError('index_archive_incomplete')
    ARCHIVE.write_text(json.dumps({'series_id':'NASDAQ100','source_url':'https://fred.stlouisfed.org/series/NASDAQ100',
        'retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'response_sha256':hashlib.sha256(raw).hexdigest(),'history':points,
        'warmup_note':'One preceding year for rolling-high calculation; displayed period remains three years.',
        'point_in_time_certified':False},ensure_ascii=False,indent=2)+'\n')

def at_or_before(points,date,max_age):
    dates=[p['date'] for p in points];i=bisect.bisect_right(dates,date)-1
    if i<0:return None
    p=points[i]
    return p if (dt.date.fromisoformat(date)-dt.date.fromisoformat(p['date'])).days<=max_age else None

def reconstruct(sessions,factors,index):
    records=[]
    for date in sessions:
        metrics={};quality={'metrics':{}}
        for key in ('hy','ig','vix','nfci'):
            p=at_or_before(factors[key]['history'],date,21 if key=='nfci' else 7)
            if p:metrics[key]={'value':p['value'],'date':p['date']};quality['metrics'][key]={'quality':'pass'}
        rate_points=factors.get('us10y',{}).get('history',[])
        rate=at_or_before(rate_points,date,7)
        if rate:
            metrics['us10y']={'value':rate['value'],'date':rate['date'],'history':[p for p in rate_points if p['date']<=date]}
            quality['metrics']['us10y']={'quality':'pass'}
        current=at_or_before(index,date,7)
        lower=(dt.date.fromisoformat(date)-dt.timedelta(days=365)).isoformat()
        window=[p['value'] for p in index if lower<=p['date']<=date]
        # A partial initial year cannot masquerade as a one-year high.
        if current and window and index[0]['date']<=lower:
            high=max(window);metrics['indices']={'drawdown_pct':round(100*(high-current['value'])/high,2),'date':current['date']}
            quality['metrics']['indices']={'quality':'pass'}
        row=score_group('global',metrics,quality)
        used=sum(c['weight'] for c in row['components'] if c['eligible'])
        for c in row['components']:
            c['contribution']=c['signal']*c['weight']/used if c['eligible'] else None
            c['effective_weight']=c['weight']/used if c['eligible'] else 0
            c['observed_date']=metrics.get(c['metric'],{}).get('date')
        records.append(dict(row,date=date,status='descriptive_reconstruction' if row['score'] is not None else 'insufficient_coverage'))
    return records

def main():
    collect()
    paths=['storage/historical_fred_factors.json','storage/historical_nasdaq100.json','storage/phase4_publication_aware_panel.json']
    blobs=[(ROOT/p).read_bytes() for p in paths];factors,index,panel=map(json.loads,blobs)
    records=reconstruct([r['date'] for r in panel['rows']],factors['series'],index['history'])
    report={'schema_version':1,'model_id':'global_rate_v2_descriptive',
            'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'window':[records[0]['date'],records[-1]['date']],
            'sessions':len(records),'valid_scores':sum(r['score'] is not None for r in records),
            'input_sha256':{p:hashlib.sha256(b).hexdigest() for p,b in zip(paths,blobs)},
            'records':records,'point_in_time_certified':False,'formal_model_validated':False,
            'limitations':['Descriptive observation-date reconstruction, not an issued historical forecast or PIT backtest.',
                'Historical FRED values may include later revisions. NASDAQ100 is sourced from Nasdaq via FRED; live prototype uses Yahoo Nasdaq 100.',
                'Global v2 retains weights and adds US10Y 20-session upward-rate-change percentile versus 60 prior changes. Breadth (10%) remains excluded; maximum coverage 90%. This research assumption is not a validated crash predictor.',
                'One warm-up year of index closes is used only for the rolling high. Missing/stale factors retain null scores.']}
    OUT.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n')
    print('GLOBAL_HISTORY',len(records),'sessions',report['valid_scores'],'valid scores; descriptive only')
if __name__=='__main__':main()
