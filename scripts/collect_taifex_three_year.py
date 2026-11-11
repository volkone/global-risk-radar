"""Bounded, resumable official TAIFEX TXF foreign OI collection.

The TWSE calendar is only a *candidate* date set, never the verified TAIFEX calendar.
Only verified TXF foreign OI rows are persisted. Every attempt is diagnosed.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "2023-11-11"
END = "2026-10-31"
URL = "https://www.taifex.com.tw/cht/3/futContractsDate"
OUT = ROOT / "storage/taifex_backfill.json"
REPORT = ROOT / "docs/taifex_collection_report.json"

class Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.tr, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.tr = []
        elif tag in ("td", "th") and self.tr is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.tr is not None:
            self.tr.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.tr is not None:
            self.rows.append(self.tr)
            self.tr = None

def extract(raw, date, url):
    html = raw.decode("utf-8", errors="replace")
    if date.replace("-", "/") not in html:
        raise ValueError("requested date absent from response")
    table = Table()
    table.feed(html)
    matches = []
    for index, row in enumerate(table.rows):
        if len(row) >= 15 and row[1].strip() in ("臺股期貨", "台股期貨") and row[2].strip() == "自營商":
            for following in table.rows[index + 1:index + 4]:
                if len(following) == 13 and following[0].strip() in ("外資", "外資及陸資"):
                    matches.append(following)
    if len(matches) != 1:
        raise ValueError(f"TXF foreign OI row count {len(matches)}")
    row = matches[0]
    long_oi, short_oi, net = (int(row[i].replace(",", "")) for i in (7, 9, 11))
    if min(long_oi, short_oi) < 0 or long_oi - short_oi != net:
        raise ValueError("OI arithmetic mismatch")
    return {
        "metric_id": "inst.futures", "date": date, "value": net,
        "long_oi": long_oi, "short_oi": short_oi, "unit": "contracts",
        "scope": "TX臺股期貨;外資及陸資;未平倉淨額", "provider": "TAIFEX",
        "source_url": url, "source_sha256": hashlib.sha256(raw).hexdigest()
    }

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20, help="maximum attempted dates, 1..30")
    parser.add_argument("--offset", type=int, default=-1, help="-1 automatically resumes next batch; >=0 selects candidate-date index")
    parser.add_argument("--timeout", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.limit <= 30 or args.offset < -1 or not 1 <= args.timeout <= 30:
        parser.error("limit must be 1..30, offset >=-1, timeout 1..30")

    with (ROOT / "storage/official_calendar/trading_days.csv").open(encoding="utf-8-sig", newline="") as f:
        dates = sorted(r["date"] for r in csv.DictReader(f)
                       if r["is_trading_day"] == "1" and START <= r["date"] <= END)
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"records": []}
    accepted = {r["date"]: r for r in previous.get("records", [])
                if r.get("metric_id") == "inst.futures" and START <= r.get("date", "") <= END}
    previous_report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    if args.offset == -1:
        args.offset = int(previous_report.get("last_batch_offset", 0)) + int(previous_report.get("last_batch_size", 0))
    failures = {r["date"]: r for r in previous_report.get("errors", []) if "date" in r}
    attempts = 0
    newly_accepted = 0
    batch = dates[args.offset:args.offset + args.limit]

    def persist():
        atomic_json(OUT, {
            "schema_version": 1,
            "records": sorted(accepted.values(), key=lambda x: x["date"]),
            "source": "TAIFEX official dated futContractsDate query; TXF foreign OI",
            "status": "collected_pending_independent_futures_calendar_audit"
        })
        atomic_json(REPORT, {
            "window": [START, END], "twse_reference_sessions": len(dates),
            "official_taifex_rows": len(accepted), "last_batch_offset": args.offset,
            "last_batch_size": len(batch), "last_batch_attempted": attempts,
            "last_batch_new_rows": newly_accepted,
            "missing_reference_dates": sorted(set(dates) - set(accepted)),
            "errors": sorted(failures.values(), key=lambda x: x["date"]),
            "independent_taifex_calendar_verified": False
        })

    persist()  # create files before network calls so cancellation cannot cause missing pathspec
    for date in batch:
        if date in accepted:
            continue
        attempts += 1
        params = {"commodityId": "TXF", "doQuery": "1",
                  "queryDate": date.replace("-", "/"), "queryType": "1"}
        url = URL + "?" + urllib.parse.urlencode(params)
        last_error = None
        for retry in range(2):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0", "Referer": URL})
                with urllib.request.urlopen(req, timeout=args.timeout) as resp:
                    raw = resp.read(2_000_000)
                    if resp.status != 200:
                        raise ValueError(f"HTTP {resp.status}")
                accepted[date] = extract(raw, date, url)
                failures.pop(date, None)
                newly_accepted += 1
                last_error = None
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:180]}"
                if retry == 0:
                    time.sleep(0.8)
        if last_error:
            failures[date] = {"date": date, "reason": last_error, "source_url": url}
        persist()  # checkpoint on every date
        print(f"{date}: {'OK' if last_error is None else last_error}; "
              f"new={newly_accepted} attempted={attempts}", flush=True)
        time.sleep(0.2)
    persist()
    print(f"batch complete: {newly_accepted} new / {attempts} attempted; "
          f"total {len(accepted)} / {len(dates)}", flush=True)

if __name__ == "__main__":
    main()
