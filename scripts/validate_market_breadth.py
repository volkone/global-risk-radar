"""Research check of weakening 20-day breadth near a TAIEX high."""

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from crash_watch_validation import (
    TARGETS, candidates, evaluate, taiwan_prices, trailing_labels,
)
from taiwan_crash_watch import ROOT, pct, us_prices

SOURCE = "https://mofiinvestment.com/tools/margin_maintenance/"
PERIODS = (("2021-07-01", "2025-12-31"), ("2021-07-01", "2023-12-31"),
           ("2024-01-01", "2025-12-31"))
HIGH_WINDOW, HIGH_DISTANCE_PCT = 60, 5
BREADTH_WINDOW, BREADTH_CHANGE_PP, MIN_DECLINING_DAYS = 5, -10, 3


def breadth_rows(html):
    # The public research page embeds its displayed combined-market observations.
    marker = re.search(r"const EMBEDDED\s*=\s*", html)
    if not marker:
        raise ValueError("breadth source format changed")
    source, _ = json.JSONDecoder().raw_decode(html[marker.end():])
    out = {}
    for row in source["series"]:
        day = date.fromisoformat(row["date"]).isoformat()
        value = row["pct_above_ma20"]
        if day in out or not 0 <= value <= 100:
            raise ValueError("invalid breadth observation")
        out[day] = value, row["close"]
    return out


def rule_at(tw, days, index, breadth):
    own, recent = days[index - HIGH_WINDOW:index], days[index - BREADTH_WINDOW - 1:index]
    if len(own) < HIGH_WINDOW or any(day not in breadth for day in recent):
        return None
    values = [breadth[day][0] for day in recent]
    return (pct(tw[own[-1]], max(tw[day] for day in own)) >= -HIGH_DISTANCE_PCT
            and values[-1] - values[0] <= BREADTH_CHANGE_PP
            and sum(b < a for a, b in zip(values, values[1:])) >= MIN_DECLINING_DAYS)


def compare(prices, sox, tsm, breadth):
    days, base = candidates(prices, sox, tsm)
    scored = []
    for row in base:
        if not PERIODS[0][0] <= row["date"] <= PERIODS[0][1] or not row["covers"]:
            continue
        signal = rule_at(prices, days, row["i"], breadth)
        if signal is not None:
            scored.append(dict(row, breadth=signal, combined=row["rule"] or signal))
    result = []
    for start, end in PERIODS:
        months = (int(end[:4]) - int(start[:4])) * 12 + int(end[5:7]) - int(start[5:7]) + 1
        block = {"start": start, "end": end, "months": months, "targets": {}}
        selected = [r for r in scored if start <= r["date"] <= end]
        for horizon, threshold in TARGETS.items():
            labels = trailing_labels(prices, days, selected, end, horizon, threshold)
            block["targets"][str(horizon)] = {
                "threshold_pct": threshold, "sessions": len(labels),
                "events": sum(row["event"] for row in labels),
                **{key: evaluate(labels, months, horizon, key) for key in ("rule", "breadth", "combined")},
            }
        result.append(block)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("breadth", "taiwan", "sox", "tsm"):
        parser.add_argument(f"--{name}-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/taiwan_breadth_validation.json")
    args = parser.parse_args()
    inputs = {name: getattr(args, f"{name}_file").read_bytes()
              for name in ("breadth", "taiwan", "sox", "tsm")}
    breadth = breadth_rows(inputs["breadth"].decode("utf-8"))
    tw, overlap = taiwan_prices(json.loads(inputs["taiwan"]))
    sox = us_prices(json.loads(inputs["sox"]), "^SOX")
    tsm = us_prices(json.loads(inputs["tsm"]), "TSM")
    for day, (_, close) in breadth.items():
        if day in tw and abs(tw[day] - close) > 0.01:
            raise ValueError(f"TAIEX close mismatch on breadth source date {day}")
    result = {
        "schema_version": 1, "status": "historical_research",
        "asof": "08:30 Asia/Taipei",
        "breadth_source": SOURCE,
        "breadth_series": "combined listed and OTC ordinary shares, public historical research series",
        "assumption": "Previous Taiwan session's end-of-day data, daily publication proxy. Historical publication times are not certified.",
        "live_series": "Independently rebuilt from official unadjusted TWSE/TPEx closes, reported per market.",
        "rule": {"high_window": HIGH_WINDOW, "within_high_pct": HIGH_DISTANCE_PCT,
                 "breadth_window": BREADTH_WINDOW, "breadth_change_pp": BREADTH_CHANGE_PP,
                 "min_declining_days": MIN_DECLINING_DAYS},
        "input_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in inputs.items()},
        "taiex_official_overlap_matches": overlap,
        "blocks": compare(tw, sox, tsm, breadth),
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Breadth validation:", [(row["start"], row["end"]) for row in result["blocks"]])


if __name__ == "__main__":
    main()
