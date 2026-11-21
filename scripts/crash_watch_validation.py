"""Retrospective check of the frozen selloff rule against a Taiwan-only baseline."""
import argparse
import hashlib
import json
from bisect import bisect_right
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from urllib.request import Request, urlopen

from taiwan_crash_watch import (
    CUTOFF, FMTQIK, ROOT, RULE, RULE_VERSION, TAIPEI, archive_closes, expected_us_session,
    fmtqik_month, url,
    pct, positive, taiwan_features, us_available_at, us_change, us_prices,
    warning, yahoo_chart,
)

TAIEX_URL = ("https://api.finmindtrade.com/api/v4/data"
             "?dataset=TaiwanStockPrice&data_id=TAIEX&start_date=1999-01-01")
CASE_TWSE_URL = url(FMTQIK, response="json", date="20261101")
US_START, US_END = 915148800, 1795305600  # 1999-01-01 to 2026-11-22 UTC exclusive.
SOX_URL = yahoo_chart("%5ESOX", interval="1d", period1=US_START, period2=US_END)
TSM_URL = yahoo_chart("TSM", interval="1d", period1=US_START, period2=US_END)
FIRST, SPLIT, LAST = "2000-01-01", "2013-01-01", "2025-12-31"
CASE = "2026-11-20"
TARGETS = {1: -4, 5: -8}


def source_bytes(link, path=None):
    if path is not None:
        return path.read_bytes()
    req = Request(link, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        return response.read()


def taiwan_prices(raw):
    prices = {}
    for row in raw["data"]:
        if row["stock_id"] != "TAIEX":
            raise ValueError("unexpected index")
        day, value = date.fromisoformat(row["date"]).isoformat(), positive(row["close"])
        if day in prices or value is None:
            raise ValueError("invalid Taiwan price row")
        prices[day] = value
    official = archive_closes()
    errors = [day for day, value in official.items()
              if day in prices and abs(prices[day] - value) > 0.01]
    matched = sum(day in prices for day in official)
    if errors or matched != len(official):
        raise ValueError(f"Taiwan source differs in official overlap: {len(errors)} / {matched}")
    return prices, matched


def candidates(tw, sox, tsm):
    days = sorted(tw)
    us_dates = sorted(sox.keys() | tsm.keys())
    available = [us_available_at(day) for day in us_dates]
    result = []
    for i in range(20, len(days)):
        day = days[i]
        if not FIRST <= day <= LAST and day != CASE:
            continue
        timestamp = datetime.combine(date.fromisoformat(day), CUTOFF, TAIPEI)
        current = bisect_right(available, timestamp) - 1
        if current < 1:
            raise ValueError("insufficient US price history")
        us_date, us_prior = us_dates[current], us_dates[current - 1]
        sox_pct, tsm_pct = us_change(sox, us_date, us_prior), us_change(tsm, us_date, us_prior)
        local = taiwan_features(tw, days[i - 20:i])
        complete = (sox_pct is not None and tsm_pct is not None
                    and 0 <= (timestamp - available[current]).total_seconds() <= 5 * 86400)
        result.append({
            "date": day, "i": i, "us_date": us_date, "taiwan": local,
            "sox_pct": sox_pct, "tsm_pct": tsm_pct,
            "covers": complete,
            "rule": warning(local, sox_pct, tsm_pct) if complete else None,
            "baseline": local["prior_day_pct"] <= RULE["prior_day_pct"],
        })
    return days, result


def trailing_labels(tw, days, rows, end, horizon, threshold):
    labels = []
    for row in rows:
        i = row["i"]
        later = days[i:i + horizon]
        if len(later) != horizon or later[-1] > end:
            continue
        returns = [pct(tw[day], tw[days[i - 1]]) for day in later]
        event = returns[-1] <= threshold
        lead = next((j for j, change in enumerate(returns) if change <= threshold), None) if event else None
        labels.append(dict(row, event=event, lead_sessions=lead))
    return labels


def episodes(events, horizon):
    grouped = []
    for event in events:
        if not grouped or event["i"] - grouped[-1][-1]["i"] >= horizon:
            grouped.append([])
        grouped[-1].append(event)
    return grouped


def evaluate(labels, months, horizon, key):
    alarms = [r for r in labels if r[key]]
    events = [r for r in labels if r["event"]]
    hits = [r for r in alarms if r["event"]]
    event_groups = episodes(events, horizon)
    leads = [r["lead_sessions"] for r in hits]
    return {
        "alerts": len(alarms),
        "hits": len(hits),
        "misses": len(events) - len(hits),
        "false_alarms": len(alarms) - len(hits),
        "false_per_month": round((len(alarms) - len(hits)) / months, 3),
        "precision_pct": round(100 * len(hits) / len(alarms), 2) if alarms else None,
        "recall_pct": round(100 * len(hits) / len(events), 2) if events else None,
        "episodes_hit": sum(any(r[key] for r in group) for group in event_groups),
        "episodes": len(event_groups),
        "lead_sessions_median": median(leads) if leads else None,
        "lead_sessions_range": [min(leads), max(leads)] if leads else None,
    }


def run(raw_taiwan, raw_sox, raw_tsm, raw_case):
    tw, verified = taiwan_prices(json.loads(raw_taiwan))
    official_case = fmtqik_month(json.loads(raw_case), CASE[:7])
    if CASE not in official_case or any(tw.get(day) != row["value"]
                                        for day, row in official_case.items() if day <= CASE):
        raise ValueError("Taiwan November case source differs from TWSE")
    sox, tsm = us_prices(json.loads(raw_sox), "^SOX"), us_prices(json.loads(raw_tsm), "TSM")
    days, rows = candidates(tw, sox, tsm)
    report = {
        "schema_version": 1,
        "rule_version": RULE_VERSION,
        "rule": RULE,
        "as_of_taipei": "08:30",
        "period": [FIRST, LAST],
        "sources": [
            {"name": name, "url": link, "sha256": hashlib.sha256(raw).hexdigest()}
            for name, link, raw in (("FinMind TAIEX", TAIEX_URL, raw_taiwan),
                                     ("Yahoo Finance SOX", SOX_URL, raw_sox),
                                     ("Yahoo Finance TSM", TSM_URL, raw_tsm),
                                     ("TWSE 台股 11 月收盤", CASE_TWSE_URL, raw_case))
        ],
        "official_overlap_matches": verified,
        "blocks": [],
    }
    for start, end in ((FIRST, LAST), (FIRST, "2012-12-31"), (SPLIT, LAST)):
        months = int(end[:4]) * 12 + int(end[5:7]) - int(start[:4]) * 12 - int(start[5:7]) + 1
        covered = [r for r in rows if start <= r["date"] <= end]
        block = {"start": start, "end": end, "months": months, "targets": {}}
        for horizon, threshold in TARGETS.items():
            eligible = trailing_labels(tw, days, covered, end, horizon, threshold)
            scored = [r for r in eligible if r["covers"]]
            block["targets"][str(horizon)] = {
                "horizon_sessions": horizon,
                "threshold_pct": threshold,
                "eligible": len(eligible),
                "scored": len(scored),
                "excluded_missing_premarket_data": len(eligible) - len(scored),
                "events": sum(r["event"] for r in scored),
                "multisource": evaluate(scored, months, horizon, "rule"),
                "baseline": evaluate(scored, months, horizon, "baseline"),
            }
        report["blocks"].append(block)
    full = report["blocks"][0]["targets"]
    report["qualification"] = "research_only"
    report["baseline_comparison"] = {
        horizon: {
            "more_hits": target["multisource"]["hits"] > target["baseline"]["hits"],
            "fewer_false_alarms": target["multisource"]["false_alarms"] < target["baseline"]["false_alarms"],
        } for horizon, target in full.items()
    }

    case, = [r for r in rows if r["date"] == CASE]
    cutoff = datetime.combine(date.fromisoformat(CASE), CUTOFF, TAIPEI)
    if case["us_date"] != expected_us_session(cutoff) or not case["covers"]:
        raise ValueError("case inputs violate premarket dates")
    prior = case["taiwan"]["date"]
    report["case"] = {
        "date": CASE, "type": "historical_replay", "assumed_cutoff_taipei": cutoff.isoformat(),
        "taiwan": case["taiwan"], "us_date": case["us_date"],
        "sox_pct": case["sox_pct"], "tsm_pct": case["tsm_pct"],
        "multisource_alert": case["rule"], "baseline_alert": case["baseline"],
        "close": tw[CASE], "change_points": round(tw[CASE] - tw[prior], 2),
        "change_pct": pct(tw[CASE], tw[prior]),
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("taiwan", "sox", "tsm", "case"):
        parser.add_argument(f"--{name}-file", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/taiwan_crash_watch_validation.json")
    args = parser.parse_args()
    report = run(source_bytes(TAIEX_URL, args.taiwan_file), source_bytes(SOX_URL, args.sox_file),
                 source_bytes(TSM_URL, args.tsm_file), source_bytes(CASE_TWSE_URL, args.case_file))
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Selloff research:", report["period"], report["official_overlap_matches"], "official matches")


if __name__ == "__main__":
    main()
