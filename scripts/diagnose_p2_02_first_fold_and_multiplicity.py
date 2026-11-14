"""P2-02 follow-up: diagnose first walk-forward fold and simultaneous 12-test block-bootstrap intervals."""
import json,random,hashlib,math
from pathlib import Path
from backtest_phase2_research import SOURCE,prepare,percentile,numeric,LOOKBACK,HORIZONS,ALERT_QUANTILE
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"docs/p2_02_failure_and_multiplicity.json"
KEYS=("foreign_tx_short_pressure","margin_deleveraging_20d","institutional_net_selling_5d","twd_depreciation_20d","hy_oas_widening_20d","prior_us_vix_level")
REPS=2500;SEED=20261114
def precision(a,e):
 k=sum(a);return sum(x and y for x,y in zip(a,e))/k if k else None
def main():
 raw=SOURCE.read_bytes();p=json.loads(raw);rows=p["rows"];n=len(rows);assert n==718 and p["formal_backtest_authorized"] is False
 dates=[r["date"] for r in rows];close=[r["taiex_price_index_close"] for r in rows];feats=prepare(rows);split=int(n*.7)
 def model(end,exclude=None):
  dist={k:sorted(f[k] for f in feats[LOOKBACK:end] if f and k in f) for k in KEYS if k!=exclude}
  assert all(len(x)>=150 for x in dist.values())
  def score(i):
   f=feats[i];r=[percentile(f[k],dist[k]) for k in dist if f and k in f]
   return sum(r)/len(r) if len(r)>=(4 if exclude else 5) else None
  vals=sorted(x for i in range(LOOKBACK,end) if (x:=score(i)) is not None)
  return score,vals[min(len(vals)-1,int(len(vals)*ALERT_QUANTILE))]
 def cases(h,start,end,train_end,exclude=None):
  score,t=model(train_end,exclude);out=[]
  for i in range(start,min(end,n-h)):
   if not numeric(close[i]) or close[i]<=0 or any(not numeric(v) or v<=0 for v in close[i+1:i+h+1]):continue
   s=score(i)
   if s is None:continue
   event=100*(min(close[i+1:i+h+1])/close[i]-1)<=HORIZONS[h]
   past=100*(close[i]/close[i-20]-1) if i>=20 and numeric(close[i-20]) and close[i-20]>0 else None
   regime="up" if past is not None and past>2 else "down" if past is not None and past< -2 else "sideways"
   out.append({"date":dates[i],"alert":s>=t,"event":event,"regime":regime,"score":s})
  return out
 def stats(c):
  a=[x for x in c if x["alert"]];e=[x for x in c if x["event"]];hits=sum(x["event"] for x in a)
  return {"n":len(c),"alerts":len(a),"events":len(e),"hits":hits,"false_alerts":len(a)-hits,"missed_events":len(e)-hits,"precision":hits/len(a) if a else None,"base_rate":len(e)/len(c) if c else None,"alert_rate":len(a)/len(c) if c else None}
 diagnostics={}
 for h in (5,20):
  folds=[cases(h,s,s+100,s-h) for s in (400,500,600)]
  first=folds[0];other=folds[1]+folds[2]
  diagnostics[str(h)+"d"]={"first_fold":stats(first),"later_folds":stats(other),
   "first_fold_regimes":{g:stats([x for x in first if x["regime"]==g]) for g in ("up","down","sideways")},
   "later_fold_regimes":{g:stats([x for x in other if x["regime"]==g]) for g in ("up","down","sideways")},
   "first_fold_alert_dates":[x["date"] for x in first if x["alert"]],
   "first_fold_hit_dates":[x["date"] for x in first if x["alert"] and x["event"]],
   "first_fold_missed_event_dates":[x["date"] for x in first if not x["alert"] and x["event"]],
   "first_fold_event_dates":[x["date"] for x in first if x["event"]],
   "warning":"Descriptive decomposition only; changes in prevalence/regimes and clustered events are possible explanations, not proven causes"}
 # Paired bootstrap on identical original holdout rows, simultaneous max absolute centered deviations across 12 comparisons.
 holdouts={};observed={}
 for h in (5,20):
  full=cases(h,split,n-h,split)
  alt={k:cases(h,split,n-h,split,k) for k in KEYS}
  assert all(len(alt[k])==len(full) and [x["date"] for x in alt[k]]==[x["date"] for x in full] for k in KEYS)
  holdouts[h]=(full,alt)
  for k in KEYS:
   f=precision([x["alert"] for x in full],[x["event"] for x in full])
   z=precision([x["alert"] for x in alt[k]],[x["event"] for x in alt[k]])
   observed[(h,k)]=f-z
 rng=random.Random(SEED);samples={key:[] for key in observed}
 for _ in range(REPS):
  for h,(full,alt) in holdouts.items():
   size=len(full);ix=[]
   while len(ix)<size:
    s=rng.randrange(size);ix.extend((s+j)%size for j in range(h))
   ix=ix[:size];events=[full[i]["event"] for i in ix]
   f=precision([full[i]["alert"] for i in ix],events)
   for k in KEYS:
    z=precision([alt[k][i]["alert"] for i in ix],events)
    samples[(h,k)].append(f-z if f is not None and z is not None else None)
 # One common simultaneous critical value across all twelve comparisons.
 valid_draws=[j for j in range(REPS) if all(samples[key][j] is not None for key in observed)]
 maxima=sorted(max(abs(samples[key][j]-observed[key]) for key in observed) for j in valid_draws)
 assert len(maxima)>=REPS*.9
 critical=maxima[math.ceil(.95*len(maxima))-1]
 comparisons={}
 for h in (5,20):
  comparisons[str(h)+"d"]={}
  for k in KEYS:
   delta=observed[(h,k)]
   comparisons[str(h)+"d"][k]={"full_minus_removed_precision":delta,
      "simultaneous_95pct_ci":[delta-critical,delta+critical],
      "familywise_ci_excludes_zero":delta-critical>0 or delta+critical<0}
 report={"stage":"P2-02_followup","status":"diagnostics_and_multiplicity_computed","input_sha256":hashlib.sha256(raw).hexdigest(),
  "first_fold_diagnostics":diagnostics,
  "familywise_adjustment":{"method":"Joint max-absolute-centered paired circular moving-block bootstrap, simultaneous 95% confidence intervals across 12 horizon-factor comparisons",
    "replicates_requested":REPS,"joint_valid_replicates":len(valid_draws),"simultaneous_half_width":critical,
    "blocks":"5d and 20d respectively, same bootstrap index across full and ablated model within horizon",
    "caution":"Exploratory nonstudentized max-deviation bootstrap, sensitive to block choice, small samples and regime nonstationarity; not a calibrated exact p-value"},
  "factor_comparisons":comparisons,
  "conclusion_policy":"Do not claim confirmed factor importance unless simultaneous CI excludes zero, and even then only exploratory within this holdout",
  "limitations":["One initial weak fold does not identify a causal failure mechanism","Event rarity and alert clustering make first-fold precision unstable","First and later folds differ in historical periods and training sizes","Repeated overlapping outcomes are not independent","Historical FRED vintages and official TXF one-day evidence unresolved"],
  "full_model_validated":False,"full_model_backtest_authorized":False,"recommended_live_threshold":None}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"first_fold":diagnostics,"adjustment":report["familywise_adjustment"],"significant":{h:[k for k,v in c.items() if v["familywise_ci_excludes_zero"]] for h,c in comparisons.items()}},ensure_ascii=False))
if __name__=="__main__":main()
