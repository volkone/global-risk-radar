"""Phase 3B-01: separate global and Taiwan risk-score prototypes.

Scores are deliberately withheld until enough independently validated inputs
are present. No trade instructions, and no conflation of data quality with risk.
"""
import datetime as dt
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data.json"
QUALITY = ROOT / "docs" / "quality.json"
OUT = ROOT / "docs" / "scores.json"

# Weights are provisional policy parameters, not empirically calibrated.
GROUPS = {
    "global": {
        "hy": 25, "ig": 10, "vix": 20, "indices": 20,
        "nfci": 10, "us10y": 5, "breadth": 10,
    },
    "taiwan": {
        "taiex": 35, "margin": 20, "inst.cash_inst": 15,
        "inst.futures": 15, "fx": 15,
    },
}
MIN_COVERAGE = 0.85


def clamp(value):
    return max(0.0, min(100.0, float(value)))


def scale(value, low, high):
    return clamp((value - low) / (high - low) * 100)


def drawdown(metric):
    value = metric.get("drawdown_pct")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def rate_change_signal(metric):
    """Research-only upward-rate pressure: 20 sessions vs 60 prior changes."""
    cutoff = metric.get('date')
    if not cutoff:
        return None
    rows = [p for p in metric.get('history', []) if p['date'] <= cutoff]
    dates = [p['date'] for p in rows]
    if dates != sorted(set(dates)):
        raise ValueError('invalid_rate_dates')
    values = [float(p['value']) for p in rows]
    if any(not math.isfinite(v) for v in values):
        raise ValueError('invalid_rate_values')
    if len(values) < 81 or dates[-1] != cutoff or values[-1] != float(metric['value']):
        return None
    changes = [values[i]-values[i-20] for i in range(20,len(values))]
    current, prior = changes[-1], changes[-61:-1]
    return 100 * (sum(v < current for v in prior) + .5 * sum(v == current for v in prior)) / 60


def signal(key, metrics):
    metric = metrics.get(key.split(".")[0], {})
    if key == "us10y":
        return rate_change_signal(metric)
    if key == "hy":
        return scale(metric["value"], 2, 8)
    if key == "ig":
        return scale(metric["value"], 0.5, 3)
    if key == "vix":
        return scale(metric["value"], 12, 45)
    if key in ("indices", "taiex"):
        d = drawdown(metric)
        return None if d is None else scale(d, 0, 30)
    if key == "nfci":
        return scale(metric["value"], -0.75, 1.5)
    # These require calibrated directionality, baseline and/or time series.
    return None


def score_group(name, metrics, quality):
    weights = GROUPS[name]
    total_weight = sum(weights.values())
    components = []
    used = 0
    weighted = 0
    for key, weight in weights.items():
        q = quality.get("metrics", {}).get(key, {})
        reason = None
        value = None
        if q.get("quality") != "pass":
            reason = "quality_gate_not_passed"
        else:
            try:
                value = signal(key, metrics)
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                reason = "missing_signal_inputs"
            if value is None and reason is None:
                reason = "signal_not_yet_calibrated"
        if value is not None:
            used += weight
            weighted += value * weight
        components.append({"metric": key, "weight": weight, "signal": round(value, 2) if value is not None else None,
                           "eligible": value is not None, "reason": reason})
    coverage = used / total_weight
    # Do not renormalize a sparse basket into a misleading authoritative score.
    eligible = coverage >= MIN_COVERAGE
    return {"status": "provisional" if eligible else "insufficient_coverage",
            "score": round(weighted / used, 1) if eligible and used else None,
            "coverage": round(coverage, 4), "min_coverage": MIN_COVERAGE,
            "components": components}


def evaluate(data, quality):
    metrics = data.get("metrics", {})
    return {"schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "model_status": "uncalibrated_prototype",
            "disclaimer": "Risk scores are provisional and not validated by historical backtests.",
            "global": score_group("global", metrics, quality),
            "taiwan": score_group("taiwan", metrics, quality)}


def main():
    report = evaluate(json.loads(DATA.read_text(encoding="utf-8")),
                      json.loads(QUALITY.read_text(encoding="utf-8")))
    from dashboard_scores import integrate
    report = integrate(report, json.loads(DATA.read_text(encoding="utf-8")))
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Scores:", {k: (report[k]["status"], report[k]["coverage"]) for k in ("global", "taiwan")})


if __name__ == "__main__":
    main()
