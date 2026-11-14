"""Independent uptrend-deterioration hypothesis, retrospective purged walk-forward only.

Design is specified after prior holdout was examined. Therefore even a newly
computed historical OOS score is NOT an untouched confirmatory holdout.
"""
import json,hashlib,random
from pathlib import Path
from backtest_phase2_research import SOURCE,numeric
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"docs/p2_03_uptrend_early_warning_research.json"
HORIZONS={5:-3.0,20:-5.0};STARTS=(400,500,600);SEED=20261114;REPS=1200
def div(x,y):return x/y if y else None
def metrics(c):
 n=len(c);a=sum(x["alert"] for x in c);e=sum(x["event"] for x in c);hit=sum(x["alert"] and x["event"] for x in c)
 return {"n":n,"alerts":a,"events":e,"hits":hit,"precision":div(hit,a),"recall":div(hit,e),"base_rate":div(e,n),"precision_lift":div(div(hit,a),div(e,n)) if a and e else None}
def main():
 raw=SOURCE.read_bytes();p=json.loads(raw);rows=p["rows"];assert len(rows)==718 and p["formal_backtest_authorized"] is False
 n=len(rows);dates=[r["date"] for r in rows];close=[r["taiex_price_index_close"] for r in rows]
 # Candidate early-warning hypothesis: past-only uptrend, short-term deceleration,
 # and institutional selling. No outcome-driven feature selection or optimization.
 trend=[];decel=[];selling=[]
 for i,r in enumerate(rows):
  ok=i>=20 and all(numeric(close[j]) and close[j]>0 for j in (i,i-5,i-10,i-20))
  if not ok:trend.append(False);decel.append(False)
  else:
   t20=100*(close[i]/close[i-20]-1)
   r5=100*(close[i]/close[i-5]-1)
   prev5=100*(close[i-5]/close[i-10]-1)
   trend.append(t20>2)
   decel.append(r5<prev5 and r5<1)
  cash=[rows[j].get("cash_institutional_net_twd") for j in range(max(0,i-4),i+1)]
  selling.append(len(cash)==5 and all(numeric(v) for v in cash) and sum(cash)<0)
 # Compare fixed predeclared rule to an uptrend-only baseline.
 # Signal observed after close t, forward label starts t+1.
 signals=[trend[i] and decel[i] and selling[i] for i in range(n)]
 results={}
 for h,cut in HORIZONS.items():
  folds=[];all_cases=[]
  for start in STARTS:
   end=min(start+100,n-h)
   # h-day embargo between prior outcomes and new test period; rule has no fitted parameters.
   train_end=start-h
   assert train_end>20
   cases=[]
   for i in range(start,end):
    future=close[i+1:i+h+1]
    if not numeric(close[i]) or close[i]<=0 or any(not numeric(v) or v<=0 for v in future):continue
    if not trend[i]:continue
    event=100*(min(future)/close[i]-1)<=cut
    cases.append({"index":i,"date":dates[i],"alert":signals[i],"event":event})
   folds.append({"test_dates":[dates[start],dates[end-1]],"prior_label_embargo_sessions":h,"uptrend_eligible":metrics(cases)})
   all_cases+=cases
  assert len(set(x["index"] for x in all_cases))==len(all_cases)
  agg=metrics(all_cases)
  # Circular shift null preserves event and alert autocorrelation, within uptrend eligible series.
  aa=[x["alert"] for x in all_cases];ee=[x["event"] for x in all_cases]
  observed=agg["precision"]-agg["base_rate"] if agg["precision"] is not None else None
  shifted=[]
  if observed is not None:
   for k in range(1,len(ee)):
    rotated=ee[k:]+ee[:k]
    hit=sum(a and e for a,e in zip(aa,rotated))
    shifted.append(hit/sum(aa)-sum(rotated)/len(rotated))
  pvalue=(1+sum(v>=observed-1e-12 for v in shifted))/(1+len(shifted)) if shifted else None
  rng=random.Random(SEED+h);effects=[]
  if aa:
   for _ in range(REPS):
    idx=[]
    while len(idx)<len(aa):
     s=rng.randrange(len(aa));idx.extend((s+j)%len(aa) for j in range(h))
    idx=idx[:len(aa)];sa=[aa[j] for j in idx];se=[ee[j] for j in idx]
    if sum(sa):effects.append(sum(a and e for a,e in zip(sa,se))/sum(sa)-sum(se)/len(se))
  effects.sort()
  ci=[effects[int(.025*(len(effects)-1))],effects[int(.975*(len(effects)-1))]] if len(effects)>=REPS*.9 else None
  results[str(h)+"d"]={"folds":folds,"aggregate":agg,"lift_difference":observed,
    "moving_block_ci95":ci,"circular_shift_one_sided_p":pvalue,
    "bonferroni_two_horizons_p":min(1,2*pvalue) if pvalue is not None else None,
    "warning":"Regime filtering changes event prevalence; comparison is to uptrend-only base rate, not all-market base rate"}
 report={"stage":"uptrend_early_warning_research","status":"retrospective_walk_forward_complete_prospective_confirmation_pending",
  "panel_sha256":hashlib.sha256(raw).hexdigest(),
  "hypothesis":"Uptrend (past 20-session return >2%) AND 5-session momentum deceleration (recent 5-session return below preceding 5-session return and below +1%) AND trailing 5-session institutional net selling",
  "evaluation":"Three disjoint historical 100-session forward test blocks, uptrend-only evaluation, future drawdown events 5d -3% / 20d -5%; signal after t close, outcome t+1 onward",
  "method_note":"Fixed rule, no parameter fitting. Embargo specified for label hygiene; this is retrospective reuse of historical data already studied in P2-02, not an untouched independent confirmation.",
  "results":results,"data_source_restrictions":["FRED vintage and TXF official exception unresolved","Preselected candidate after inspecting historical model failure; selection bias cannot be eliminated retrospectively"],
  "prospective_validation_plan":{"start":"First new session after 2026-10-30 for which all PIT data can be certified","requirements":["Freeze rule and source hash before observation","Accumulate new unseen outcomes for both horizons","No threshold edits during collection","Re-evaluate serial dependence and uncertainty after sufficient independent event clusters"]},
  "live_trading_authorized":False,"full_model_validated":False,"recommended_live_threshold":None}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"status":report["status"],"results":results}))
if __name__=="__main__":main()
