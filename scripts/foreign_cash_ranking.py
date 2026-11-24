"""Rank listed-market foreign cash flows, retaining each day's entry rank."""
from bisect import bisect_left
import csv
from datetime import date
import json
from math import isfinite
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "storage/foreign_cash_history.csv"
REPORT = ROOT / "docs/foreign_cash_ranking.json"
LIMIT = 25
QUALIFIED_NAMES = {"外資及陸資(不含外資自營商)", "外資及陸資（不含外資自營商）"}


def rankings(records, *, buying=False):
    top, entries = [], []
    order = -1 if buying else 1
    for sessions, (day, amount) in enumerate(sorted(records.items()), 1):
        sort_amount = amount * order
        if sort_amount >= 0:
            continue
        key = (sort_amount, day)
        place = bisect_left(top, key)
        if place >= LIMIT:
            continue
        top.insert(place, key)
        del top[LIMIT:]
        entries.append({"date": day, "net_twd": amount, "rank": place + 1, "sessions_to_date": sessions})
    return [
        {"date": day, "net_twd": records[day], "rank": i}
        for i, (_, day) in enumerate(top, 1)
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


MAX_REBOUND_DAYS = 20


def rebound_windows(entries, cash_dates, files_root):
    """Align each event to its next sessions without bridging missing prices."""
    archive = json.loads((files_root / "storage/historical_taiex_close.json").read_bytes())
    history = json.loads((files_root / "docs/history/observations.json").read_bytes())
    closes = {}
    for rows, metric, day_key, unit in (
        (archive["records"], "taiex.close", "date", "index_points"),
        (history["observations"], "taiex.tw_price", "observation_date", "points"),
    ):
        for row in rows:
            value = row.get("value")
            if (row.get("metric_id") == metric and row.get("provider") == "TWSE"
                    and row.get("unit") == unit and type(value) in (int, float)
                    and isfinite(value) and value > 0):
                closes[row[day_key]] = round(value * 100)

    calendar = files_root / "storage/official_calendar/trading_days.csv"
    with calendar.open(newline="", encoding="utf-8") as stream:
        days = {row["date"]: row["is_trading_day"] == "1" for row in csv.DictReader(stream)}
    # Beyond the calendar archive, use dated official market observations.
    sessions = sorted({day for day in cash_dates | closes.keys() if days.get(day, True)}
                      | {day for day, trading in days.items() if trading})
    positions = {day: index for index, day in enumerate(sessions)}
    as_of = max(max(cash_dates), max(closes, default=""))
    for event in entries:
        day = event["date"]
        event["rebound_window"] = None
        if day not in closes or day not in positions:
            continue
        event["rebound_window"] = []
        previous = day
        index = positions[day] + 1
        for session in sessions[index:index + MAX_REBOUND_DAYS]:
            if session > as_of:
                break
            current, prior = closes.get(session), closes.get(previous)
            event["rebound_window"].append({
                "date": session,
                "change": current - prior if current and prior else None,
                "previous": prior,
            })
            previous = session
    return {"max_days": MAX_REBOUND_DAYS, "price_start": min(closes, default=None),
            "price_end": max(closes, default=None), "calendar_end": max(days, default=None)}


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
    buy_top, buy_entries = rankings(records, buying=True)
    report = {
        "scope": "TWSE listed market foreign investors; excludes foreign dealers' proprietary trading",
        "unit": "TWD",
        "start_date": min(records),
        "end_date": max(records),
        "sessions": len(records),
        "top": top,
        "entries": entries,
        "rebound": rebound_windows(entries, records.keys(), ROOT),
        "buy": {"top": buy_top, "entries": buy_entries},
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Foreign cash rankings: {report['sessions']} sessions, "
          f"{len(entries)} sell and {len(buy_entries)} buy entry events")


if __name__ == "__main__":
    main()
