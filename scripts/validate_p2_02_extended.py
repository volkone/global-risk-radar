"""P2-02 extension: purged expanding walk-forward, block CI by regime, paired block ablations."""
import json,hashlib,random
from pathlib import Path
from backtest_phase2_research import SOURCE,prepare,percentile,numeric,LOOKBACK,HORIZONS,ALERT_QUANTILE
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"docs/p2_02_extended_validation.json"
KEYS=("foreign_tx_short_pressure","margin_deleveraging_20d","institutional_net_selling_5d","twd_depreciation_20d","hy_oas_widening_20d","prior_us_vix_level")
REPS=1500;SEED=20261114
def rate(a,e):
 n=len(a);alarms=sum(a);hits=sum(x and y for x,y in zip(a,e))
 return hits/alarms if alarms else None
def lift(a,e):
 p=rate(a,e)
 return p-sum(e)/len(e) if p is not None and e else None
def interval(vals):
 v=sorted(x for x in vals if x is not None)
 return [v[int(.025*(len(v)-1))],v[int(.975*(len(v)-1))]] if len(v)>=REPS*.9 else None
def block_indices(n,b,rng):
 out=[]
 while len(out)<n:
  start=rng.randrange(n)
  out.extend((start+j)%n for j in range(b))
 return out[:n]
def summary(a,e):
 return {"n":len(a),"alerts":sum(a),"events":sum(e),"hits":sum(x and y for x,y in zip(a,e)),"precision":rate(a,e),"precision_minus_base_rate":lift(a,e)}
def main():
 raw=SOURCE.read_bytes();p=json.loads(raw);rows=p["rows"];n=len(rows);assert n==718 and p["formal_backtest_authorized"] is False
 dates=[x["date"] for x in rows];feats=prepare(rows);close=[r["taiex_price_index_close"] for r in rows]
 regime=[]
 for i in range(n):
  if i<20 or not numeric(close[i]) or not numeric(close[i-20]) or close[i-20]<=0:regime.append("unknown")
  else:
   z=100*(close[i]/close[i-20]-1)
   regime.append("up_20d" if z>2 else "down_20d" if z< -2 else "sideways_20d")
 def model(train_end,excluded=None):
  # train_end is exclusive, and no future outcome labels enter fitting
  dist={k:sorted(f[k] for f in feats[LOOKBACK:train_end] if f and k in f) for k in KEYS if k!=excluded}
  if any(len(v)<150 for v in dist.values()):return None
  def score(i):
   f=feats[i];z=[percentile(f[k],dist[k]) for k in dist if f and k in f]
   return sum(z)/len(z) if len(z)>= (4 if excluded else 5) else None
  train=sorted(x for i in range(LOOKBACK,train_end) if (x:=score(i)) is not None)
  if len(train)<150:return None
  return score,train[min(len(train)-1,int(len(train)*ALERT_QUANTILE))]
 results={}
 for h,cut in HORIZONS.items():
  # 3 contiguous OOS folds, expanding history; purge h observations before test start.
  folds=[];allwf=[]
  for start in (400,500,600):
   end=min(start+100,n-h);train_end=start-h
   m=model(train_end);assert m is not None
   score,threshold=m;cases=[]
   for i in range(start,end):
    if not numeric(close[i]) or close[i]<=0 or any(not numeric(x) or x<=0 for x in close[i+1:i+h+1]):continue
    s=score(i)
    if s is not None:cases.append((i,s>=threshold,100*(min(close[i+1:i+h+1])/close[i]-1)<=cut))
   assert cases
   folds.append({"train_range":[dates[LOOKBACK],dates[train_end-1]],"test_range":[dates[start],dates[end-1]],"purged_train_rows":h,"score_threshold":threshold,"metrics":summary([x[1] for x in cases],[x[2] for x in cases])})
   allwf.extend(cases)
  assert len({i for i,_,_ in allwf})==len(allwf)
  # Freeze original 70/30 split for paired comparisons; do not tune on holdout.
  split=int(n*.7);full=model(split);assert full
  variants={k:model(split,k) for k in KEYS};assert all(variants.values())
  cases=[]
  for i in range(split,n-h):
   if not numeric(close[i]) or close[i]<=0 or any(not numeric(x) or x<=0 for x in close[i+1:i+h+1]):continue
   s=full[0](i)
   if s is None:continue
   v={k:(m[0](i)>=m[1] if m[0](i) is not None else False) for k,m in variants.items()}
   cases.append({"date":dates[i],"regime":regime[i],"event":100*(min(close[i+1:i+h+1])/close[i]-1)<=cut,"alert":s>=full[1],"alternatives":v})
  rng=random.Random(SEED+h);blocks=[block_indices(len(cases),h,rng) for _ in range(REPS)]
  groups={}
  for g in ("up_20d","down_20d","sideways_20d"):
   sub=[x for x in cases if x["regime"]==g]
   a=[x["alert"] for x in sub];e=[x["event"] for x in sub]
   # Resample full chronological timeline to preserve clustered regime membership.
   vals=[]
   for ix in blocks:
    selected=[cases[j] for j in ix if cases[j]["regime"]==g]
    vals.append(lift([x["alert"] for x in selected],[x["event"] for x in selected]) if selected else None)
   groups[g]={"metrics":summary(a,e),"block_bootstrap_precision_minus_base_rate_ci95":interval(vals),"valid_bootstrap_draws":sum(x is not None for x in vals),"caution":"Subgroup is observational; CI may be unstable with few alerts"}
  paired={}
  for k in KEYS:
   delta=[]
   for ix in blocks:
    z=[cases[j] for j in ix];e=[x["event"] for x in z]
    f=rate([x["alert"] for x in z],e);alt=rate([x["alternatives"][k] for x in z],e)
    delta.append(f-alt if f is not None and alt is not None else None)
   full_precision=rate([x["alert"] for x in cases],[x["event"] for x in cases])
   alt_precision=rate([x["alternatives"][k] for x in cases],[x["event"] for x in cases])
   ci=interval(delta)
   paired[k]={"full_minus_removed_precision":full_precision-alt_precision if alt_precision is not None else None,
      "paired_moving_block_bootstrap_ci95":ci,"valid_bootstrap_draws":sum(x is not None for x in delta),
      "ci_excludes_zero":bool(ci and (ci[0]>0 or ci[1]<0)),
      "note":"Exploratory paired comparison on same dates, no multiplicity-adjusted confirmatory inference"}
  results[str(h)+"d"]={"walk_forward_folds":folds,"walk_forward_aggregate":summary([x[1] for x in allwf],[x[2] for x in allwf]),"regime_uncertainty":groups,"paired_factor_ablations":paired}
 report={"stage":"P2-02_extension","status":"completed_exploratory_not_confirmatory","input_sha256":hashlib.sha256(raw).hexdigest(),
  "walk_forward":"3 nonoverlapping 100-session OOS blocks starting at indices 400/500/600, expanding training, h-session pretest purge; fixed 80th percentile training-only threshold",
  "bootstrap":"Paired circular moving-block bootstrap of chronological holdout; block length equals forward horizon; 1500 replicates; deterministic seed",
  "multiple_comparisons":"Six exploratory ablations per horizon; no familywise correction, so no definitive factor-significance claims",
  "caveats":["Walk-forward windows partly reuse dates from original train/holdout; not an independent external validation dataset","Regime uncertainty estimates may be unreliable for small subgroups","Overlapping forward labels and serial dependence persist","Purging is conservative: model fits features only, but gap also prevents label boundary contamination","Historical source timing and one TXF official record remain uncertified"],
  "holdout":results,"full_model_validated":False,"full_model_backtest_authorized":False,"recommended_live_threshold":None}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({k:{"walk_forward":v["walk_forward_aggregate"],"folds":[x["metrics"] for x in v["walk_forward_folds"]]} for k,v in results.items()}))
if __name__=="__main__":main()
