"""Build a day-level TWSE calendar from reviewed official annual holiday JSON archives.

Input files: storage/official_calendar/2023.json ... 2026.json, each a JSON
array of TWSE holidaySchedule objects (Name, Date [ROC YYYYMMDD], Description).
Archives MUST be obtained separately for each year from official TWSE pages.
A current-year OpenAPI response cannot substitute for earlier years.
Extraordinary closures are supplied separately as a reviewed CSV with
date,source_url,reason and must cite a primary-source announcement.
"""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path

SOURCE = "https://www.twse.com.tw/zh/trading/holiday.html"
START, END = dt.date(2023, 11, 1), dt.date(2026, 10, 31)
NON_TRADING_KEYWORDS = ("休市", "放假", "無交易", "結算交割", "除夕", "春節")
TRADING_KEYWORDS = ("開始交易", "最後交易")

def parse_year_archive(path, year):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"{year}: empty or invalid annual archive")
    closed = set()
    observed = set()
    for item in data:
        raw = str(item.get("Date", "")).strip()
        if len(raw) != 7 or not raw.isdigit():
            raise ValueError(f"{year}: invalid ROC date {raw}")
        d = dt.date(int(raw[:3]) + 1911, int(raw[3:5]), int(raw[5:7]))
        if d.year != year:
            raise ValueError(f"{year}: wrong-year row {raw}")
        if d in observed:
            raise ValueError(f"{year}: duplicate date {raw}")
        observed.add(d)
        name = str(item.get("Name", ""))
        if any(x in name for x in TRADING_KEYWORDS):
            continue
        if any(x in name for x in NON_TRADING_KEYWORDS) or name:
            closed.add(d)
        else:
            raise ValueError(f"{year}: ambiguous unnamed holiday {raw}")
    return closed

def build(folder, exceptional_csv):
    closed = set()
    for year in range(2023, 2027):
        closed.update(parse_year_archive(folder / f"{year}.json", year))
    with exceptional_csv.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            d = dt.date.fromisoformat(row["date"])
            if not row["source_url"].startswith("https://") or not row["reason"].strip():
                raise ValueError(f"unverified exceptional closure {d}")
            closed.add(d)
    out = []
    d = START
    while d <= END:
        out.append({"date": d.isoformat(), "is_trading_day": int(d.weekday() < 5 and d not in closed)})
        d += dt.timedelta(days=1)
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--archives", type=Path, default=Path("storage/official_calendar"))
    p.add_argument("--exceptional", type=Path, default=Path("storage/official_calendar/exceptional_closures.csv"))
    p.add_argument("--out", type=Path, default=Path("storage/official_calendar/trading_days.csv"))
    args = p.parse_args()
    rows = build(args.archives, args.exceptional)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=("date", "is_trading_day"))
        w.writeheader()
        w.writerows(rows)
    print(f"Calendar: {len(rows)} days, {sum(r['is_trading_day'] for r in rows)} expected sessions")
if __name__ == "__main__":
    main()
