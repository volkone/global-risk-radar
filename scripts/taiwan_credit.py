"""Published market-wide credit account statistics from the TWSE dashboard."""

import json
from datetime import date, datetime, timezone
from math import isfinite

from backfill_twse import parse_roc_date
from taiwan_crash_watch import ROOT, sessions_through, url
from taiwan_market_breadth import read_history, save_history

HISTORY = ROOT / "docs/taiwan_credit_history.json"
BASE_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/BFIJ3U_TREND"
DASHBOARD = "https://www.twse.com.tw/dashboard/zh/credit/margin.html"
SCOPE = "上市櫃整戶信用交易"
COUNTS = {
    "belowAccNum": "accounts_below_130",
    "callAmt": "margin_call_twd",
    "exeAccNum": "disposal_accounts",
    "exeAmt": "disposal_twd",
}


def source_url(day, count=60):
    return url(BASE_URL, response="json", days=count, date=day.replace("-", ""))


def parse_report(obj, through, calendar, retrieved_at):
    if obj.get("stat") != "OK" or not isinstance(obj.get("data"), list):
        raise ValueError("official credit report unavailable")
    records = {}
    for row in obj["data"]:
        day = parse_roc_date(row["date"])
        if not day or day > through or not calendar.get(date.fromisoformat(day)):
            raise ValueError("invalid credit observation date")
        ratio = row["keepRate"]
        counts = {field: row[name] for name, field in COUNTS.items()}
        if (day in records or type(ratio) not in (int, float) or not isfinite(ratio) or ratio <= 0
                or any(type(v) is not int or v < 0 for v in counts.values())):
            raise ValueError("invalid official credit values")
        records[day] = {"maintenance_pct": ratio, **counts, "observed_at": retrieved_at.isoformat()}
    return records


def merge_reports(original, incoming):
    combined = dict(original)
    for day, new in incoming.items():
        old = combined.get(day, {})
        facts = ("maintenance_pct", *COUNTS.values())
        if not old or any(new[key] != old.get(key) for key in facts):
            combined[day] = new
    return combined


def summarize(records, through, calendar, status):
    latest = max((d for d in records if d <= through), default=None)
    result = {"date": latest, "expected_date": through, "status": status, "source_url": DASHBOARD}
    if not latest:
        return result
    record = records[latest]
    following = min((day.isoformat() for day, trading in calendar.items()
                     if trading and day > date.fromisoformat(latest)), default=None)
    result.update(record, disposal_date=following, sessions=len(records))
    short = sessions_through(date.fromisoformat(latest), 6, calendar)
    for window in (1, 5):
        if len(short) > window and short[-1 - window] in records:
            ref = short[-1 - window]
            result[f"change_{window}d_pp"] = round(record["maintenance_pct"] - records[ref]["maintenance_pct"], 2)
    return result


def refresh(metric, fetch, through, calendar):
    if not through:
        return None
    archive = read_history(HISTORY, {"records": {}})
    records = archive["records"]
    try:
        if through not in records:
            body = fetch(source_url(through))
            observed = datetime.now(timezone.utc)
            incoming = parse_report(json.loads(body), through, calendar, observed)
            merged = merge_reports(records, incoming)
            if merged != records:
                save_history(HISTORY, {"schema_version": 1, "scope": SCOPE,
                                       "source_url": DASHBOARD, "records": merged})
                records = merged
        status = "ok" if through in records else "pending"
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        status = "source_error"
        print("Official market credit unavailable:", type(exc).__name__, flush=True)
    result = summarize(records, through, calendar, status)
    if result["date"]:
        metric.update(status="ok", reason="證交所全市場整戶信用交易擔保維持率",
                      provider="TWSE", scope=SCOPE, unit="%", date=result["date"],
                      value=result["maintenance_pct"], checked_at=result["observed_at"],
                      source_url=source_url(result["date"], count=1))
        recent = sessions_through(date.fromisoformat(through), 2, calendar)
        if result["date"] not in recent or status == "source_error":
            metric["cache_status"] = "stale"
    return result
