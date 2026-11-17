"""Rank listed-market foreign cash net selling, retaining each day's entry rank."""
from bisect import bisect_left
import csv
from datetime import date
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "storage/foreign_cash_history.csv"
REPORT = ROOT / "docs/foreign_cash_ranking.json"
LIMIT = 25
QUALIFIED_NAMES = {"外資及陸資(不含外資自營商)", "外資及陸資（不含外資自營商）"}


def rankings(records):
    top, entries = [], []
    for sessions, (day, amount) in enumerate(sorted(records.items()), 1):
        if amount >= 0:
            continue
        key = (amount, day)
        place = bisect_left(top, key)
        if place >= LIMIT:
            continue
        top.insert(place, key)
        del top[LIMIT:]
        entries.append({"date": day, "net_twd": amount, "rank": place + 1, "sessions_to_date": sessions})
    return [
        {"date": day, "net_twd": amount, "rank": i}
        for i, (amount, day) in enumerate(top, 1)
    ], entries


def append_official_cash(records, snapshot, quality):
    if snapshot.get("updated_utc") != quality.get("snapshot_updated_at"):
        return
    cash = snapshot["metrics"].get("inst", {}).get("official_sources", {}).get("cash_inst", {})
    inspected = quality["metrics"].get("inst.cash_inst", {})
    day = cash.get("date")
    if not (
        cash.get("status") == "ok" and cash.get("provider") == "TWSE" and cash.get("unit") == "TWD"
        and cash.get("cache_status") != "stale" and not cash.get("last_error")
        and day and inspected.get("quality") == "pass" and inspected.get("date") == day
    ):
        return
    values = [row.get("net_twd") for row in cash.get("categories", [])
              if row.get("name") in QUALIFIED_NAMES]
    if len(values) == 1 and type(values[0]) is int:
        records[date.fromisoformat(day).isoformat()] = values[0]


def main():
    with HISTORY.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    records = {date.fromisoformat(row["date"]).isoformat(): int(row["net_twd"]) for row in rows}
    if len(records) != len(rows) or not records:
        raise ValueError("Missing or duplicate foreign cash history dates")
    before = records.copy()
    snapshot = json.loads((ROOT / "docs/data.json").read_bytes())
    quality = json.loads((ROOT / "docs/quality.json").read_bytes())
    append_official_cash(records, snapshot, quality)
    if records != before:
        with HISTORY.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["date", "net_twd"])
            writer.writerows(sorted(records.items()))
    top, entries = rankings(records)
    report = {
        "scope": "TWSE listed market foreign investors; excludes foreign dealers' proprietary trading",
        "unit": "TWD",
        "start_date": min(records),
        "end_date": max(records),
        "sessions": len(records),
        "top": top,
        "entries": entries,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Foreign cash ranking: {report['sessions']} sessions, {len(entries)} historical entry events")


if __name__ == "__main__":
    main()
