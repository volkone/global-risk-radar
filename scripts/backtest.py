"""3B-02: reproducible, no-lookahead FX/TAIEX diagnostic backtest.

This is an association study, NOT a validation of the full Taiwan risk model.
Forward outcomes: next 5/20 session return and worst drawdown within the window.
Each signal percentile is estimated only from earlier completed observations.
"""
import datetime as dt
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data.json"
OUT = ROOT / "docs" / "backtest.json"
HORIZONS = (5, 20)
FX_LOOKBACK = 20
MIN_TRAIN = 40
THRESHOLDS = (70, 80, 90)
MIN_TEST = 20


def clean(series):
    result = {}
    for row in series:
        try:
            date = row["date"]
            value = row["value"]
            dt.date.fromisoformat(date)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                continue
            result[date] = float(value)
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(result.items())


def run(fx, taiex):
    fx = clean(fx)
    taiex = clean(taiex)
    fx_changes = {fx[i][0]: 100 * (fx[i][1] / fx[i-FX_LOOKBACK][1] - 1)
                  for i in range(FX_LOOKBACK, len(fx))}
    common = [(d, close, fx_changes[d]) for d, close in taiex if d in fx_changes]
    # A conservative date intersection: never match values from different days.
    output = {"method": "expanding_window_walk_forward",
              "signal": "20-session USD/TWD change percentile",
              "target": "TAIEX forward return and maximum intra-window drawdown",
              "train_min": MIN_TRAIN, "test_min": MIN_TEST,
              "common_sessions": len(common), "thresholds": {}}
    # Train with past FX signals only; future TAIEX outcomes never enter thresholds.
    for horizon in HORIZONS:
        for threshold in THRESHOLDS:
            cases = []
            for i in range(MIN_TRAIN, len(common) - horizon):
                prior = [x[2] for x in common[:i]]
                percentile = 100 * (sum(v < common[i][2] for v in prior)
                                    + 0.5 * sum(v == common[i][2] for v in prior)) / len(prior)
                prices = [common[j][1] for j in range(i+1, i+horizon+1)]
                forward = 100 * (prices[-1] / common[i][1] - 1)
                worst = 100 * (min(prices) / common[i][1] - 1)
                cases.append((percentile >= threshold, forward, worst))
            alerts = [c for c in cases if c[0]]
            baseline = [c for c in cases]
            enough = len(cases) >= MIN_TEST and len(alerts) >= 10
            output["thresholds"][f"{horizon}d_p{threshold}"] = {
                "status": "diagnostic_only" if enough else "insufficient_samples",
                "test_cases": len(cases), "alert_cases": len(alerts),
                "mean_forward_return_pct": round(sum(x[1] for x in alerts)/len(alerts), 3) if enough else None,
                "mean_worst_drawdown_pct": round(sum(x[2] for x in alerts)/len(alerts), 3) if enough else None,
                "baseline_mean_return_pct": round(sum(x[1] for x in baseline)/len(baseline), 3) if enough else None,
                "warning": "Overlapping forward windows; not independent, no causal or out-of-sample validation."
            }
    output["status"] = ("diagnostic_only" if any(v["status"] == "diagnostic_only"
                            for v in output["thresholds"].values()) else "insufficient_samples")
    output["full_model_validated"] = False
    output["recommended_live_threshold"] = None
    return output


def main():
    metrics = json.loads(DATA.read_text(encoding="utf-8")).get("metrics", {})
    report = run(metrics.get("fx", {}).get("history", []),
                 metrics.get("taiex", {}).get("history", []))
    report["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Backtest:", report["status"], "aligned sessions:", report["common_sessions"])


if __name__ == "__main__":
    main()
