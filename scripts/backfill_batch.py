"""Up to three bounded TWSE historical months per scheduled run, 2023-11 to 2026-10.

A month is attempted once and tracked even if official endpoints reject dates.
Rejections are NOT interpreted as missing trading days and never become data.
"""
import datetime as dt
import json
from pathlib import Path
from scripts.backfill_twse import run, OUT

STATE = OUT.parent / "backfill_progress.json"
START = (2023, 11)
END = (2026, 10)


def months():
    y, m = START
    while (y, m) <= END:
        yield f"{y:04d}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def main():
    progress = json.loads(STATE.read_text()) if STATE.exists() else {"attempted_months": []}
    done = set(progress["attempted_months"])
    oct_cash = {r["date"] for r in json.loads(OUT.read_text()).get("records", [])
                if r["metric_id"] == "inst.cash_inst" and r["date"].startswith("2026-10")} if OUT.exists() else set()
    if len(oct_cash) < 15:
        if progress.get("october_gate_attempts", 0) >= 2:
            print("October institutional validation failed twice; automatic backfill halted")
            return
        queue = ["2026-10"]
    else:
        queue = [m for m in months() if m not in done][:3]
    if not queue:
        print("TWSE backfill: all 36 months attempted; audit coverage before use")
        return
    for month in queue:
        run(month, 31, kinds=("margin", "cash_inst"))
        payload = json.loads(OUT.read_text())
        month_cash = {r["date"] for r in payload.get("records", [])
                      if r["metric_id"] == "inst.cash_inst" and r["date"].startswith(month)}
        if month == "2026-10" and len(oct_cash) < 15:
            progress["october_gate_attempts"] = progress.get("october_gate_attempts", 0) + 1
            if len(month_cash) < 15:
                print("October institutional gate still below 15; stopping batch")
                break
        done.add(month)
        progress = {"october_gate_attempts": progress.get("october_gate_attempts", 0),
                    "attempted_months": sorted(done),
                    "accepted_records": len(payload["records"]),
                    "rejected_requests": sum(x["status"] == "rejected" for x in payload["attempts"]),
                    "last_attempted_month": month,
                    "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "status": "attempted_not_verified_complete"}
        STATE.write_text(json.dumps(progress, ensure_ascii=False, indent=2))
        print("Backfill progress:", len(done), "/ 36 months attempted; verified records:", len(payload["records"]))


if __name__ == "__main__":
    main()
