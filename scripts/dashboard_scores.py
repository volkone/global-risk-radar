"""3B integration: versioned PIT panel + frozen research scores + daily prototypes.
Historical ranks use the frozen all-history reference distribution: descriptive
reconstruction only, NEVER a historical real-time forecast or new backtest.
"""
import copy
import datetime as dt
import hashlib
import json
import sqlite3
from zoneinfo import ZoneInfo
from phase5_forward_capture import verify_frozen
from phase5_forward_ledger import KEYS, frozen_distributions, verified_snapshot, score as frozen_score
from backtest_phase2_research import prepare, percentile, numeric
from history import ROOT, DATABASE

PANEL = ROOT / 'storage/phase4_publication_aware_panel.json'
OUT = ROOT / 'docs/risk_dashboard.json'
LABELS = ['外資台指期淨空壓力', '融資 20 日減槓桿', '法人現貨 5 日淨賣超',
          '台幣 20 日貶值', '高收益債利差 20 日擴大', 'VIX 水準']


def clean_rows(rows):
    dates = [r['date'] for r in rows]
    if dates != sorted(set(dates)):
        raise ValueError('duplicate_or_unsorted_sessions')
    result = copy.deepcopy(rows)
    for r in result:
        tx = [r.get(k) for k in ('tx_oi_long_contracts','tx_oi_short_contracts','tx_oi_net_contracts')]
        if not all(numeric(v) for v in tx) or min(tx[:2]) < 0 or tx[0]-tx[1] != tx[2]:
            r['tx_oi_net_contracts'] = None
        if not numeric(r.get('margin_balance_twd')) or r['margin_balance_twd'] <= 0:
            r['margin_balance_twd'] = None
        if not numeric(r.get('cash_institutional_net_twd')):
            r['cash_institutional_net_twd'] = None
        for k, o in r['us_previous_dated_observations'].items():
            valid = (numeric(o.get('value')) and o.get('time_gate_passed') is True
                     and o.get('stale') is False and isinstance(o.get('observed_date'),str)
                     and o['observed_date'] < r['date'])
            if o.get('conservative_earliest_use_at_taipei'):
                valid = valid and (dt.datetime.fromisoformat(o['conservative_earliest_use_at_taipei'])
                                   <= dt.datetime.fromisoformat(o['decision_at_taipei']))
            if not valid:
                o['value'] = None
    return result


def components(feat, distributions):
    result = []
    for key, label in zip(KEYS, LABELS):
        val = (feat or {}).get(key)
        rank = percentile(val, distributions[key]) if numeric(val) and distributions[key] else None
        result.append({'metric':key,'label':label,'raw_value':val,'signal':rank,
                       'eligible':rank is not None,'reason':None if rank is not None else '缺值、品質未過或尚未滿足回看期'})
    used = sum(c['eligible'] for c in result)
    for c in result:
        c['effective_weight'] = 1/used if c['eligible'] and used else 0
        c['contribution'] = c['signal']/used if c['eligible'] and used else None
    return result


def reconstruct(rows, distributions, lag):
    feats = prepare(clean_rows(rows))
    history = []
    for i, r in enumerate(rows):
        source = i-lag
        cs = components(feats[source] if source >= 0 else None, distributions)
        n = sum(c['eligible'] for c in cs)
        score = round(sum(c['contribution'] or 0 for c in cs),5) if n >= 5 else None
        history.append({'date':r['date'],'score':score,'coverage':n/6,
                        'signal_date':rows[source]['date'] if source >= 0 else None,
                        'components':cs,'status':'historical_reconstruction' if score is not None else 'insufficient_coverage'})
    return history


def calibration_report(panel, digest, frozen, history):
    features = prepare(clean_rows(panel['rows']))
    distributions = frozen_distributions()
    latest = next((r for r in reversed(history) if r['score'] is not None), None)
    signals = {}
    for key, label in zip(KEYS, LABELS):
        c = next((c for c in (latest or {}).get('components',[]) if c['metric']==key), {})
        signals[key] = dict(c, label=label,
            raw_observations=len(panel['rows']),
            transformed_observations=sum(numeric((f or {}).get(key)) for f in features),
            reference_observations=len(distributions[key]),
            current_date=(latest or {}).get('signal_date'),
            status='research_calibrated' if c.get('eligible') else 'insufficient_history')
    return {'schema_version':2,'model_id':'frozen_six_factor_research',
            'model_status':'research_only','source_panel_sha256':digest,
            'historical_sessions':len(panel['rows']),
            'valid_historical_scores':sum(r['score'] is not None for r in history),
            'method':'frozen_reference_distribution_descriptive_reconstruction',
            'signals':signals,'latest_research':latest,
            'research_threshold':frozen['alert_score_threshold_frozen_before_future_outcomes'],
            'notes':['使用與儀表板相同六因子、PIT 資料及凍結參考分布。',
                     '歷史重建不是當時已發出的訊號，也不是新的獨立回測。',
                     '舊五項加權原型已停用；不將三年資料直接拼接到不同定義的舊訊號。']}


def integrate(report, data):
    frozen = verify_frozen()
    raw = PANEL.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    timing = json.loads((ROOT/'docs/phase4_publication_timing_audit.json').read_text())
    if timing['output_sha256'] != digest:
        raise ValueError('publication_panel_audit_hash_mismatch')
    panel = json.loads(raw)
    history = reconstruct(panel['rows'], frozen_distributions(), frozen['post_close_feature_action_lag_taiwan_sessions'])
    latest = next((r for r in reversed(history) if r['score'] is not None), None)
    # Only expose already-issued and traceable prospective predictions. Never issue here.
    forecasts = []
    protocol_hash = hashlib.sha256((ROOT/'docs/phase4_frozen_prospective_protocol.json').read_bytes()).hexdigest()
    for path in sorted((ROOT/'storage/prospective/forecasts').glob('*.json')):
        pred = json.loads(path.read_text())
        if pred['frozen_protocol_sha256'] != protocol_hash:
            raise ValueError('forecast_protocol_mismatch')
        for date, expected_hash in pred['feature_source_snapshots_sha256'].items():
            _, actual_hash = verified_snapshot(ROOT/'storage/prospective/snapshots'/f'{date}.json')
            if actual_hash != expected_hash:
                raise ValueError('forecast_snapshot_hash_mismatch')
        created = dt.datetime.fromisoformat(pred['created_at_utc'])
        if (created.astimezone(ZoneInfo('Asia/Taipei')).date().isoformat() != pred['forecast_session']
                or path.stem != pred['forecast_session']
                or len(pred['feature_source_snapshots_sha256']) < 23
                or frozen_score(pred['model_feature_values'], frozen_distributions()) != pred['score']):
            raise ValueError('forecast_time_or_model_score_mismatch')
        forecasts.append({'date':pred['forecast_session'],'score':pred['score'],
                          'signal_date':pred['signal_observed_session'],
                          'components':components(pred['model_feature_values'], frozen_distributions()),
                          'status':'prospective_research','created_at_utc':pred['created_at_utc']})
    from model_gate import evaluate_gate
    today = dt.datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat()
    gate = evaluate_gate(ROOT, digest, protocol_hash, forecasts[-1] if forecasts else None, today)
    (ROOT/'docs/model_readiness.json').write_text(json.dumps(gate,ensure_ascii=False,indent=2)+'\n')
    official = forecasts[-1] if gate['status'] == 'PASS' else None
    calibration = calibration_report(panel, digest, frozen, history)
    (ROOT/'docs/calibration.json').write_text(json.dumps(calibration,ensure_ascii=False,indent=2)+'\n')
    report['taiwan_legacy_prototype'] = dict(report['taiwan'], deprecated=True, use_scope='inactive_legacy_diagnostic')
    report['taiwan'] = {
        'status':'validated' if official else 'formal_model_blocked','score':official['score'] if official else None,'coverage':sum(c['eligible'] for c in official['components'])/6 if official else 0,
        'components':official['components'] if official else [], 'formal_model_validated':bool(official),
        'as_of':official['date'] if official else None,'quality_gate':gate,
        'reason':'；'.join(gate['blockers']),
        'latest_research':forecasts[-1] if forecasts else latest,
        'research_threshold':frozen['alert_score_threshold_frozen_before_future_outcomes'],
        'research_min_factors':5,'research_factor_count':6}
    report['schema_version'] = 3
    report['model_status'] = 'separate_global_prototype_and_evidence_gated_taiwan'
    report['disclaimer'] = 'Global is provisional; historical Taiwan reconstruction is research-only. Formal Taiwan eligibility is recorded in quality_gate.'
    report['global']['model_id'] = 'global_rate_v2'
    report['global']['as_of'] = data.get('updated_utc')
    used = sum(c['weight'] for c in report['global']['components'] if c['eligible'])
    for c in report['global']['components']:
        c['contribution'] = c['signal']*c['weight']/used if c['eligible'] and used else None
    report['formal_model_status'] = gate['status']
    stamp = data.get('updated_utc') or report['generated_at']
    with sqlite3.connect(DATABASE) as db:
        db.execute('CREATE TABLE IF NOT EXISTS pit_panel_versions (sha256 TEXT, session_date TEXT, row_json TEXT NOT NULL, PRIMARY KEY(sha256,session_date))')
        db.executemany('INSERT OR IGNORE INTO pit_panel_versions VALUES(?,?,?)',
                       [(digest,r['date'],json.dumps(r,ensure_ascii=False,allow_nan=False)) for r in panel['rows']])
        db.execute('CREATE TABLE IF NOT EXISTS dashboard_score_snapshots (observed_at TEXT, model TEXT, payload TEXT NOT NULL, PRIMARY KEY(observed_at,model))')
        db.execute('INSERT OR IGNORE INTO dashboard_score_snapshots VALUES(?,?,?)',
                   (stamp,'global_rate_v2',json.dumps(report['global'],ensure_ascii=False,allow_nan=False)))
        global_history = [dict(date=s, **json.loads(payload)) for s,payload in db.execute(
            "SELECT observed_at,payload FROM dashboard_score_snapshots WHERE model='global_rate_v2' ORDER BY observed_at")]
    payload = {'schema_version':1,'generated_at':report['generated_at'],
               'formal_model_status':gate['status'],'source_panel_sha256':digest,
               'historical_sessions':len(history), 'valid_historical_scores':sum(r['score'] is not None for r in history),
               'global':report['global'],'taiwan':report['taiwan'],
               'taiwan_history':history,'global_history':global_history,'prospective_history':forecasts,
               'limitations':['台灣歷史曲線使用全期間凍結分布重建，並非當時發出的預測，不能作為無前視回測績效。',
                              '全球逐次留存與三年描述性重建分開顯示；重建曲線不是事前預測或 PIT 回測。',
                              '研究分數不是下跌機率；全球原型與台灣六因子模型不宜直接比較高低。',
                              '正式評分依獨立證據關卡判定；資料不齊不等於低風險。']}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    print('3B dashboard:',len(history),'sessions;',payload['valid_historical_scores'],'research scores; formal',gate['status'])
    return report
