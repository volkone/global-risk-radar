"""End-of-day market breadth from dated TWSE and TPEx common-share closes."""

import gzip
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone

from backfill_twse import parse_roc_date
from taiwan_crash_watch import ROOT, sessions_through, url

PRICE_CACHE = ROOT / "storage/taiwan_breadth_closes.json.gz"
HISTORY = ROOT / "docs/taiwan_market_breadth.json"
MARKETS = ("tse", "otc")
WINDOWS = (20, 60)
KEEP_SESSIONS = 65
REPAIR_PER_MARKET = 2
EXCHANGE_PAGES = {
    "tse": "https://www.twse.com.tw/zh/trading/historical/mi-index.html",
    "otc": "https://www.tpex.org.tw/zh-tw/mainboard/trading/info/mi-pricing.html",
}


def close_url(market, day):
    if market == "tse":
        return url("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
                   response="json", date=day.replace("-", ""), type="ALLBUT0999")
    return url("https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes",
               date=day.replace("-", "/"), id="", response="json")


def common_code(code):
    # Four-digit ordinary-share codes in the cash equity reports. The 91xx
    # range is reserved for Taiwan depositary receipts.
    return bool(re.fullmatch(r"[1-9][0-9]{3}", code)) and not code.startswith("91")


def parse_daily_closes(raw, market, day):
    if raw["stat"].casefold() != "ok" or parse_roc_date(raw["date"]) != day:
        raise ValueError("daily market close date mismatch")
    code_col, price_col = ("證券代號", "收盤價") if market == "tse" else ("代號", "收盤")
    quotes = {}
    for table in raw["tables"]:
        fields = table.get("fields", [])
        if market == "otc" and table.get("title") not in ("上櫃股票行情", "管理股票"):
            continue
        if code_col not in fields or price_col not in fields:
            continue
        code_index, price_index = fields.index(code_col), fields.index(price_col)
        expected_rows = table.get("total")
        if isinstance(expected_rows, int) and expected_rows != len(table["data"]):
            raise ValueError("partial market price table")
        for row in table["data"]:
            code = str(row[code_index]).strip()
            if not common_code(code):
                continue
            raw_price = str(row[price_index]).strip().replace(",", "")
            if raw_price in ("", "-", "--", "---"):
                continue
            if not re.fullmatch(r"\d+(?:\.\d{1,2})?", raw_price):
                raise ValueError("invalid closing price")
            whole, _, cents = raw_price.partition(".")
            close = 100 * int(whole) + int(cents.ljust(2, "0"))
            if not close:
                continue
            if code in quotes:
                raise ValueError("duplicate cash equity close")
            quotes[code] = close
    if len(quotes) < 550:
        raise ValueError("incomplete market equity coverage")
    return quotes


def capture(raw, market, day, retrieved_at):
    return {
        "prices": parse_daily_closes(json.loads(raw), market, day),
        "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "retrieved_at": retrieved_at.isoformat(),
    }


def breadth_at(closes, sessions):
    """Calculate exact rolling market-session windows with observed prices only."""
    if not sessions or sessions[-1] not in closes:
        return None
    last = closes[sessions[-1]]["prices"]
    result = {"stocks_with_close": len(last)}
    for window in WINDOWS:
        days = sessions[-window:]
        if len(days) < window or any(day not in closes for day in days):
            continue
        prices = [closes[day]["prices"] for day in days]
        eligible = set(last).intersection(*prices[:-1])
        if eligible:
            above = sum(last[code] * window > sum(row[code] for row in prices)
                        for code in eligible)
            result[f"ma{window}"] = {
                "above": above, "eligible": len(eligible),
                "pct": round(100 * above / len(eligible), 4),
            }
    return result


def archive_breadth(closes, sessions):
    report = {}
    for i, day in enumerate(sessions):
        window = sessions[max(0, i - WINDOWS[-1] + 1):i + 1]
        markets = {market: breadth_at(closes[market], window) for market in MARKETS}
        if any(record and "ma20" in record for record in markets.values()):
            report[day] = markets
    return report


def read_history(path, empty, *, compressed=False):
    try:
        raw = path.read_bytes()
        return json.loads(gzip.decompress(raw) if compressed else raw)
    except FileNotFoundError:
        return empty


def save_history(path, payload, *, compressed=False):
    data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n").encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(gzip.compress(data, mtime=0) if compressed else data)
    os.replace(tmp, path)


def capture_missing(fetch, market, day):
    try:
        body = fetch(close_url(market, day))
        return capture(body, market, day, datetime.now(timezone.utc))
    except (AttributeError, IndexError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print("Market breadth close unavailable:", market, day, type(exc).__name__, flush=True)
        return None


def refresh(fetch, through, calendar):
    """Repair bounded holes in the rolling cache and keep prior dated history."""
    if not through:
        return None
    sessions = sessions_through(date.fromisoformat(through), KEEP_SESSIONS, calendar)
    closes = read_history(PRICE_CACHE, {market: {} for market in MARKETS}, compressed=True)
    previous = read_history(HISTORY, {"records": {}})
    changed = False
    for market in MARKETS:
        prices = closes[market]
        missing = [day for day in reversed(sessions) if day not in prices]
        for day in missing[:REPAIR_PER_MARKET]:
            new = capture_missing(fetch, market, day)
            if new:
                prices[day] = new
                changed = True
        for day in set(prices) - set(sessions):
            del prices[day]
            changed = True
    if changed:
        save_history(PRICE_CACHE, closes, compressed=True)

    records = previous["records"]
    updated = dict(records)
    # Retain valid earlier calculations even if a close has already rolled out.
    for day, markets in archive_breadth(closes, sessions).items():
        older = updated.setdefault(day, {}).copy()
        for market, record in markets.items():
            if record and "ma20" in record:
                older[market] = {**(older.get(market) or {}), **record}
        updated[day] = older
    if updated != records or not HISTORY.exists():
        save_history(HISTORY, {
            "schema_version": 1, "markets": EXCHANGE_PAGES,
            "price_basis": "unadjusted_close", "records": updated,
        })

    latest = {}
    for market in MARKETS:
        day = max((d for d, row in updated.items()
                   if d <= through and (row.get(market) or {}).get("ma20")), default=None)
        if day:
            record = updated[day][market]
            prior_sessions = sessions_through(date.fromisoformat(day), 6, calendar)
            prior = (updated.get(prior_sessions[0], {}).get(market) or {}
                     if len(prior_sessions) == 6 else {})
            change = {f"ma{window}_change_5d_pp": round(
                record[f"ma{window}"]["pct"] - prior[f"ma{window}"]["pct"], 2)
                for window in WINDOWS if f"ma{window}" in record and f"ma{window}" in prior}
            latest[market] = {
                **record, **change, "date": day, "source_url": close_url(market, day),
                "status": "ok" if day == through else "stale",
            }
    return {"expected_date": through, "markets": latest}
