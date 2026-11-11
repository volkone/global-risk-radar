"""Audit TWSE backfill coverage without treating rejected requests as holidays."""
import calendar
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "storage" / "twse_backfill.json"
OUT = ROOT / "docs" / "backfill_audit.json"


def audit(payload):
    records = payload.get("records", [])
    attempts = payload.get("attempts", [])
    grouped = defaultdict(set)
    duplicates = 0
    for r in records:
        key = (r.get("metric_id"), r.get("date"))
        if r.get("date") in grouped[r.get("metric_id")]:
            duplicates += 1
        grouped[r.get("metric_id")].add(r.get("date"))
    months = sorted({r.get("date", "")[:7] for r in records if r.get("date")})
    by_month = {}
    for month in months:
        y, m = map(int, month.split("-"))
        weekdays = sum(__import__("datetime").date(y, m, d).weekday() < 5
                       for d in range(1, calendar.monthrange(y, m)[1] + 1))
        margin_days = {d for d in grouped["margin.margin"] if d.startswith(month)}
        cash_days = {d for d in grouped["inst.cash_inst"] if d.startswith(month)}
        by_month[month] = {
            "margin_unique_dates": len([d for d in grouped["margin.margin"] if d.startswith(month)]),
            "cash_unique_dates": len([d for d in grouped["inst.cash_inst"] if d.startswith(month)]),
            "weekday_reference_count_not_official_calendar": weekdays,
            "cash_missing_vs_margin_dates": sorted(margin_days - cash_days),
            "margin_missing_vs_cash_dates": sorted(cash_days - margin_days),
            "paired_observation_dates": len(margin_days & cash_days),
            "official_trading_day_count": None,
            "trading_day_completeness": None,
            "reason": "Official trading calendar and verified listed-market sessions not joined",
        }
    failures = Counter((x.get("kind", "unknown"), x.get("reason", "unknown"))
                       for x in attempts if x.get("status") == "rejected")
    return {
        "status": "partial_verified",
        "accepted_unique_records": len({(r.get("metric_id"), r.get("date")) for r in records}),
        "duplicate_records": duplicates,
        "attempt_count": len(attempts),
        "accepted_attempt_count": sum(x.get("status") == "accepted" for x in attempts),
        "rejected_attempt_count": sum(x.get("status") == "rejected" for x in attempts),
        "rejections": [{"kind": k, "reason": reason, "count": n}
                       for (k, reason), n in sorted(failures.items())],
        "months": by_month,
        "cash_source_status": ("historical_dates_observed_pending_official_calendar"
                               if grouped["inst.cash_inst"] else "historical_dates_not_verified"),
        "taifex_source_status": "not_backfilled",
        "out_of_sample_backtest_status": "blocked_incomplete_panel",
        "live_thresholds_status": "not_authorized",
    }


def main():
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    OUT.write_text(json.dumps(audit(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    print("Audit:", len(payload.get("records", [])), "records")


if __name__ == "__main__":
    main()
