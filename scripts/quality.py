"""Phase 3A-03: independently auditable risk data quality gates.

Reports source age, consistency, plausibility and readiness. Does not change
risk scores or turn absent data into a safe reading.
"""
import datetime as dt
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "data.json"
HISTORY = ROOT / "docs" / "history" / "observations.json"
OUTPUT = ROOT / "docs" / "quality.json"
VERSION = 1
# Calendar-day freshness limits include weekends/holidays; conservative for weekly NFCI.
AGE_LIMITS = {"nfci": 14, "hy": 7, "ig": 7, "us10y": 7, "vix": 7,
              "indices": 5, "taiex": 5, "margin": 5, "fx": 5}
RANGES = {"hy": (0, 30), "ig": (0, 20), "us10y": (-5, 30),
          "vix": (0, 150), "indices": (100, 100000),
          "taiex": (100, 100000), "margin": (1e9, 1e14),
          "fx": (10, 100), "nfci": (-10, 10)}
TOLERANCES = {"taiex.tw_price": 0.005}  # relative fraction; 0.5%


def date_value(value):
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def evaluate(snapshot, history, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    issues = []
    results = {}
    for key, metric in snapshot.get("metrics", {}).items():
        if not isinstance(metric, dict):
            continue
        status = metric.get("status", "unavailable")
        record = metric
        # Official source is preferred for validation, without changing display source.
        official = [(name, item) for name, item in metric.get("official_sources", {}).items()
                    if isinstance(item, dict) and item.get("status") == "ok"]
        if official and key in ("margin", "taiex"):
            name, record = official[0]
            source = key + "." + name
        else:
            source = key
        date = date_value(record.get("date"))
        value = record.get("value")
        unit = record.get("unit")
        errors = []
        warnings = []
        if status != "ok" or record.get("status") not in (None, "ok"):
            errors.append("source_not_verified")
        if metric.get("cache_status") == "stale" or record.get("cache_status") == "stale":
            errors.append("stale_cache")
        if date is None:
            errors.append("missing_or_invalid_date")
        else:
            age = (today - date).days
            if age < 0:
                errors.append("future_observation_date")
            elif age > AGE_LIMITS.get(key, 7):
                errors.append("observation_older_than_limit")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append("missing_or_invalid_numeric_value")
        elif key in RANGES and not RANGES[key][0] <= value <= RANGES[key][1]:
            errors.append("outside_plausibility_range")
        if not isinstance(unit, str) or not unit:
            errors.append("missing_unit")
        if key == "margin" and (unit != "TWD" or record.get("scope") != "TWSE上市市場"):
            errors.append("margin_unit_or_scope_unverified")
        if key == "taiex" and source == "taiex.tw_price":
            other = metric
            if (other.get("status") == "ok" and date == date_value(other.get("date"))
                    and isinstance(other.get("value"), (int, float)) and isinstance(value, (int, float))
                    and value != 0):
                difference = abs(value - other["value"]) / abs(value)
                if difference > TOLERANCES[source]:
                    errors.append("official_yahoo_taiex_disagreement")
            else:
                warnings.append("taiex_cross_source_not_comparable")
        if key == "margin" and date is not None and isinstance(value, (int, float)):
            matches = [r for r in history.get("observations", [])
                       if r.get("metric_id") == source and r.get("observation_date") == date.isoformat()
                       and r.get("provider") == record.get("provider")]
            if not matches:
                warnings.append("not_yet_in_history")
            elif len(matches) != 1 or matches[0].get("value") != value:
                errors.append("history_snapshot_disagreement")
        quality = "blocked" if errors else ("caution" if warnings else "pass")
        results[key] = {"quality": quality, "source": source, "date": date.isoformat() if date else None,
                        "age_days": (today - date).days if date else None,
                        "errors": errors, "warnings": warnings}
        for issue in errors:
            issues.append({"metric": key, "severity": "error", "code": issue})
        for issue in warnings:
            issues.append({"metric": key, "severity": "warning", "code": issue})
    # Composite institutional metrics are not scalar scores. Validate official
    # cash and futures independently instead of treating the whole group as data.
    inst = snapshot.get("metrics", {}).get("inst", {})
    for source_id, record in inst.get("official_sources", {}).items():
        if source_id not in ("cash_inst", "futures") or not isinstance(record, dict):
            continue
        name = "inst." + source_id
        errors = []
        date = date_value(record.get("date"))
        if record.get("status") != "ok":
            errors.append("source_not_verified")
        if date is None:
            errors.append("missing_or_invalid_date")
        elif (today - date).days < 0:
            errors.append("future_observation_date")
        elif (today - date).days > 5:
            errors.append("observation_older_than_limit")
        if source_id == "cash_inst":
            categories = record.get("categories", [])
            total = [x.get("net_twd") for x in categories if x.get("name") == "合計"]
            if (record.get("unit") != "TWD" or len(total) != 1
                    or not isinstance(total[0], (int, float)) or isinstance(total[0], bool)):
                errors.append("invalid_cash_inst_total")
        else:
            net = record.get("foreign_tx_net_oi")
            if (record.get("unit") != "口" or isinstance(net, bool)
                    or not isinstance(net, (int, float)) or not math.isfinite(net)):
                errors.append("invalid_foreign_futures_net_oi")
        results[name] = {"quality": "blocked" if errors else "pass", "source": name,
                         "date": date.isoformat() if date else None,
                         "age_days": (today - date).days if date else None,
                         "errors": errors, "warnings": []}
        for issue in errors:
            issues.append({"metric": name, "severity": "error", "code": issue})
    counts = {label: sum(x["quality"] == label for x in results.values())
              for label in ("pass", "caution", "blocked")}
    return {"schema_version": VERSION, "evaluated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "snapshot_updated_at": snapshot.get("updated_utc"),
            "history_generated_at": history.get("generated_at"),
            "summary": counts, "metrics": results, "issues": issues,
            "policy": "Only pass metrics are eligible for automatic risk scoring; caution requires review; blocked excluded."}


def main():
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    report = evaluate(snapshot, history)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Quality:", report["summary"], "issues:", len(report["issues"]))


if __name__ == "__main__":
    main()
