"""Fail-closed, evidence-bound production eligibility. Never issues certification."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = {
    'publication': ('docs/phase4_publication_timing_audit.json',
                    ('actual_publication_timestamps_verified_for_all_718', 'source_clock_gates_fully_certified', 'data_revisions_independently_verified_for_all_718')),
    'calendar': ('docs/taifex_prebacktest_gate.json',
                 ('independent_taifex_calendar_verified', 'primary_evidence_complete', 'full_notice_sweep_verified')),
    'validation': ('docs/independent_model_validation.json', ('independent_validation_passed',)),
}
LABELS = {'publication':'歷史發布時間與版本逐筆認證', 'calendar':'期交所獨立交易日曆認證',
          'validation':'獨立前瞻驗證', 'authorization':'模型版本與證據授權', 'current_forecast':'當日可追溯前瞻分數'}

def read(root, path):
    try:
        raw = (root/path).read_bytes()
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError):
        return {}, None

def evaluate_gate(root, panel_hash, protocol_hash, forecast, today):
    checks = []
    hashes = {}
    for key, (path, fields) in EVIDENCE.items():
        obj, digest = read(root, path)
        hashes[path] = digest
        ok = bool(digest) and all(obj.get(k) is True for k in fields)
        if key == 'publication':
            ok = ok and obj.get('output_sha256') == panel_hash
        if key == 'validation':
            ok = (ok and obj.get('frozen_protocol_sha256') == protocol_hash
                  and obj.get('source_panel_sha256') == panel_hash
                  and all(type(obj.get('matured_nonoverlapping_events', {}).get(h)) is int
                          and obj['matured_nonoverlapping_events'][h] >= 30 for h in ('5d','20d')))
        checks.append({'id':key,'label':LABELS[key],'passed':bool(ok),'evidence':path})
    auth, _ = read(root, 'docs/production_model_authorization.json')
    authorized = (auth.get('production_scoring_authorized') is True
                  and auth.get('source_panel_sha256') == panel_hash
                  and auth.get('frozen_protocol_sha256') == protocol_hash
                  and all(v and auth.get('evidence_sha256', {}).get(p) == v for p,v in hashes.items()))
    checks.append({'id':'authorization','label':LABELS['authorization'],'passed':bool(authorized),
                   'evidence':'docs/production_model_authorization.json'})
    fresh = bool(forecast and forecast.get('status') == 'prospective_research'
                 and forecast.get('date') == today and isinstance(forecast.get('score'), (int,float))
                 and not isinstance(forecast.get('score'),bool) and 0 <= forecast['score'] <= 100)
    checks.append({'id':'current_forecast','label':LABELS['current_forecast'],'passed':fresh,
                   'evidence': 'storage/prospective/forecasts/' + today + '.json'})
    return {'status':'PASS' if all(c['passed'] for c in checks) else 'BLOCKED',
            'evaluated_for_date':today,'checks':checks,
            'blockers':[c['label'] for c in checks if not c['passed']],
            'source_panel_sha256':panel_hash,'frozen_protocol_sha256':protocol_hash}
