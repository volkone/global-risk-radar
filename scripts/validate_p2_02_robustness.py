"""P2-02 descriptive robustness: frozen holdout, past-only regimes, temporal slices, leave-one-factor-out."""
import hashlib,json,math
from pathlib import Path
from backtest_phase2_research import SOURCE,prepare,percentile,numeric,LOOKBACK,TRAIN_FRACTION,ALERT_QUANTILE,HORIZONS
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"docs/p2_02_robustness.json"
KEYS=("foreign_tx_short_pressure","margin_deleveraging_20d","institutional_net_selling_5d","twd_depreciation_20d","hy_oas_widening_20d","prior_us_vix_level")
def summarize(samples):
 n=len(samples);a=[x for x in samples if x["alert"]];ev=sum(x["event"] for x in samples);hit=sum(x["event"] for x in a)
 return {"n":n,"alerts":len(a),"events":ev,"hits":hit,"precision":hit/len(a) if a else None,"recall":hit/ev if ev else None,"base_rate":ev/n if n else None,"precision_minus_base_rate":hit/len(a)-ev/n if a and n else None,"adequate_for_descriptive_comparison":n>=30 and len(a)>=10 and ev>=5}
def main():
 raw=SOURCE.read_bytes();p=json.loads(raw);rows=p["rows"];dates=[x["date"] for x in rows];n=len(rows);split=int(n*TRAIN_FRACTION)
 assert n==718 and p["formal_backtest_authorized"] is False
 feats=prepare(rows)
 distributions={k:sorted(f[k] for f in feats[LOOKBACK:split] if f and k in f) for k in KEYS}
 assert all(len(v)>=150 for v in distributions.values())
 ranks=[{k:percentile(f[k],distributions[k]) for k in KEYS if f and k in f} if f else {} for f in feats]
 def score(i,excluded=None):
  z=[v for k,v in ranks[i].items() if k!=excluded]
  return sum(z)/len(z) if len(z)>=(4 if excluded else 5) else None
 def threshold(excluded=None):
  vals=sorted(x for i in range(LOOKBACK,split) if (x:=score(i,excluded)) is not None)
  assert len(vals)>=150
  return vals[min(len(vals)-1,int(len(vals)*ALERT_QUANTILE))]
 base_threshold=threshold()
 close=[r.get("taiex_price_index_close") for r in rows]
 # Past-only 20-session market return and 20-session realized volatility; no future regime information.
 returns=[100*(close[i]/close[i-1]-1) if i and numeric(close[i]) and numeric(close[i-1]) and close[i-1]>0 else None for i in range(n)]
 regimes=[]
 for i in range(n):
  if i<20 or not numeric(close[i]) or not numeric(close[i-20]) or close[i-20]<=0:regimes.append("unknown");continue
  trend=100*(close[i]/close[i-20]-1)
  regimes.append("up_20d" if trend>2 else "down_20d" if trend< -2 else "sideways_20d")
 out={}
 for h,cutoff in HORIZONS.items():
  samples=[];alternatives={k:[] for k in KEYS};alt_thresholds={k:threshold(k) for k in KEYS}
  for i in range(split,n-h):
   if not numeric(close[i]) or close[i]<=0 or any(not numeric(v) or v<=0 for v in close[i+1:i+h+1]):continue
   s=score(i)
   if s is None:continue
   event=100*(min(close[i+1:i+h+1])/close[i]-1)<=cutoff
   samples.append({"index":i,"date":dates[i],"alert":s>=base_threshold,"event":event,"regime":regimes[i]})
   for k in KEYS:
    z=score(i,k);alternatives[k].append({"alert":z is not None and z>=alt_thresholds[k],"event":event})
  assert len(samples)==len(next(iter(alternatives.values())))
  overall=summarize(samples)
  mid=len(samples)//2
  periods={"first_half":summarize(samples[:mid]),"second_half":summarize(samples[mid:])}
  by_regime={r:summarize([x for x in samples if x["regime"]==r]) for r in ("up_20d","down_20d","sideways_20d","unknown")}
  ablations={}
  for k,alt in alternatives.items():
   m=summarize(alt)
   ablations[k]={"without_factor":m,"delta_precision_vs_full":m["precision"]-overall["precision"] if m["precision"] is not None and overall["precision"] is not None else None,
     "delta_recall_vs_full":m["recall"]-overall["recall"] if m["recall"] is not None and overall["recall"] is not None else None,
     "alert_threshold_reestimated_using_training_only":alt_thresholds[k],
     "interpretation":"Diagnostic leave-one-out with reestimated training-only threshold; not causal attribution"}
  out[str(h)+"d"]={"overall":overall,"temporal_halves":periods,"past_only_trend_regimes":by_regime,"leave_one_factor_out":ablations,
    "holdout_range":[samples[0]["date"],samples[-1]["date"]]}
 report={"stage":"P2-02","status":"descriptive_robustness_completed","input_sha256":hashlib.sha256(raw).hexdigest(),
  "regime_definition":"Past 20-session TAIEX return: >2% up, <-2% down, otherwise sideways; chosen for descriptive slicing, not optimization",
  "time_slices":"Two contiguous halves of fixed original 30% holdout; no reshuffle",
  "ablation":"Drop one feature, recompute percentile-average score and alert threshold on training only; same holdout dates",
  "holdout":out,"warnings":["Exploratory subgroup comparisons; no statistical significance claims","Small regime groups and overlapping outcomes can distort results","Correlated factors mean ablation is not causal feature importance","Only one holdout period; no walk-forward validation yet","Do not choose best feature combination using these holdout results","Historical FRED vintage and TXF official one-day source remain uncertified"],
  "full_model_validated":False,"full_model_backtest_authorized":False,"recommended_live_threshold":None}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 for h,v in out.items():print(h,"overall",v["overall"],"halves",v["temporal_halves"],"regimes",v["past_only_trend_regimes"])
if __name__=="__main__":main()
