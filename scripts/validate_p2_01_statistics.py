"""P2-01: dependence-aware quality audit of fixed, out-of-sample risk alerts."""
import json,random,math,hashlib
from pathlib import Path
from backtest_phase2_research import SOURCE,prepare,percentile,numeric,LOOKBACK,TRAIN_FRACTION,ALERT_QUANTILE,HORIZONS
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs/p2_01_statistical_validation.json"
KEYS=("foreign_tx_short_pressure","margin_deleveraging_20d","institutional_net_selling_5d","twd_depreciation_20d","hy_oas_widening_20d","prior_us_vix_level")
SEED=20261114
def metrics(a,e):
 n=len(a);tp=sum(x and y for x,y in zip(a,e));fp=sum(x and not y for x,y in zip(a,e));fn=sum(not x and y for x,y in zip(a,e));tn=n-tp-fp-fn
 div=lambda x,y:x/y if y else None
 return {"tp":tp,"fp":fp,"fn":fn,"tn":tn,"n":n,"precision":div(tp,tp+fp),"recall":div(tp,tp+fn),"specificity":div(tn,tn+fp),"false_positive_rate":div(fp,fp+tn),"false_negative_rate":div(fn,fn+tp),"base_rate":div(tp+fn,n),"precision_lift":div(div(tp,tp+fp),div(tp+fn,n)) if n and tp+fp and tp+fn else None}
def effect(a,e):
 m=metrics(a,e)
 return m["precision"]-m["base_rate"] if m["precision"] is not None else None
def bootstrap(a,e,block,reps=3000):
 rng=random.Random(SEED+block);n=len(a);values=[]
 for _ in range(reps):
  idx=[]
  while len(idx)<n:
   s=rng.randrange(n);idx.extend((s+j)%n for j in range(block))
  idx=idx[:n]
  d=effect([a[i] for i in idx],[e[i] for i in idx])
  if d is not None:values.append(d)
 values.sort()
 return {"block_length":block,"replicates_valid":len(values),"precision_minus_base_rate_ci95":[values[int(.025*(len(values)-1))],values[int(.975*(len(values)-1))]] if values else None}
def shifts(a,e):
 # Exact finite circular shifts; preserve both time-series' internal autocorrelation.
 obs=effect(a,e);n=len(a)
 null=[effect(a,e[k:]+e[:k]) for k in range(1,n)]
 valid=[x for x in null if x is not None]
 return {"test":"circular_shift_one_sided_precision_lift","shifts_evaluated":len(valid),
         "p_value":(1+sum(x>=obs-1e-12 for x in valid))/(len(valid)+1) if obs is not None else None,
         "assumption":"Stationarity under cyclic shifts; not reliable under regime changes; overlapping outcomes retained"}
def main():
 raw=SOURCE.read_bytes();panel=json.loads(raw);rows=panel["rows"];dates=[x["date"] for x in rows]
 assert len(rows)==718 and panel["formal_backtest_authorized"] is False
 feats=prepare(rows);split=int(len(rows)*TRAIN_FRACTION)
 distributions={k:sorted(x[k] for x in feats[LOOKBACK:split] if x and k in x) for k in KEYS}
 assert all(len(v)>=150 for v in distributions.values())
 scores=[]
 for f in feats:
  ranks=[percentile(f[k],distributions[k]) for k in KEYS if f and k in f]
  scores.append(sum(ranks)/len(ranks) if len(ranks)>=5 else None)
 train=sorted(x for x in scores[LOOKBACK:split] if x is not None)
 threshold=train[min(len(train)-1,int(len(train)*ALERT_QUANTILE))]
 results={}
 for horizon,cutoff in HORIZONS.items():
  alerts=[];events=[];valid_dates=[]
  for i in range(split,len(rows)-horizon):
   p=rows[i].get("taiex_price_index_close")
   future=[x.get("taiex_price_index_close") for x in rows[i+1:i+horizon+1]]
   if scores[i] is None or not numeric(p) or p<=0 or any(not numeric(x) or x<=0 for x in future):continue
   alerts.append(scores[i]>=threshold);events.append(100*(min(future)/p-1)<=cutoff);valid_dates.append(dates[i])
  m=metrics(alerts,events)
  assert m["tp"]+m["fp"]+m["fn"]+m["tn"]==m["n"]
  ci=bootstrap(alerts,events,horizon)
  shift=shifts(alerts,events)
  results[str(horizon)+"d"]={"event_threshold_pct":cutoff,"range":[valid_dates[0],valid_dates[-1]],"confusion_matrix":m,"effect_precision_minus_base_rate":effect(alerts,events),
    "moving_block_bootstrap":ci,"circular_shift_null":shift,
    "bonferroni_adjusted_p_value":min(1,2*shift["p_value"]) if shift["p_value"] is not None else None,
    "nominal_significance_0_05":bool(shift["p_value"] is not None and shift["p_value"]<0.025 and ci["precision_minus_base_rate_ci95"][0]>0),
    "limitations":["Overlapping forward event labels and clustered alerts reduce effective sample size","Circular shift assumes approximate stationarity","Block bootstrap intervals depend on chosen block size","No economic profitability or calibration validation"]}
 report={"stage":"P2-01","status":"statistical_validation_completed","panel_sha256":hashlib.sha256(raw).hexdigest(),
  "method":"Fixed train-only alert threshold, chronological holdout, exact circular shift null and seeded moving-block bootstrap",
  "seed":SEED,"bootstrap_replicates":3000,"multiple_testing":"Bonferroni across 5d and 20d horizons; family-wise alpha 0.05",
  "holdout":results,"statistical_significance_not_equal_to_live_readiness":True,
  "full_model_backtest_authorized":False,"recommended_live_threshold":None,
  "caveat":"Exploratory research; historical publication vintages and official TXF exception remain uncertified"}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({k:{"counts":v["confusion_matrix"],"p":v["circular_shift_null"]["p_value"],"ci":v["moving_block_bootstrap"]["precision_minus_base_rate_ci95"],"significant":v["nominal_significance_0_05"]} for k,v in results.items()}))
if __name__=="__main__":main()
