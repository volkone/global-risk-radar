"""Full internal vintage replay; NOT independent source or release-time certification."""
import bisect
import datetime as dt
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def replay_audit(panel, vintages):
    dates=[r['date'] for r in panel['rows']]
    if dates!=sorted(set(dates)):raise ValueError('duplicate_or_unsorted_sessions')
    indexes={}
    future_changes={}
    for key, stream in vintages['series'].items():
        events={}
        for item in stream['bootstrap']:
            events.setdefault(item['date'],[]).append((stream['bootstrap_date'],item['value']))
        for item in stream['changes']:
            events.setdefault(item['observed_date'],[]).append((item['vintage_date'],item['value']))
        indexes[key]={d:sorted(v,key=lambda x:x[0]) for d,v in events.items()}
        future_changes[key]=stream.get('future_dated_source_changes',0)
    mismatches=[];counts={};records=[]
    for key, events in indexes.items():
        counts[key]={'checked':0,'matched_values':0,'expected_missing':0,'mismatches':0,'uncertified_release_values':0}
        for row in panel['rows']:
            o=row['us_previous_dated_observations'][key];cutoff=o['asof_us_calendar_date']
            available={}
            if cutoff>=vintages['series'][key]['bootstrap_date']:
                for date, versions in events.items():
                    if date>cutoff:continue
                    i=bisect.bisect_right([v[0] for v in versions],cutoff)-1
                    if i>=0 and versions[i][1] is not None:available[date]=versions[i][1]
            # Independent application of the documented conservative schedule.
            eligible={}
            decision=dt.datetime.fromisoformat(o['decision_at_taipei'])
            from zoneinfo import ZoneInfo
            for date,value in available.items():
                day=dt.date.fromisoformat(date);stamp=None
                if key in ('fx','nfci'):
                    friday=day+dt.timedelta(days=(4-day.weekday())%7)
                    release=friday+dt.timedelta(days=6)
                    stamp=dt.datetime.combine(release,dt.time(16,15) if key=='fx' else dt.time(8,30),ZoneInfo('America/New_York'))
                elif key=='us10y':stamp=dt.datetime.combine(day,dt.time(16,15),ZoneInfo('America/New_York'))
                if stamp is None or stamp<decision:eligible[date]=value
            observed=max(eligible) if eligible else None
            age=(dt.date.fromisoformat(row['date'])-dt.date.fromisoformat(observed)).days if observed else None
            expected=eligible[observed] if observed and age<=21 else None
            reasons=[]
            if cutoff>=row['date']:reasons.append('asof_not_prior')
            if o['value']!=expected:reasons.append('value_mismatch')
            if expected is not None and o['observed_date']!=observed:reasons.append('selected_date_mismatch')
            if expected is not None and o.get('time_gate_passed') is not True:reasons.append('gate_flag_mismatch')
            counts[key]['checked']+=1
            if reasons:
                counts[key]['mismatches']+=1
                mismatches.append({'session':row['date'],'factor':key,'reasons':reasons,'expected_date':observed,'expected_value':expected,'actual_date':o['observed_date'],'actual_value':o['value']})
            elif expected is None:counts[key]['expected_missing']+=1
            else:counts[key]['matched_values']+=1
            if expected is not None and o.get('actual_historical_release_timestamp_verified') is not True:counts[key]['uncertified_release_values']+=1
    return {'status':'internal_replay_pass' if not mismatches else 'internal_replay_failed',
            'sessions':len(dates),'checks':sum(c['checked'] for c in counts.values()),'per_factor':counts,
            'mismatch_count':len(mismatches),'mismatches':mismatches,'source_future_dated_changes':future_changes,
            'independent_source_query_validation':False,'actual_publication_time_certification':False,
            'limitations':['Replays existing archived vintages; no new independent ALFRED response.',
                          'Conservative schedule compatibility is not proof of actual publication time.',
                          'Future-observation source entries are excluded until observation date is no later than cutoff.']}

def main():
    paths=['storage/phase4_publication_aware_panel.json','storage/phase3_fred_pit_vintages.json']
    blobs=[(ROOT/p).read_bytes() for p in paths]
    report=replay_audit(*(json.loads(b) for b in blobs))
    report['input_sha256']={p:hashlib.sha256(b).hexdigest() for p,b in zip(paths,blobs)}
    report['checked_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    (ROOT/'docs/pit_full_replay_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','checks','mismatch_count','per_factor')}))
    if report['mismatch_count']:raise SystemExit(1)
if __name__=='__main__':main()
