"""One bounded TWSE historical month per scheduled run, 2023-11 to 2026-10.

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
    next_month = next((m for m in months() if m not in done), None)
    if next_month is None:
        print("TWSE backfill: all 36 months attempted; audit coverage before use")
        return
    run(next_month, 31)
    done.add(next_month)
    payload = json.loads(OUT.read_text())
    progress = {"attempted_months": sorted(done),
                "accepted_records": len(payload["records"]),
                "rejected_requests": sum(x["status"] == "rejected" for x in payload["attempts"]),
                "last_attempted_month": next_month,
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "status": "attempted_not_verified_complete"}
    STATE.write_text(json.dumps(progress, ensure_ascii=False, indent=2))
    print("Backfill progress:", len(done), "/ 36 months attempted; verified records:", len(payload["records"]))


if __name__ == "__main__":
    main()
