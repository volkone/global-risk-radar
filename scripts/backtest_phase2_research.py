"""Phase-2 research diagnostic on real TX/TWSE/TAIEX/FRED historical inputs.
Not a trading backtest; never a full-model or live-threshold authorization.

Signals observed after Taiwan market close on date t are used only for NEXT
session outcomes. For US data, the joined panel uses strictly prior dates.
Fixed directions, weights, holdout split and event thresholds are declared here
and are NOT selected using holdout results. Overlapping windows remain correlated.
"""
import hashlib
import json
import math
from bisect import bisect_left
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "storage/phase2_joined_panel.json"
OUT = ROOT / "docs/phase2_risk_research_backtest.json"
HORIZONS = {5: -3.0, 20: -5.0}   # hypotheticals, not optimized or operational
LOOKBACK = 20
TRAIN_FRACTION = 0.70
ALERT_QUANTILE = 0.80
MIN_FEATURES = 5
MIN_TEST_EVENTS = 5

def pct(now, before):
    if before is None or now is None or before <= 0:
        return None
    return 100.0 * (now / before - 1.0)

def numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def prepare(rows):
    features = []
    for i, r in enumerate(rows):
        if i < LOOKBACK:
            features.append(None)
            continue
        prev = rows[i - LOOKBACK]
        item = {}
        net, long_, short_ = (r.get(k) for k in
            ("tx_oi_net_contracts", "tx_oi_long_contracts", "tx_oi_short_contracts"))
        if all(numeric(x) for x in (net, long_, short_)) and long_ + short_ > 0:
            item["foreign_tx_short_pressure"] = -net / (long_ + short_)
        margin_change = pct(r.get("margin_balance_twd"), prev.get("margin_balance_twd"))
        if margin_change is not None:
            item["margin_deleveraging_20d"] = -margin_change
        cash = [rows[j].get("cash_institutional_net_twd") for j in range(i-4, i+1)]
        if all(numeric(x) for x in cash):
            item["institutional_net_selling_5d"] = -sum(cash)
        def prior_value(row, key):
            return row["us_previous_dated_observations"][key]["value"]
        fxchg = pct(prior_value(r, "fx"), prior_value(prev, "fx"))
        if fxchg is not None:
            item["twd_depreciation_20d"] = fxchg
        hychg = (prior_value(r, "hy") - prior_value(prev, "hy")
                 if numeric(prior_value(r, "hy")) and
                    numeric(prior_value(prev, "hy")) else None)
        if hychg is not None:
            item["hy_oas_widening_20d"] = hychg
        vix = prior_value(r, "vix")
        if numeric(vix):
            item["prior_us_vix_level"] = vix
        features.append(item if len(item) >= MIN_FEATURES else None)
    return features

def percentile(value, sorted_values):
    n = len(sorted_values)
    if not n:
        return None
    left = bisect_left(sorted_values, value)
    # Inclusive percentile; no holdout outcomes inform the ranking.
    return 100.0 * left / n

def evaluate():
    panel_bytes = SOURCE.read_bytes()
    panel = json.loads(panel_bytes)
    rows = panel["rows"]
    assert len(rows) == 718 and panel["formal_backtest_authorized"] is False
    dates = [x["date"] for x in rows]
    assert dates == sorted(set(dates)), "panel dates unsorted or duplicates"
    assert all(x["tw_end_of_day_signals_eligible_from_session"] == (
        dates[i+1] if i+1<len(dates) else None) for i, x in enumerate(rows))
    feats = prepare(rows)
    split = int(len(rows) * TRAIN_FRACTION)
    keys = ("foreign_tx_short_pressure", "margin_deleveraging_20d",
            "institutional_net_selling_5d", "twd_depreciation_20d",
            "hy_oas_widening_20d", "prior_us_vix_level")
    training_distribution = {
        k: sorted(x[k] for x in feats[LOOKBACK:split] if x and k in x)
        for k in keys
    }
    if any(len(v) < 150 for v in training_distribution.values()):
        return {"status": "insufficient_training_coverage", "full_model_backtest_authorized": False,
                "errors": ["At least one training feature has fewer than 150 observations"]}
    scores = []
    for feat in feats:
        if feat is None:
            scores.append(None)
            continue
        ranks = [percentile(feat[k], training_distribution[k]) for k in keys if k in feat]
        scores.append(sum(ranks) / len(ranks) if len(ranks) >= MIN_FEATURES else None)
    train_scores = sorted(x for x in scores[LOOKBACK:split] if x is not None)
    if len(train_scores) < 150:
        return {"status": "insufficient_train_scores", "full_model_backtest_authorized": False}
    score_threshold = train_scores[min(len(train_scores)-1, int(len(train_scores)*ALERT_QUANTILE))]
    samples = {}
    for horizon, event_cutoff in HORIZONS.items():
        held = []
        # no holdout target can touch a future date beyond data coverage
        for i in range(split, len(rows)-horizon):
            if scores[i] is None or not numeric(rows[i].get("taiex_price_index_close")):
                continue
            p0 = rows[i]["taiex_price_index_close"]
            future = [r.get("taiex_price_index_close") for r in rows[i+1:i+horizon+1]]
            if any(not numeric(x) or x <= 0 for x in future):
                continue
            worst = 100.0 * (min(future) / p0 - 1.0)
            fwd = 100.0 * (future[-1] / p0 - 1.0)
            held.append({"date": dates[i], "score": scores[i],
                         "alert": scores[i] >= score_threshold,
                         "risk_event": worst <= event_cutoff,
                         "forward_return_pct": fwd, "worst_forward_drawdown_pct": worst})
        alerted = [x for x in held if x["alert"]]
        evented = [x for x in held if x["risk_event"]]
        alert_events = sum(x["risk_event"] for x in alerted)
        enough = len(evented) >= MIN_TEST_EVENTS and len(alerted) >= 10
        samples[str(horizon)+"d"] = {
            "status": "diagnostic_descriptive_only" if enough else "insufficient_events_or_alerts",
            "warning_event_threshold_pct": event_cutoff,
            "holdout_cases": len(held), "holdout_event_cases": len(evented),
            "holdout_alert_cases": len(alerted), "alerted_event_cases": alert_events,
            "holdout_event_base_rate": round(len(evented)/len(held), 4) if held else None,
            "alert_precision": round(alert_events/len(alerted), 4) if alerted and enough else None,
            "mean_alert_forward_return_pct": round(sum(x["forward_return_pct"] for x in alerted)/len(alerted),4) if alerted and enough else None,
            "mean_alert_worst_forward_drawdown_pct": round(sum(x["worst_forward_drawdown_pct"] for x in alerted)/len(alerted),4) if alerted and enough else None,
            "note": "Forward windows overlap; confidence intervals and effective independent sample size not established."
        }
    return {
        "status": "research_only_no_trading_validation",
        "method": "fixed_direction_6_factor_rank_signal_70_30_chronological_holdout",
        "signal_observation_timing": "TX/TWSE EOD on date t; earliest action next Taiwan session; US FX/risks strictly prior source date",
        "research_signal_features": list(keys),
        "fixed_alert_quantile": ALERT_QUANTILE,
        "train_samples": len(train_scores), "train_range": [dates[LOOKBACK], dates[split-1]],
        "holdout_range": [dates[split], dates[-1]],
        "alert_score_threshold_from_train_only": round(score_threshold, 4),
        "holdout": samples,
        "data_sha256": hashlib.sha256(panel_bytes).hexdigest(),
        "restrictions": [
            "This is NOT the complete Taiwan/global model or a transaction-cost-adjusted trading strategy.",
            "Signals use fixed illustrative weights and directions; no optimization against holdout labels.",
            "FRED publication timing and vintage revision historical verification remains pending.",
            "Index forward return describes price index changes, not dividend-inclusive investor returns.",
            "The formal TX evidence gate remains blocked; no live parameter changes."
        ],
        "full_model_backtest_authorized": False,
        "full_model_validated": False,
        "recommended_live_threshold": None
    }

def main():
    result = evaluate()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PHASE2_RESEARCH_DIAGNOSTIC", result["status"], result.get("holdout", {}))
    assert result["full_model_backtest_authorized"] is False

if __name__ == "__main__":
    main()
