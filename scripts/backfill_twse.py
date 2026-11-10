"""Bounded, auditable TWSE historical backfill (listed market only).

Run with --month YYYY-MM. Fetches two official monthly reports, validates the
reported date and units, and saves raw provenance in a separate JSON file.
Never fabricates TAIFEX history or changes the live risk score.
"""
import argparse
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "storage" / "twse_backfill.json"
URLS = {
    "margin": "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
    "cash_inst": "https://www.twse.com.tw/rwd/zh/fund/BFI82U",
}


def request_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def money(value):
    return int(str(value).replace(",", "").strip())


def parse_margin(obj, requested_month):
    # MI_MARGN is a daily summary, NOT a monthly historical series.
    # Reject responses not explicitly dated in the requested month.
    raw = str(obj.get("date", ""))
    date = parse_roc_date(raw)
    if not date or date[:7] != requested_month:
        raise ValueError("margin_response_date_not_requested_month")
    tables = obj.get("tables", [])
    matches = []
    for t in tables:
        fields = t.get("fields", [])
        if "今日餘額" not in fields:
            continue
        for row in t.get("data", []):
            if len(row) == len(fields) and "融資金額" in str(row[0]):
                matches.append(money(row[fields.index("今日餘額")]) * 1000)
    if len(matches) != 1 or matches[0] <= 0:
        raise ValueError("margin_schema_or_unit_unverified")
    return [{"metric_id": "margin.margin", "date": date, "value": matches[0],
             "unit": "TWD", "scope": "TWSE上市市場", "provider": "TWSE"}]


def parse_roc_date(raw):
    import re
    m = re.search(r"(\d{2,4})[年/\-](\d{1,2})[月/\-](\d{1,2})", raw)
    if not m:
        return None
    y, mo, day = map(int, m.groups())
    if y < 1911:
        y += 1911
    try:
        return dt.date(y, mo, day).isoformat()
    except ValueError:
        return None


def parse_cash(obj, requested_month):
    # BFI82U date=YYYYMMDD is a one-day report, never infer a month of data.
    date = parse_roc_date(str(obj.get("date", "")))
    if not date or date[:7] != requested_month:
        raise ValueError("cash_response_date_not_requested_month")
    fields = obj.get("fields", [])
    rows = obj.get("data", [])
    if "買賣差額" not in fields or "單位名稱" not in fields:
        raise ValueError("cash_schema_unverified")
    totals = [money(row[fields.index("買賣差額")]) for row in rows
              if len(row) == len(fields) and row[fields.index("單位名稱")] == "合計"]
    if len(totals) != 1:
        raise ValueError("cash_total_not_unique")
    return [{"metric_id": "inst.cash_inst", "date": date, "value": totals[0],
             "unit": "TWD", "scope": "TWSE上市市場", "provider": "TWSE"}]


def run(month, days=5):
    dt.date.fromisoformat(month + "-01")
    if not 1 <= days <= 23:
        raise ValueError("days must be 1..23")
    existing = json.loads(OUT.read_text()) if OUT.exists() else {"records": [], "attempts": []}
    records = {(r["metric_id"], r["date"]): r for r in existing["records"]}
    attempts = existing["attempts"]
    count = 0
    for day in range(1, days + 1):
        date = f"{month}-{day:02d}"
        try:
            dt.date.fromisoformat(date)
        except ValueError:
            break
        for kind, base in URLS.items():
            # Each request is one day; cap requests to 2*days.
            url = base + "?" + urllib.parse.urlencode({
                "date": date.replace("-", ""), "response": "json",
                **({"selectType": "ALL"} if kind == "margin" else {})})
            try:
                obj = request_json(url)
                parsed = parse_margin(obj, month) if kind == "margin" else parse_cash(obj, month)
                # Critical: do not attribute a report to the requested day if it returned another day.
                if parsed[0]["date"] != date:
                    raise ValueError("response_date_mismatch")
                record = dict(parsed[0], source_url=url)
                records[(record["metric_id"], record["date"])] = record
                attempts.append({"requested_date": date, "kind": kind, "status": "accepted"})
                count += 1
            except Exception as exc:
                attempts.append({"requested_date": date, "kind": kind,
                                 "status": "rejected", "reason": type(exc).__name__ + ":" + str(exc)[:90]})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"schema_version": 1, "records": list(records.values()),
                               "attempts": attempts[-1000:]}, ensure_ascii=False, indent=2))
    print("TWSE backfill:", count, "verified observations; requests:", days * 2)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--days", type=int, default=5)
    a = p.parse_args()
    run(a.month, a.days)
