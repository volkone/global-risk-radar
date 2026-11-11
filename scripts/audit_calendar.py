"""Offline, fail-closed official session-calendar audit for TWSE history.

Input is a reviewed UTF-8 CSV with columns date,is_trading_day (YYYY-MM-DD, 1/0).
This script does not claim the CSV is official: source metadata must be supplied.
"""
import argparse
import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

METRICS = ("margin.margin", "inst.cash_inst")

def evaluate(records, calendar_rows, start="2023-11-01", end="2026-10-31"):
    sessions = set()
    covered = set()
    for row in calendar_rows:
        day = dt.date.fromisoformat(row["date"]).isoformat()
        if day in covered:
            raise ValueError("duplicate calendar date: " + day)
        covered.add(day)
        flag = str(row["is_trading_day"]).strip()
        if flag not in ("0", "1"):
            raise ValueError("invalid trading flag: " + day)
        if flag == "1":
            sessions.add(day)
    required = {(dt.date.fromisoformat(start) + dt.timedelta(days=i)).isoformat()
                for i in range((dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1)}
    if not required <= covered:
        raise ValueError("calendar date coverage incomplete; missing " + str(len(required - covered)) + " days")
    observed = defaultdict(set)
    for record in records:
        metric, day = record["metric_id"], record["date"]
        if metric in METRICS and start <= day <= end:
            if day in observed[metric]:
                raise ValueError("duplicate observation: " + metric + " " + day)
            observed[metric].add(day)
    report = {}
    for metric in METRICS:
        missing = sorted(sessions - observed[metric])
        unexpected = sorted(observed[metric] - sessions)
        report[metric] = {"expected_sessions": len(sessions),
                          "observed_sessions": len(observed[metric] & sessions),
                          "missing_dates": missing, "unexpected_dates": unexpected,
                          "coverage_ratio": len(observed[metric] & sessions) / len(sessions) if sessions else None}
    return {"status": "pass" if all(not v["missing_dates"] and not v["unexpected_dates"] for v in report.values()) else "blocked",
            "calendar_days": len(covered), "metrics": report}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--calendar", required=True, type=Path)
    p.add_argument("--source-url", required=True)
    p.add_argument("--retrieved-at", required=True)
    p.add_argument("--history", type=Path, default=Path("storage/twse_backfill.json"))
    p.add_argument("--out", type=Path, default=Path("docs/calendar_coverage_audit.json"))
    a = p.parse_args()
    if not a.source_url.startswith("https://"):
        raise ValueError("official source URL required")
    dt.datetime.fromisoformat(a.retrieved_at.replace("Z", "+00:00"))
    with a.calendar.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    payload = json.loads(a.history.read_text(encoding="utf-8"))
    report = evaluate(payload["records"], rows)
    report["calendar_source_url"] = a.source_url
    report["calendar_retrieved_at"] = a.retrieved_at
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Calendar gate:", report["status"])
    if report["status"] != "pass":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
