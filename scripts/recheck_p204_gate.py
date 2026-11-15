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
 notices=read('docs/taifex_notice_monthly_audit.json')
 official=read('docs/p2_04_taifex_official_primary_documents.json')
 forward=read('docs/phase5_forward_status.json')
 assert taifex['checked_records']==718 and taifex['counts']['pass']==718
 assert source['critical_record']['verification_status']=='pass'
 assert alfred['verified']==18 and alfred['mismatch']==0 and alfred['fetch_errors']==0
 assert len(notices['months'])==36 and notices['all_months_queried'] is True
 assert notices['pagination_exhaustive'] is False and official['all_pages_categories_and_notices_exhaustively_swept'] is False
 assert official['official_historical_extract_acquired'] is False
 today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
 forecast_path=ROOT/'storage/prospective/forecasts'/f'{today}.json'
 forecast=json.loads(forecast_path.read_text(encoding='utf-8')) if forecast_path.exists() else None
 result=evaluate_gate(ROOT,previous['source_panel_sha256'],previous['frozen_protocol_sha256'],forecast,today)
 assert result['status']=='BLOCKED' and not result['checks'][0]['passed'] and not result['checks'][1]['passed']
 out={'schema_version':1,'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'EVIDENCE_RECHECKED_PRODUCTION_BLOCKED',
      'official_txf_daily_records_verified':718,'historical_2023_11_13_daily_source_verified':True,
      'alfred_independent_asof_sample_verified':18,'alfred_mismatch':0,
      'historical_notice_months_queried':36,'historical_notice_positive_controls_passed':notices['positive_controls']['passed'],
      'archive_pagination_exhaustive':False,'official_historical_extract_acquired':False,
      'formal_gate':result,'forward_capture_status':forward.get('status'),
      'note':'Independent daily TAIFEX endpoint verification does not substitute for requested historical extract; 36 HTTP 200 form responses do not prove result coverage.'}
 (ROOT/'docs/p2_04_gate_recheck.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':out['status'],'checks':result['checks'],'alfred':18,'txf':718,'notices_exhaustive':False},ensure_ascii=False))
if __name__=='__main__':main()
