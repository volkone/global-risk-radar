"""3B-02 Taiwan signal calibration. No future data, no fabricated backtest.

Quantile ranks use only prior observations, with a minimum of 60 distinct
historical sessions and a 20-session change for margin/FX. All results remain
experimental until a separate forward-return validation is completed.
"""
import datetime as dt
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data.json"
QUALITY = ROOT / "docs" / "quality.json"
HISTORY = ROOT / "docs" / "history" / "observations.json"
OUT = ROOT / "docs" / "calibration.json"
MIN_SAMPLES = 60
LOOKBACK = 20
SIGNAL_KEYS = ("margin", "inst.cash_inst", "inst.futures", "fx")


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def series_from_snapshot(metric):
    return [(r.get("date"), r.get("value")) for r in metric.get("history", [])
            if isinstance(r, dict)]


def extract(data, history, key):
    metrics = data.get("metrics", {})
    if key == "margin":
        m = metrics.get("margin", {}).get("official_sources", {}).get("margin", {})
        current = (m.get("date"), m.get("value"))
        identifier = "margin.margin"
    elif key == "inst.cash_inst":
        m = metrics.get("inst", {}).get("official_sources", {}).get("cash_inst", {})
        totals = [x.get("net_twd") for x in m.get("categories", [])
                  if x.get("name") == "合計" and isinstance(x, dict)]
        current = (m.get("date"), totals[0] if len(totals) == 1 else None)
        identifier = key
    elif key == "inst.futures":
        m = metrics.get("inst", {}).get("official_sources", {}).get("futures", {})
        current = (m.get("date"), m.get("foreign_tx_net_oi"))
        identifier = key
    elif key == "fx":
        m = metrics.get("fx", {})
        current = (m.get("date"), m.get("value"))
        identifier = "fx"
    else:
        raise ValueError("unknown signal")
    pairs = [(r.get("observation_date"), r.get("value"))
             for r in history.get("observations", []) if r.get("metric_id") == identifier]
    if key == "fx":
        pairs += series_from_snapshot(metrics.get("fx", {}))
    pairs.append(current)
    # Exact-date deduplication; current snapshot wins over older exports.
    points = {}
    for date, value in pairs:
        try:
            if dt.date.fromisoformat(date).isoformat() != date or not finite(value):
                continue
        except (ValueError, TypeError):
            continue
        points[date] = float(value)
    return sorted(points.items()), current


def transform(key, points):
    if key in ("margin", "fx"):
        # Relative change: margin deleveraging / FX depreciation.
        return [(points[i][0], (points[i][1] / points[i-LOOKBACK][1] - 1) * 100)
                for i in range(LOOKBACK, len(points))
                if points[i-LOOKBACK][1] > 0]
    # Negative net cash buying or negative foreign futures OI indicate stress.
    # Daily magnitude is deliberately NOT compared across time until normalized
    # by market turnover or open interest and audited.
    return []


def rank(current, past):
    return round(100 * (sum(x < current for x in past) +
                        0.5 * sum(x == current for x in past)) / len(past), 2)


def evaluate(data, quality, history):
    results = {}
    for key in SIGNAL_KEYS:
        points, current = extract(data, history, key)
        errors = []
        if quality.get("metrics", {}).get(key, {}).get("quality") != "pass":
            errors.append("quality_gate_not_passed")
        if len(points) < MIN_SAMPLES + (LOOKBACK if key in ("margin", "fx") else 0):
            errors.append("insufficient_historical_sessions")
        transformed = transform(key, points)
        if key.startswith("inst."):
            errors.append("normalization_denominator_unavailable")
        if len(transformed) < MIN_SAMPLES + 1:
            errors.append("insufficient_transformed_history")
        # Use ONLY prior observations to rank the most recent signal.
        score = None
        if not errors:
            date, latest = transformed[-1]
            if date != current[0]:
                errors.append("latest_date_mismatch")
            else:
                past = [value for _, value in transformed[:-1]]
                score = rank(latest, past)
        results[key] = {
            "status": "experimental" if score is not None else "insufficient_history",
            "score": score, "current_date": current[0], "current_value": current[1],
            "raw_observations": len(points), "transformed_observations": len(transformed),
            "min_prior_transformed_observations": MIN_SAMPLES,
            "lookback_sessions": LOOKBACK if key in ("margin", "fx") else None,
            "method": "prior_only_empirical_percentile" if key in ("margin", "fx") else "awaiting_turnover_or_open_interest_normalization",
            "errors": errors,
        }
    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model_status": "research_only_not_backtested",
        "notes": [
            "Percentile calibration is descriptive, not a validated predictive risk threshold.",
            "20-session FX appreciation/depreciation is directional; negative FX change is not a safe-market guarantee.",
            "Margin decreases may indicate deleveraging or forced liquidation; directional risk must be tested against future returns.",
            "Historical backtesting requires timestamped observations, benchmark forward returns and out-of-sample evaluation.",
        ],
        "signals": results,
        "backtest": {"status": "not_run", "reason": "No complete synchronized historical panel and forward return labels."}
    }


def main():
    from dashboard_scores import PANEL, clean_rows, reconstruct, calibration_report
    from phase5_forward_capture import verify_frozen
    from phase5_forward_ledger import frozen_distributions
    import hashlib
    frozen = verify_frozen()
    raw = PANEL.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    timing = json.loads((ROOT/'docs/phase4_publication_timing_audit.json').read_text())
    if timing.get('output_sha256') != digest:
        raise ValueError('publication_panel_audit_hash_mismatch')
    panel = json.loads(raw)
    rows = reconstruct(panel['rows'], frozen_distributions(), frozen['post_close_feature_action_lag_taiwan_sessions'])
    report = calibration_report(panel, digest, frozen, rows)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Calibration:", {k: (v["status"], v["raw_observations"], v.get("signal"))
                           for k, v in report["signals"].items()})


if __name__ == "__main__":
    main()
