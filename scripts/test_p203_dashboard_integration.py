"""P2-03 regression checks: verify source JSON, DOM wiring, and isolation without trading authorization."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'docs'
index=(D/'index.html').read_text(encoding='utf-8')
research=(D/'p203_research.js').read_text(encoding='utf-8')
legacy=(D/'dashboard.js').read_text(encoding='utf-8')
assert index.count('id="p203-research"')==1
assert index.count('<script src="dashboard.js"></script>')==1
assert index.count('<script src="p203_research.js"></script>')==1
assert index.index('dashboard.js')<index.index('p203_research.js')
for id in ('global-score','taiwan-score','formal-score','risk-chart','risk-factors','risk-date','risk-series','risk-range','gate-checks','forward-health'):
 assert 'id="'+id+'"' in index,id
assert 'p203-research' not in legacy
assert 'global-score' not in research and 'taiwan-score' not in research
assert 'root.dataset.status=\'unavailable\'' in research
paths=('model_readiness.json','p2_01_statistical_validation.json','p2_02_robustness.json','p2_02_extended_validation.json','p2_02_failure_and_multiplicity.json','p2_03_uptrend_early_warning_research.json','risk_dashboard.json')
data={p:json.loads((D/p).read_text(encoding='utf-8')) for p in paths}
assert data['model_readiness.json']['status']=='BLOCKED'
assert data['risk_dashboard.json']['formal_model_status']=='BLOCKED'
ex=data['p2_02_extended_validation.json']['holdout'];mu=data['p2_02_failure_and_multiplicity.json']['factor_comparisons'];up=data['p2_03_uptrend_early_warning_research.json']['results']
def pct(x):return f'{x*100:.1f}%'
def fixed(x):return f'{x:.2f}'
expect={'walk_forward':{},'factors':{},'uptrend':{}}
for h in ('5d','20d'):
 expect['walk_forward'][h]=[pct(x['metrics']['precision']) for x in ex[h]['walk_forward_folds']]+[pct(ex[h]['walk_forward_aggregate']['precision'])]
 expect['factors'][h]={k:pct(v['full_minus_removed_precision']) for k,v in mu[h].items()}
 expect['uptrend'][h]={'precision':pct(up[h]['aggregate']['precision']),'base_rate':pct(up[h]['aggregate']['base_rate']),'adjusted_p':fixed(up[h]['bonferroni_two_horizons_p'])}
 assert len(ex[h]['walk_forward_folds'])==3 and len(mu[h])==6
assert not any(v['familywise_ci_excludes_zero'] for h in mu.values() for v in h.values())
assert data['p2_03_uptrend_early_warning_research.json']['live_trading_authorized'] is False
assert 'root.innerHTML=' in research and 'root.dataset.status=\'loaded\'' in research
print(json.dumps({'status':'passed_static_and_data_contract','expected_ui_values':expect,'note':'Not a real browser render or production HTTP smoke test'},ensure_ascii=False))
