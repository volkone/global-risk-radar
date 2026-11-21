"""Taiwan equity selloff monitor. Quote, close and research clocks stay separate."""
import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from math import isfinite
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from backfill_twse import parse_margin, parse_roc_date
from build_official_calendar import parse_year_archive
from foreign_cash_ranking import QUALIFIED_NAMES

ROOT = Path(__file__).resolve().parents[1]
TAIPEI, NEW_YORK = ZoneInfo("Asia/Taipei"), ZoneInfo("America/New_York")
ONE_DAY = timedelta(days=1)
OPEN, CLOSE = time(9), time(13, 30)
PREMARKET_START, CLOSE_REPORT = time(7, 30), time(14, 15)
CUTOFF = time(8, 30)  # Historical decision clock, in Taipei.
QUOTE_MAX_AGE = timedelta(minutes=30)
SAMPLE_MIN_PCT = 85
BATCH_SIZE = 150
RULE = {"prior_day_pct": -3, "drawdown_20_pct": -8, "sox_pct": -2, "tsm_pct": -2}
RULE_VERSION = "taiwan-selloff-v1"
FMTQIK = "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK"
TW_OHLC = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
TW_BREADTH = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
OTC_BREADTH = "https://www.tpex.org.tw/www/zh-tw/afterTrading/highlight"
MARGIN = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
MIS = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
MEMBERS = {
    "tse": ("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "公司代號", "出表日期"),
    "otc": ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", "SecuritiesCompanyCode", "Date"),
}
# Published regular full-day US exchange holidays. Conservative 16:00 ET is used
# for the completion clock, including early-close sessions.
US_HOLIDAYS = {
    2026: "01-01 01-19 02-16 04-03 05-25 06-19 07-03 09-07 11-26 12-25",
    2027: "01-01 01-18 02-15 03-26 05-31 06-18 07-05 09-06 11-25 12-24",
    2028: "01-17 02-21 04-14 05-29 06-19 07-04 09-04 11-23 12-25",
}


def url(base, **params):
    return f"{base}?{urlencode(params)}"


def number(raw):
    try:
        n = float(str(raw).replace(",", "").strip())
        return n if isfinite(n) else None
    except (TypeError, ValueError):
        return None


def positive(raw):
    n = number(raw)
    return n if n is not None and n > 0 else None


def pct(current, previous):
    return round(100 * (current / previous - 1), 10)


def available(record):
    return (
        record.get("status") == "ok"
        and record.get("cache_status") != "stale"
        and not record.get("last_error")
    )


@lru_cache
def calendar():
    """Extend the existing audited day list with published TWSE holiday tables."""
    folder = ROOT / "storage" / "official_calendar"
    with (folder / "trading_days.csv").open(newline="", encoding="utf-8") as stream:
        days = {date.fromisoformat(r["date"]): r["is_trading_day"] == "1"
                for r in csv.DictReader(stream)}
    for year in (2026, 2027):
        closed = parse_year_archive(folder / f"crash_watch_{year}.json", year)
        day = date(year, 1, 1)
        while day.year == year:
            days.setdefault(day, day.weekday() < 5 and day not in closed)
            day += ONE_DAY
    return days


@lru_cache
def archive_closes():
    data = json.loads((ROOT / "storage/historical_taiex_close.json").read_bytes())
    return {r["date"]: r["value"] for r in data["records"]
            if r["provider"] == "TWSE" and r["unit"] == "index_points"
            and positive(r["value"]) is not None}


def sessions_through(day, count, days):
    sessions = []
    while day in days and len(sessions) < count:
        if days[day]:
            sessions.append(day.isoformat())
        day -= ONE_DAY
    return list(reversed(sessions))


def table_rows(table):
    fields, data = table["fields"], table["data"]
    if not isinstance(fields, list) or not isinstance(data, list):
        raise ValueError("invalid exchange table")
    return [dict(zip(fields, row, strict=True)) for row in data]


def fmtqik_month(raw, month):
    if raw.get("stat") != "OK":
        raise ValueError("TWSE monthly close unavailable")
    result = {}
    for row in table_rows(raw):
        day = parse_roc_date(row["日期"])
        close = positive(row["發行量加權股價指數"])
        shares = positive(row["成交股數"])
        turnover = positive(row["成交金額"])
        if not day or day[:7] != month or day in result or None in (close, shares, turnover):
            raise ValueError("invalid TWSE monthly observation")
        result[day] = {"date": day, "value": close, "volume_shares": int(shares),
                       "turnover_twd": int(turnover), "change_points": number(row.get("漲跌點數"))}
    if not result:
        raise ValueError("empty TWSE month")
    return result


def publish_official_close(metric, prior, fetch, now, days):
    """Replace the display close with TWSE. Keep dated cache on collection errors."""
    local = now.astimezone(TAIPEI)
    through = local.date() if local.time() >= CLOSE_REPORT else local.date() - ONE_DAY
    expected = sessions_through(through, 1, days)
    expected = expected[-1] if expected else None
    last = dict(prior.get("official_sources", {}).get("tw_price", {}))
    closes = dict(archive_closes())
    closes.update({day: value for day, value in prior.get("official_history", [])
                   if positive(value) is not None})
    if last.get("provider") == "TWSE" and last.get("date") and positive(last.get("value")):
        closes[last["date"]] = last["value"]

    needed = sessions_through(through, 21, days)
    recent_missing = [day for day in needed if day not in closes]
    # Fetch only months needed around the latest completed session.
    months = {day[:7] for day in recent_missing}
    if expected and (last.get("date") != expected or not available(last)):
        months.add(expected[:7])
    # Recover a longer gap (e.g. collector downtime) from the official source
    # without spending the entire request budget in one run.
    if expected:
        high_days = [day for day, opened in days.items() if opened
                     and through - timedelta(days=365) <= day <= through]
        missing_months = sorted({day.isoformat()[:7] for day in high_days
                                 if day.isoformat() not in closes} - months)
        months.update(missing_months[-1:])
    for month in sorted(months)[-3:]:
        source = url(FMTQIK, response="json", date=month.replace("-", "") + "01")
        try:
            rows = fmtqik_month(json.loads(fetch(source)), month)
            closes.update({day: row["value"] for day, row in rows.items()
                           if day <= through.isoformat()})
            eligible = [day for day in rows if day <= through.isoformat()]
            if eligible and max(eligible) >= (last.get("date") or ""):
                last = dict(rows[max(eligible)], status="ok", provider="TWSE", unit="points",
                            source_url=source, checked_at=now.isoformat())
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
            print("TWSE close refresh:", month, type(exc).__name__, flush=True)

    if not last or not last.get("date") or last["date"] > through.isoformat():
        metric["reason"] = "證交所收盤資料未取得"
        return closes
    if last["date"] != expected:
        last["cache_status"] = "stale"
        last["last_error"] = "expected_official_close_missing"
    else:
        last.pop("cache_status", None)
        last.pop("last_error", None)
    archive_start = (through - timedelta(days=390)).isoformat()
    history = sorted((day, value) for day, value in closes.items()
                     if archive_start <= day <= last["date"])
    metric.update(
        status="ok", provider="TWSE", source="TWSE", source_url=last["source_url"],
        checked_at=last.get("checked_at"), reason="證交所發行量加權股價指數收盤",
        date=last["date"], value=last["value"], unit="points",
        official_close=last["value"], official_close_date=last["date"],
        official_volume_shares=last["volume_shares"], official_turnover_twd=last["turnover_twd"],
        official_history=history, history=[dict(date=d, value=v) for d, v in history[-90:]],
        official_sources={"tw_price": last},
    )
    if last.get("cache_status"):
        metric["cache_status"] = last["cache_status"]
    end = date.fromisoformat(last["date"])
    year = [day.isoformat() for day, opened in days.items()
            if opened and end - timedelta(days=365) <= day <= end]
    if year and all(day in closes for day in year):
        high = max(closes[day] for day in year)
        metric.update(drawdown_pct=round(-pct(last["value"], high), 2),
                      reference="證交所近一年最高收盤價")
    return closes


def yahoo_chart(symbol, **query):
    return url(f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}", **query)


def us_prices(raw, symbol):
    result, = raw["chart"]["result"]
    meta = result["meta"]
    if meta["symbol"] != symbol or meta["exchangeTimezoneName"] != "America/New_York":
        raise ValueError("unexpected US instrument or exchange time zone")
    dates, prices = result["timestamp"], result["indicators"]["quote"][0]["close"]
    if len(dates) != len(prices):
        raise ValueError("US timestamps and prices do not align")
    rows = {}
    for stamp, raw_price in zip(dates, prices):
        session = datetime.fromtimestamp(stamp, NEW_YORK).date().isoformat()
        if session in rows:
            raise ValueError("duplicate US session")
        rows[session] = positive(raw_price)
    return rows


def us_available_at(day):
    return datetime.combine(date.fromisoformat(day), time(16, 15), NEW_YORK)


def expected_us_session(now, before=None):
    cursor = (now.astimezone(NEW_YORK).date() if before is None
              else date.fromisoformat(before) - ONE_DAY)
    for _ in range(10):
        if cursor.year not in US_HOLIDAYS:
            return None
        day = cursor.isoformat()
        if (cursor.weekday() < 5 and day[5:] not in US_HOLIDAYS[cursor.year].split()
                and us_available_at(day) <= now):
            return day
        cursor -= ONE_DAY
    return None


def us_change(rows, session, preceding):
    return pct(rows[session], rows[preceding]) if rows.get(session) and rows.get(preceding) else None


def taiwan_features(closes, dates):
    if len(dates) != 20 or any(day not in closes for day in dates):
        return None
    latest = closes[dates[-1]]
    return {"date": dates[-1], "prior_day_pct": pct(latest, closes[dates[-2]]),
            "drawdown_20_pct": pct(latest, max(closes[day] for day in dates))}


def warning(taiwan, sox_pct, tsm_pct):
    return (
        (taiwan["prior_day_pct"] <= RULE["prior_day_pct"]
         or taiwan["drawdown_20_pct"] <= RULE["drawdown_20_pct"])
        and sox_pct <= RULE["sox_pct"] and tsm_pct <= RULE["tsm_pct"]
    )


def read(fetch, source, parser):
    try:
        return parser(json.loads(fetch(source)))
    except (AttributeError, IndexError, ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        print("Crash watch source unavailable:", source.split("?")[0], type(exc).__name__, flush=True)
        return None


def premarket(now, days, closes, fetch, utcnow):
    local = now.astimezone(TAIPEI)
    day = local.date().isoformat()
    tw = taiwan_features(closes, sessions_through(local.date() - ONE_DAY, 20, days))
    us_day = expected_us_session(now)
    previous_us_day = expected_us_session(now, before=us_day) if us_day else None
    result = {"date": day, "captured_at": now.isoformat(), "status": "unavailable",
              "taiwan": tw, "us_date": us_day, "rule_version": RULE_VERSION}
    if tw is None or not previous_us_day:
        result["missing"] = ["TWSE 近 20 個交易日收盤或美股交易日"]
        return result
    missing = []
    for symbol, name in (("^SOX", "sox"), ("TSM", "tsm")):
        label = "%5ESOX" if symbol == "^SOX" else symbol
        source = yahoo_chart(label, range="1mo", interval="1d")
        rows = read(fetch, source, lambda raw: us_prices(raw, symbol))
        change = us_change(rows or {}, us_day, previous_us_day)
        result[name] = {"value": change, "source_url": source}
        if change is None:
            missing.append(symbol)
    fetched_at = utcnow()
    result["captured_at"] = fetched_at.isoformat()
    if fetched_at.astimezone(TAIPEI) >= datetime.combine(local.date(), OPEN, TAIPEI):
        missing.append("盤前擷取未於 09:00 前完成")
    if missing:
        result["missing"] = missing
    else:
        result["status"] = "alert" if warning(tw, result["sox"]["value"], result["tsm"]["value"]) else "clear"
    return result


def counts(up, down, flat, limit_down, members=None):
    if any(type(v) is not int or v < 0 for v in (up, down, flat, limit_down)):
        raise ValueError("invalid breadth count")
    denominator = up + down + flat
    if not denominator or limit_down > down or (members is not None and denominator > members):
        raise ValueError("breadth totals disagree")
    return {"up": up, "down": down, "flat": flat, "limit_down": limit_down,
            "compared": denominator, "down_pct": round(100 * down / denominator, 2),
            "limit_down_pct": round(100 * limit_down / denominator, 2)}


def official_counts(raw, market, day):
    if parse_roc_date(raw["date"]) != day or raw["stat"].casefold() != "ok":
        raise ValueError("exchange breadth date mismatch")
    name = "漲跌證券數合計" if market == "tse" else "上櫃股票當日彙總資訊"
    table, = [table for table in raw["tables"] if table.get("title") == name]
    rows = table_rows(table)
    integer = lambda x: int(str(x).replace(",", ""))
    if market == "tse":
        by_type = {r["類型"]: r["股票"].replace(",", "") for r in rows}
        risen = re.fullmatch(r"(\d+)\((\d+)\)", by_type["上漲(漲停)"])
        fallen = re.fullmatch(r"(\d+)\((\d+)\)", by_type["下跌(跌停)"])
        if not risen or not fallen:
            raise ValueError("invalid TWSE stock count format")
        up, up_limit = map(int, risen.groups())
        down, down_limit = map(int, fallen.groups())
        if up_limit > up:
            raise ValueError("TWSE rise count mismatch")
        return counts(up, down, integer(by_type["持平"]), down_limit)
    row, = rows
    close, change = positive(row["收市指數"]), number(row["指數漲跌"])
    if close is None or change is None or close <= change:
        raise ValueError("invalid TPEx closing index")
    return dict(counts(*[integer(row[key]) for key in ("上漲家數", "下跌家數", "平盤家數", "跌停家數")],
                       members=integer(row["上櫃家數"])), index_pct=pct(close, close - change))


def quote_rows(raw):
    if raw.get("rtcode") != "0000" or not isinstance(raw.get("msgArray"), list):
        raise ValueError("invalid MIS response")
    return raw["msgArray"]


def quote_url(channels):
    return url(MIS, ex_ch="|".join(channels), json="1", delay="0")


def quote_time(day, clock):
    return datetime.combine(date.fromisoformat(day), time.fromisoformat(clock), TAIPEI)


def indices(raw, now, prior_close):
    local = now.astimezone(TAIPEI)
    day = local.date().isoformat()
    records = {(r.get("ex"), r.get("c")): r for r in quote_rows(raw)}
    tse, otc = records[("tse", "t00")], records[("otc", "o00")]
    stamps = [quote_time(day, r["t"]) for r in (tse, otc)]
    if any(parse_roc_date(r.get("d", "")) != day for r in (tse, otc)) or any(
            not OPEN <= stamp.time() <= CLOSE or not timedelta(0) <= now - stamp <= QUOTE_MAX_AGE
            for stamp in stamps) or abs(stamps[0] - stamps[1]) > timedelta(minutes=2):
        raise ValueError("MIS indices out of phase or stale")
    if prior_close is None or positive(tse["y"]) != prior_close:
        raise ValueError("TWSE previous close cannot be confirmed")
    tw, tp = pct(positive(tse["z"]), prior_close), pct(positive(otc["z"]), positive(otc["y"]))
    return {"quote_at": min(stamps).isoformat(), "taiex_pct": tw, "tpex_pct": tp,
            "relative_pp": tp - tw, "gap_pct": pct(positive(tse["o"]), prior_close)}


def membership(raw, market, day):
    _, field, date_field = MEMBERS[market]
    if not isinstance(raw, list) or not raw:
        raise ValueError("invalid issuer list")
    dates = {parse_roc_date(r[date_field]) for r in raw}
    if None in dates or len(dates) != 1:
        raise ValueError("issuer list dates disagree")
    age = date.fromisoformat(day) - date.fromisoformat(next(iter(dates)))
    ids = [r[field] for r in raw if re.fullmatch(r"\d{4}", r[field])]
    if not timedelta(0) <= age <= timedelta(days=14) or len(ids) < 600 or len(ids) != len(set(ids)):
        raise ValueError("issuer list stale or incomplete")
    return sorted(ids)


def intraday_counts(rows, market, ids, now):
    day = now.astimezone(TAIPEI).date().isoformat()
    by_id = {}
    for row in rows:
        if row.get("ex") != market or row.get("c") not in ids:
            continue
        code = row["c"]
        if code in by_id:
            raise ValueError("duplicate MIS quote")
        by_id[code] = row
    up = down = flat = lower = known_limits = 0
    for row in by_id.values():
        if parse_roc_date(row.get("d", "")) != day:
            continue
        recent = row.get("trade")
        last_trade = positive(recent.get("z")) if isinstance(recent, dict) else None
        trade = last_trade or positive(row.get("z"))
        clock = recent.get("t") if last_trade else row.get("t")
        reference = positive(row.get("y"))
        if not trade or not reference or not clock:
            continue
        try:
            stamp = quote_time(day, clock)
        except (ValueError, TypeError):
            continue
        if not OPEN <= stamp.time() <= CLOSE or stamp > now:
            continue
        limit = positive(row.get("w"))
        known_limits += limit is not None
        up += trade > reference
        down += trade < reference
        flat += trade == reference
        lower += trade < reference and limit is not None and abs(trade - limit) < 1e-7
    result = counts(up, down, flat, lower, members=len(ids)) if up + down + flat else {}
    total = result.get("compared", 0)
    result.update(members=len(ids), returned=len(by_id), coverage_pct=round(100 * total / len(ids), 2),
                  limit_coverage_pct=round(100 * known_limits / total, 2) if total else 0)
    if result["coverage_pct"] < SAMPLE_MIN_PCT:
        result.update(down_pct=None, limit_down_pct=None)
    elif result["limit_coverage_pct"] < 98:
        result["limit_down_pct"] = None
    return result


def live_breadth(fetch, now, utcnow):
    day = now.astimezone(TAIPEI).date().isoformat()
    markets = {}
    for market, (source, _, _) in MEMBERS.items():
        ids = read(fetch, source, lambda raw: membership(raw, market, day))
        if not ids:
            continue
        batches = [quote_url([f"{market}_{code}.tw" for code in ids[i:i + BATCH_SIZE]])
                   for i in range(0, len(ids), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda source: read(fetch, source, quote_rows), batches))
        try:
            markets[market] = intraday_counts(
                [row for batch in results if batch is not None for row in batch],
                market, set(ids), utcnow())
        except (ValueError, TypeError, KeyError) as exc:
            print("MIS breadth:", market, type(exc).__name__, flush=True)
    return markets


def official_open(raw, day):
    if raw.get("stat") != "OK":
        raise ValueError("TWSE open unavailable")
    row, = [row for row in table_rows(raw) if parse_roc_date(row["日期"]) == day]
    value = positive(row["開盤指數"])
    if value is None:
        raise ValueError("TWSE open invalid")
    return value


def closing_breadth(fetch, day, prior, close, old, now):
    if old.get("mode") != "close" or old.get("date") != day:
        old = {}
    result = dict(old, mode="close", date=day, checked_at=now.isoformat(), taiex_pct=pct(close, prior))
    sources = {
        "tse": url(TW_BREADTH, date=day.replace("-", ""), type="MS", response="json"),
        "otc": url(OTC_BREADTH, date=day.replace("-", "/"), response="json"),
    }
    for market, source in sources.items():
        if not result.get(market):
            parsed = read(fetch, source, lambda raw: official_counts(raw, market, day))
            if parsed:
                result[market] = dict(parsed, source_url=source)
    if result.get("otc"):
        result["tpex_pct"] = result["otc"]["index_pct"]
        result["relative_pp"] = result["tpex_pct"] - result["taiex_pct"]
    if result.get("gap_pct") is None:
        source = url(TW_OHLC, date=day[:7].replace("-", "") + "01", response="json")
        index_open = read(fetch, source, lambda raw: official_open(raw, day))
        if index_open is not None:
            result["gap_pct"] = pct(index_open, prior)
            result["gap_source_url"] = source
    return result


def official_cash(record, day):
    if not (available(record) and record.get("provider") == "TWSE"
            and record.get("unit") == "TWD" and record.get("date") == day):
        return None
    rows = record.get("categories", [])
    try:
        values = {r["name"].replace("（", "(").replace("）", ")"): r["net_twd"] for r in rows}
        if len(values) != len(rows) or any(type(v) is not int for v in values.values()):
            return None
        foreign, = [value for name, value in values.items() if name in QUALIFIED_NAMES]
        parts = {"foreign_twd": foreign, "trust_twd": values["投信"],
                 "dealer_twd": values["自營商(自行買賣)"] + values["自營商(避險)"]}
        total = values["合計"]
        if total != sum(parts.values()):
            return None
        return dict(parts, total_twd=total, source_url=record["source_url"])
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def leverage(metrics, dates, fetch, previous):
    day = dates[-1]
    result = {"date": day, "cash": official_cash(
        metrics["inst"].get("official_sources", {}).get("cash_inst", {}), day)}
    record = metrics["margin"].get("official_sources", {}).get("margin", {})
    if not (available(record) and record.get("date") == day and record.get("provider") == "TWSE"
            and record.get("unit") == "TWD" and record.get("scope") == "TWSE上市市場"
            and positive(record.get("value"))):
        return result
    if len(dates) < 6:
        return result
    prior = dates[-2], dates[-6]
    refs = {d: v for d, v in previous.get("margin_references", {}).items()
            if d in prior and positive(v)}
    for d in prior:
        if d in refs:
            continue
        source = url(MARGIN, date=d.replace("-", ""), response="json", selectType="ALL")
        rows = read(fetch, source, lambda raw: parse_margin(raw, d[:7]))
        if rows and rows[0]["date"] == d:
            refs[d] = rows[0]["value"]
    result.update(margin_twd=record["value"], margin_source_url=record["source_url"],
                  margin_references=refs, prior_date=prior[0], five_day_prior_date=prior[1])
    for key, d in zip(("one_day_pct", "five_day_pct"), prior):
        result[key] = pct(record["value"], refs[d]) if d in refs else None
    return result


def snapshot(metrics, previous, closes, fetch, now, days, *, utcnow=None):
    utcnow = utcnow or (lambda: datetime.now(timezone.utc))
    local = now.astimezone(TAIPEI)
    day, clock = local.date(), local.time()
    today = day.isoformat()
    trading = days.get(day)
    result = {"schema_version": 1, "date": today, "checked_at": now.isoformat(),
              "trading_day": trading, "rule_version": RULE_VERSION, "rule": RULE}
    old_pre = previous.get("premarket", {})
    if trading and PREMARKET_START <= clock < OPEN:
        if old_pre.get("date") == today and old_pre.get("status") in ("alert", "clear"):
            result["premarket"] = old_pre
        else:
            result["premarket"] = premarket(now, days, closes, fetch, utcnow)
    elif old_pre:
        result["premarket"] = old_pre

    completed = sessions_through(day if clock >= CLOSE_REPORT else day - ONE_DAY, 6, days)
    if trading and OPEN <= clock <= CLOSE:
        earlier = sessions_through(day - ONE_DAY, 1, days)
        prior = closes.get(earlier[0]) if earlier else None
        source = quote_url(["tse_t00.tw", "otc_o00.tw"])
        index = read(fetch, source, lambda raw: indices(raw, utcnow(), prior))
        if index:
            markets = live_breadth(fetch, now, utcnow)
            result["market"] = dict(index, mode="intraday", date=today, **markets,
                                    captured_at=utcnow().isoformat(),
                                    index_source_url=source, breadth_source_url=MIS)
        else:
            result["market"] = {"mode": "unavailable", "date": today}
    elif len(completed) >= 2 and all(d in closes for d in completed[-2:]):
        close, prior = (closes[d] for d in reversed(completed[-2:]))
        result["market"] = closing_breadth(fetch, completed[-1], prior, close, previous.get("market", {}), now)
    elif previous.get("market"):
        result["market"] = previous["market"]
    if completed:
        result["leverage"] = leverage(metrics, completed, fetch, previous.get("leverage", {}))
    return result
