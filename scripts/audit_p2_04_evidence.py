"""P2-04 conservative evidence audit. Inventory is NOT primary-source certification."""
import datetime as dt, hashlib, json
from pathlib import Path
from model_gate import evaluate_gate
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'docs'
def load(p):
    f=ROOT/p
    try:
        raw=f.read_bytes()
        return json.loads(raw),hashlib.sha256(raw).hexdigest()
    except (OSError,ValueError):return {},None
def main():
    pub,_=load('docs/phase4_publication_timing_audit.json')
    vintage,_=load('docs/phase3_pit_source_audit.json')
    samples,_=load('docs/phase3_vintage_audit.json')
    taifex,_=load('docs/taifex_prebacktest_gate.json')
    cal,_=load('docs/taifex_calendar_independent_audit.json')
    official,_=load('docs/official_source_evidence_2026_11_14.json')
    fwd,_=load('docs/phase5_forward_status.json')
    ready,_=load('docs/model_readiness.json')
    sessions=pub.get('sessions')
    assert sessions==718 and taifex.get('record_count')==718
    assert pub.get('output_sha256')==ready.get('source_panel_sha256')
    assert vintage.get('historical_pit_daily_panel_ready') is True
    factors=vintage.get('series_status',{})
    assert len(factors)==6
    publication={
        'sessions':sessions,
        'source_clock_certified':pub.get('source_clock_gates_fully_certified') is True,
        'all_actual_publication_timestamps_verified':pub.get('actual_publication_timestamps_verified_for_all_718') is True,
        'all_revisions_independently_verified':pub.get('data_revisions_independently_verified_for_all_718') is True,
        'source_time_uncertified_counts':pub.get('not_source_time_certified_records',{}),
        'sample_vintage_violations':samples.get('violations_count'),
        'sample_vintage_checks':samples.get('series_sample_size'),
        'source_clock_assumptions':pub.get('policy',{}),
        'status':'CERTIFIED' if all(pub.get(k) is True for k in ('source_clock_gates_fully_certified','actual_publication_timestamps_verified_for_all_718','data_revisions_independently_verified_for_all_718')) else 'BLOCKED'
    }
    fred={
        'series_count':len(factors),
        'vintage_dates_covered':{k:v.get('valid_asof_dates') for k,v in factors.items()},
        'independent_full_series_requery':official.get('alfred',{}).get('vintage_dates_independently_requeried_for_all_series') is True,
        'independent_value_comparison':official.get('alfred',{}).get('observation_values_independently_compared') is True,
        'historical_intraday_publication_certified':official.get('publication',{}).get('historical_minute_level_timestamps_certified') is True,
        'limitations':vintage.get('limitations',[]),
    }
    fred['status']='CERTIFIED' if all(fred[k] for k in ('independent_full_series_requery','independent_value_comparison','historical_intraday_publication_certified')) else 'BLOCKED'
    tx={
        'records':taifex.get('record_count'),
        'official_raw_values_verified':taifex.get('raw_source_values_verified'),
        'unverified_dates':taifex.get('raw_source_unverified_dates',[]),
        'annual_calendar_sources_recorded':cal.get('annual_calendar_sources_recorded'),
        'special_date_groups':cal.get('special_date_group_count'),
        'full_notice_sweep_verified':taifex.get('full_notice_sweep_verified') is True,
        'independent_calendar_verified':taifex.get('independent_taifex_calendar_verified') is True,
        'primary_evidence_complete':taifex.get('primary_evidence_complete') is True,
        'official_historical_data_request':taifex.get('official_historical_data_request',{}),
    }
    tx['status']='CERTIFIED' if all(tx[k] for k in ('full_notice_sweep_verified','independent_calendar_verified','primary_evidence_complete')) and not tx['unverified_dates'] else 'BLOCKED'
    checks=ready.get('checks',[])
    assert len(checks)==5 and ready.get('status')=='BLOCKED'
    report={
        'schema_version':1,
        'status':'P2_04_EVIDENCE_INVENTORY_COMPLETE_CERTIFICATION_BLOCKED',
        'scope':'Reconcile existing repository evidence; no external official source reauthentication performed by this run',
        'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'source_evidence_hashes':{p:load(p)[1] for p in (
            'docs/phase4_publication_timing_audit.json','docs/phase3_pit_source_audit.json',
            'docs/phase3_vintage_audit.json','docs/taifex_prebacktest_gate.json',
            'docs/taifex_calendar_independent_audit.json','docs/official_source_evidence_2026_11_14.json',
            'docs/model_readiness.json','docs/phase5_forward_status.json')},
        'steps':{
            '1_publication_and_PIT':publication,
            '2_FRED_vintages':fred,
            '3_TAIFEX_official_calendar_and_TXF':tx,
            '4_formal_quality_gate':{'status':ready['status'],'checks':checks,'blockers':ready['blockers'],
              'previously_blocked_conditions_cleared':[]},
            '5_prospective_capture':{'status':fwd.get('status'),'first_observed_session':fwd.get('first_observed_session'),
              'last_observed_session':fwd.get('last_observed_session'),
              'snapshots':fwd.get('prospective_immutable_snapshots'),
              'predictions':fwd.get('research_predictions_total'),
              'outcomes':fwd.get('research_outcome_files_total'),
              'frozen_protocol_sha256':fwd.get('frozen_protocol_sha256'),
              'must_continue_existing_capture_workflow':True}
        },
        'next_required_actions':[
            'Obtain independently authenticated source release timestamps and revised-value evidence for all relevant sessions',
            'Requery ALFRED vintages and compare source values across all six series; preserve response hashes',
            'Obtain official TXF 2023-11-13 investor open-interest extract; reconcile full official closure notice archive',
            'Rerun production model gate only after actual evidence is updated',
            'Keep existing forward capture schedule and immutable forecasts; do not backfill retrospective predictions'],
        'formal_backtest_authorized':False,'production_scoring_authorized':False,'live_trading_authorized':False}
    assert all(report['steps'][k]['status']=='BLOCKED' for k in ('1_publication_and_PIT','2_FRED_vintages','3_TAIFEX_official_calendar_and_TXF'))
    out=D/'p2_04_evidence_audit.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'publication':publication['status'],'fred':fred['status'],'taifex':tx['status'],'gate':ready['status'],'forward':fwd.get('status')},ensure_ascii=False))
if __name__=='__main__':main()
