"""Fail-closed, evidence-bound production eligibility. Never issues certification."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE_EVIDENCE = 'docs/pit_publication_evidence_scope.json'
PANEL = 'storage/phase4_publication_aware_panel.json'
VINTAGES = 'storage/phase3_fred_pit_vintages.json'
FACTORS = {'fx', 'hy', 'ig', 'vix', 'us10y', 'nfci'}
EVIDENCE = {
    'publication': ('docs/alfred_vintage_interval_verification.json',
                    ('effective_date_intervals_verified_after_scoped_exclusion', 'panel_nonmissing_values_verified')),
    'calendar': ('docs/taifex_prebacktest_gate.json',
                 ('independent_taifex_calendar_verified', 'primary_evidence_complete', 'full_notice_sweep_verified')),
    'validation': ('docs/independent_model_validation.json', ('independent_validation_passed',)),
}
LABELS = {'publication':'歷史數值與版本日期認證', 'calendar':'期交所獨立交易日曆認證',
          'validation':'獨立前瞻驗證', 'authorization':'模型版本與證據授權', 'current_forecast':'當日可追溯前瞻分數'}

def read(root, path):
    try:
        raw = (root/path).read_bytes()
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError):
        return {}, None

def historical_version_check(root, report, panel_hash, scope):
    replay, _ = read(root, 'docs/pit_full_replay_audit.json')
    inputs = replay.get('input_sha256', {})
    vintage_hash = report.get('source_vintage_sha256')
    series = report.get('series', {})
    if not (
        report.get('source_panel_sha256') == scope.get('panel_sha256') == inputs.get(PANEL) == panel_hash
        and vintage_hash and vintage_hash == scope.get('raw_vintages_sha256') == inputs.get(VINTAGES)
        and scope.get('sessions') == replay.get('sessions') == 718
        and scope.get('replay_positions') == replay.get('checks') == 4308
        and scope.get('replay_mismatches_after_exclusion') == replay.get('mismatch_count') == 0
        and replay.get('status') == 'internal_replay_pass'
        and isinstance(series, dict) and series.keys() == FACTORS
    ):
        return False
    per_factor = replay.get('per_factor', {})
    return all(
        isinstance(item, dict)
        and item.get('differences_after_exclusion') == 0
        and item.get('panel_value_differences') == []
        and item.get('panel_values_checked') == per_factor.get(key, {}).get('matched_values')
        and item.get('panel_missing_values') == per_factor.get(key, {}).get('expected_missing')
        for key, item in series.items()
    )


def evaluate_gate(root, panel_hash, protocol_hash, forecast, today):
    checks = []
    hashes = {}
    for key, (path, fields) in EVIDENCE.items():
        obj, digest = read(root, path)
        hashes[path] = digest
        ok = bool(digest) and all(obj.get(k) is True for k in fields)
        if key == 'publication':
            scope, scope_digest = read(root, SCOPE_EVIDENCE)
            hashes[SCOPE_EVIDENCE] = scope_digest
            ok = ok and bool(scope_digest) and historical_version_check(root, obj, panel_hash, scope)
        if key == 'calendar' and 'excluded_dates' in obj:
            ok = (ok and obj.get('excluded_dates') == ['2023-11-13']
                  and obj.get('source_panel_sha256') == panel_hash
                  and obj.get('raw_source_values_verified') == obj.get('raw_source_values_expected') == 717)
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
