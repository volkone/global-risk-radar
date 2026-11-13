"""Audit matured first-seen outcomes and summarize; never self-certifies a model."""
import datetime as dt
import json
from pathlib import Path
from phase5_forward_ledger import verified_snapshot,session_sequence
from phase5_forward_capture import canonical,sha,verify_frozen
ROOT=Path(__file__).resolve().parents[1]

def metrics(rows):
    n=len(rows);tp=sum(r['alert'] and r['event'] for r in rows)
    fp=sum(r['alert'] and not r['event'] for r in rows)
    fn=sum(not r['alert'] and r['event'] for r in rows)
    tn=n-tp-fp-fn
    ratio=lambda a,b:a/b if b else None
    return dict(samples=n,alerts=tp+fp,events=tp+fn,true_positive=tp,false_positive=fp,false_negative=fn,true_negative=tn,
                precision=ratio(tp,tp+fp),false_positive_rate=ratio(fp,fp+tn),recall=ratio(tp,tp+fn),base_event_rate=ratio(tp+fn,n))

def nonoverlap(rows):
    chosen=[];end=''
    for r in sorted(rows,key=lambda x:x['date']):
        if r['date']>end:chosen.append(r);end=r['end']
    return chosen

def audit_outcome(outcome,pred,snapshots,expected,protocol_hash):
    day=pred['forecast_session'];h=outcome['horizon']
    if h not in (5,20) or outcome['forecast_session']!=day:raise ValueError('outcome_identity')
    if pred['frozen_protocol_sha256']!=protocol_hash or outcome['forecast_sha256']!=sha(canonical(pred)):raise ValueError('forecast_hash')
    anchor=expected.index(day);dates=expected[anchor+1:anchor+h+1]
    if len(dates)!=h or dates!=outcome['forward_snapshot_dates'] or any(d not in snapshots for d in dates):raise ValueError('incomplete_window')
    created=dt.datetime.fromisoformat(pred['created_at_utc'])
    if created.astimezone(dt.timezone(dt.timedelta(hours=8))).date().isoformat()!=day:raise ValueError('backdated_forecast')
    times=[dt.datetime.fromisoformat(snapshots[d]['completed_at_utc']) for d in dates]
    if any(t<=created for t in times):raise ValueError('outcome_known_before_prediction')
    if dt.datetime.fromisoformat(outcome['created_after_forward_window_completed_at_utc'])<max(times):raise ValueError('premature_outcome')
    price=snapshots[day]['sources']['taiex']['value'][0]
    prices=[snapshots[d]['sources']['taiex']['value'][0] for d in dates]
    worst=round(100*(min(prices)/price-1),5);terminal=round(100*(prices[-1]/price-1),5)
    cutoff=-3.0 if h==5 else -5.0
    if (outcome['worst_forward_close_drawdown_pct']!=worst or outcome['terminal_forward_price_return_pct']!=terminal
        or outcome['event_cutoff_pct']!=cutoff or outcome['event_occurred'] is not (worst<=cutoff)):
        raise ValueError('outcome_value_mismatch')
    return dict(date=day,end=dates[-1],alert=pred['score']>=pred['frozen_research_threshold'],event=worst<=cutoff)

def main():
    frozen=verify_frozen();protocol_hash=sha((ROOT/'docs/phase4_frozen_prospective_protocol.json').read_bytes())
    snapshots={};hashes={}
    for path in sorted((ROOT/'storage/prospective/snapshots').glob('*.json')):
        snap,digest=verified_snapshot(path);snapshots[snap['session_date']]=snap;hashes[snap['session_date']]=digest
    expected=session_sequence(snapshots);groups={5:[],20:[]};errors=[];seen=set()
    for path in sorted((ROOT/'storage/prospective/outcomes').glob('*.json')):
        try:
            out=json.loads(path.read_bytes());identity=(out['forecast_session'],out['horizon'])
            if identity in seen:raise ValueError('duplicate_outcome')
            seen.add(identity)
            pred=json.loads((ROOT/'storage/prospective/forecasts'/f'{identity[0]}.json').read_bytes())
            if pred['frozen_research_threshold']!=frozen['alert_score_threshold_frozen_before_future_outcomes']:raise ValueError('threshold_changed')
            if not pred['feature_source_snapshots_sha256'] or any(hashes.get(d)!=v for d,v in pred['feature_source_snapshots_sha256'].items()):raise ValueError('source_hash')
            groups[out['horizon']].append(audit_outcome(out,pred,snapshots,expected,protocol_hash))
        except (OSError,KeyError,TypeError,ValueError) as exc:errors.append({'file':path.name,'error':str(exc)})
    report={'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'status':'audit_failed' if errors else 'waiting_for_matured_outcomes' if not any(groups.values()) else 'research_metrics_available',
            'frozen_protocol_sha256':protocol_hash,'snapshots':len(snapshots),'errors':errors,
            'horizons':{str(h)+'d':{'all_overlapping':metrics(rows),'nonoverlapping':metrics(nonoverlap(rows))} for h,rows in groups.items()},
            'independent_validation_passed':False,
            'limitations':['Automated ledger verification is not independent model certification.',
                          'Nonoverlap cohort uses earliest eligible anchor and excludes shared boundaries.',
                          'Zero events or alerts produce null ratios, never invented 0% accuracy.',
                          'The frozen minimum of 30 nonoverlapping observations is a sample floor, not proof of predictive value.']}
    (ROOT/'docs/prospective_evaluation.json').write_bytes(canonical(report))
    print('FORWARD_EVALUATION',report['status'],len(errors))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
