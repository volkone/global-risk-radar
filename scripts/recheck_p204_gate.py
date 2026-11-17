"""P2-04 evidence reconciliation and fail-closed production gate rerun."""
import datetime as dt,json
from pathlib import Path
from model_gate import evaluate_gate
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def main():
 previous=read('docs/model_readiness.json')
 taifex=read('docs/taifex_source_verification.json')
 source=read('docs/p2_04_taifex_source_reconciliation.json')
 alfred=read('docs/p2_04_alfred_observation_recheck.json')
 notices=read('docs/taifex_hisnews_coverage.json')
 intervals=read('docs/alfred_vintage_interval_verification.json')
 official=read('docs/p2_04_taifex_official_primary_documents.json')
 forward=read('docs/phase5_forward_status.json')
 assert taifex['checked_records']==718 and taifex['counts']['pass']==718
 assert source['critical_record']['verification_status']=='pass'
 assert alfred['verified']==18 and alfred['mismatch']==0 and alfred['fetch_errors']==0
 today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
 forecast_path=ROOT/'storage/prospective/forecasts'/f'{today}.json'
 forecast=json.loads(forecast_path.read_text(encoding='utf-8')) if forecast_path.exists() else None
 result=evaluate_gate(ROOT,previous['source_panel_sha256'],previous['frozen_protocol_sha256'],forecast,today)
 out={'schema_version':1,'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'EVIDENCE_RECHECKED_PRODUCTION_'+result['status'],
      'official_txf_daily_records_verified':718,'historical_2023_11_13_daily_source_verified':True,
      'alfred_independent_asof_sample_verified':18,'alfred_mismatch':0,
      'alfred_panel_values_verified':sum(x['panel_values_checked'] for x in intervals['series'].values()),
      'alfred_vintage_archive_differences':sum(x['differences'] for x in intervals['series'].values()),
      'historical_notice_months_queried':notices['months_matched'],
      'historical_notice_positive_controls_passed':all(notices['closure_positive_controls'].values()),
      'public_archive_coverage_verified':notices['public_archive_coverage_verified'],
      'historical_notice_count':notices['notice_count'],
      'official_historical_extract_acquired':official['official_historical_extract_acquired'],
      'formal_gate':result,'forward_capture_status':forward.get('status'),
      'note':'Public archive coverage is supported by unfiltered monthly and subdivided searches. Historical certification uses independently verified numeric values, vintage dates and prior-date replay. Model validation uses historical expanding-window evidence. Observed same-day scores are evaluated separately.'}
 (ROOT/'docs/p2_04_gate_recheck.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':out['status'],'checks':result['checks'],'alfred':18,'txf':718,'public_archive_coverage_verified':notices['public_archive_coverage_verified']},ensure_ascii=False))
if __name__=='__main__':main()
