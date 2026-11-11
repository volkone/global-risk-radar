"""Repair only explicitly identified TWSE date/metric gaps.

Never accept a response for a different date. Existing records are preserved;
failed requests are logged, not replaced by inferred values.
"""
import argparse
import json
import urllib.parse
from pathlib import Path
from scripts.backfill_twse import OUT, URLS, request_json, parse_margin, parse_cash

TARGETS = (("2023-12-29", "cash_inst"), ("2024-01-24", "margin"), ("2024-01-29", "margin"), ("2024-01-29", "cash_inst"))

def repair(fetch=request_json, path=OUT):
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = {(r["metric_id"], r["date"]): r for r in payload["records"]}
    attempts = payload.get("attempts", [])
    repaired = []
    for date, kind in TARGETS:
        metric = "margin.margin" if kind == "margin" else "inst.cash_inst"
        if (metric, date) in records:
            continue
        params = ({"date": date.replace("-", ""), "response": "json", "selectType": "ALL"}
                  if kind == "margin" else
                  {"dayDate": date.replace("-", ""), "type": "day", "response": "json"})
        url = URLS[kind] + "?" + urllib.parse.urlencode(params)
        try:
            response = fetch(url)
            row = (parse_margin(response, date[:7]) if kind == "margin"
                   else parse_cash(response, date[:7]))[0]
            if row["date"] != date:
                raise ValueError("response_date_mismatch")
            records[(metric, date)] = dict(row, source_url=url)
            attempts.append({"requested_date": date, "kind": kind, "status": "accepted"})
            repaired.append(date)
        except Exception as exc:
            attempts.append({"requested_date": date, "kind": kind, "status": "rejected",
                             "reason": type(exc).__name__ + ":" + str(exc)[:90]})
    payload["records"] = sorted(records.values(), key=lambda r: (r["date"], r["metric_id"]))
    payload["attempts"] = attempts[-1000:]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return repaired

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Perform only missing targeted official TWSE requests")
    args = parser.parse_args()
    if not args.execute:
        parser.error("explicit --execute required; default is no network and no mutation")
    print("Repaired dates:", repair())
