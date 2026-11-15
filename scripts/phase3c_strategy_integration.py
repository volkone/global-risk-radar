"""3C-01: scenario-only TAIEX tranche policy linked to audited prospective evidence.

No broker integrations, orders, live recommendations or retroactive forecasts.
"""
import argparse,datetime as dt,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/phase3c_strategy_integration.json'
TRANCHES=[(-5,1000000),(-10,1000000),(-15,2000000),(-20,2000000),(-25,2000000)]
ANCHOR=45211
def build(anchor=ANCHOR,market_close=None,prospective=None):
 if not isinstance(anchor,(int,float)) or anchor<=0:raise ValueError('anchor must be positive')
 if market_close is not None and (not isinstance(market_close,(int,float)) or market_close<=0):raise ValueError('close must be positive')
 stages=[]
 for pct,amount in TRANCHES:
  trigger=round(anchor*(1+pct/100),2)
  reached=market_close is not None and market_close<=trigger
  stages.append({'drawdown_from_fixed_anchor_pct':pct,'trigger_taiex_points':trigger,'planned_twd':amount,'historical_scenario_reached':reached if market_close is not None else None,'order_authorized':False})
 return {'schema_version':1,'status':'scenario_only_not_investment_instruction','anchor_taiex_points':anchor,'anchor_source':'user_supplied_historical_reference_not_live_index','market_close':market_close,'market_close_verified':False,'stages':stages,'planned_total_twd':sum(v for _,v in TRANCHES),'tranche_basis':'independent drawdown from fixed reference, not compounded sequential drops','prospective_evaluation_status':prospective.get('status') if prospective else None,'prospective_snapshots':prospective.get('snapshots') if prospective else None,'prospective_model_validated':False,'risk_policy':{'when_unvalidated':'display scenarios and evidence only; no entry or risk alert instruction','when_missing_source':'do not extrapolate current score','threshold_change':'prohibited without new frozen prospective cohort'},'order_execution_enabled':False,'telegram_alert_enabled':False,'automatic_trading_enabled':False}
def test():
 r=build()
 assert r['planned_total_twd']==8000000
 assert [x['trigger_taiex_points'] for x in r['stages']]==[42950.45,40689.9,38429.35,36168.8,33908.25]
 assert all(x['historical_scenario_reached'] is None and not x['order_authorized'] for x in r['stages'])
 assert build(market_close=40000)['stages'][1]['historical_scenario_reached'] is True
 try:build(anchor=0);raise AssertionError('invalid anchor accepted')
 except ValueError:pass
 print('3C_SCENARIO_SELFTEST_PASS')
def main():
 p=argparse.ArgumentParser();p.add_argument('--selftest',action='store_true');a=p.parse_args()
 if a.selftest:test();return
 status_path=ROOT/'docs/prospective_evaluation.json'
 prospective=json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else None
 out=build(prospective=prospective)
 out['generated_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
 OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('3C_STRATEGY_SCENARIO_ONLY',out['planned_total_twd'],out['prospective_evaluation_status'])
if __name__=='__main__':main()
