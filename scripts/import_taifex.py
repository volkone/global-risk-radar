"""Strict offline import for TAIFEX TX foreign institutional historical CSV.

Source: https://www.taifex.com.tw/cht/3/futContractsDateView
Official historical form supports a date range and commodity selector. The
HTTP form submission parameters are NOT yet verified; do not invent them.
Import a downloaded CSV only after its exact headers have been inspected.
"""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "storage" / "taifex_backfill.json"
REQUIRED = ("日期", "商品名稱", "身份別", "未平倉多方口數", "未平倉空方口數", "未平倉多空淨額口數")


def number(value):
    return int(str(value).replace(",", "").strip())


def normalize_date(value):
    value = str(value).strip().replace("/", "-")
    return dt.date.fromisoformat(value).isoformat()


def parse_rows(rows):
    result = []
    for row in rows:
        if not all(k in row for k in REQUIRED):
            raise ValueError("Unverified TAIFEX CSV schema; explicit mapping required")
        if row["商品名稱"].strip() not in ("臺股期貨", "台股期貨", "TX"):
            continue
        if row["身份別"].strip() not in ("外資", "外資及陸資"):
            continue
        long_oi, short_oi, net = (number(row[k]) for k in REQUIRED[3:])
        if min(long_oi, short_oi) < 0 or long_oi - short_oi != net:
            raise ValueError("TAIFEX TX OI identity mismatch")
        date = normalize_date(row["日期"])
        result.append({"metric_id": "inst.futures", "date": date, "value": net,
                       "long_oi": long_oi, "short_oi": short_oi, "unit": "contracts",
                       "scope": "TX臺股期貨;外資及陸資;未平倉淨額", "provider": "TAIFEX"})
    dates = [r["date"] for r in result]
    if len(set(dates)) != len(dates):
        raise ValueError("Duplicate TX foreign rows on the same date")
    return sorted(result, key=lambda r: r["date"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True, type=Path)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    a = p.parse_args()
    with a.csv.open(encoding="utf-8-sig", newline="") as stream:
        rows = parse_rows(csv.DictReader(stream))
    if not rows:
        raise ValueError("No validated TX foreign OI rows")
    if any(not a.start <= r["date"] <= a.end for r in rows):
        raise ValueError("Historical rows outside requested date range")
    existing = json.loads(OUT.read_text()) if OUT.exists() else {"records": []}
    merged = {(r["metric_id"], r["date"]): r for r in existing["records"]}
    for row in rows:
        key = row["metric_id"], row["date"]
        if key in merged and merged[key]["value"] != row["value"]:
            raise ValueError("Conflicting historical TAIFEX observation: " + row["date"])
        merged[key] = row
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"schema_version": 1, "records": sorted(merged.values(), key=lambda r: r["date"]),
                               "source": "TAIFEX official downloaded CSV; manually inspected headers",
                               "status": "offline_import_validated"}, ensure_ascii=False, indent=2))
    print("TAIFEX TX imported:", len(rows), "rows")


if __name__ == "__main__":
    main()
