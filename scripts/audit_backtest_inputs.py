"""Phase 1: read-only inventory of inputs actually needed for a TX/Taiwan risk backtest.
No network requests, no backtest authorization, no implied TAIFEX-calendar certification.
"""
import collections
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
START, END = "2023-11-11", "2026-10-31"
OUT = ROOT / "docs/taifex_backtest_input_audit.json"

def read(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))

def digest(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()

def fingerprint(r):
    keys = ("date", "source_url", "source_sha256", "value", "long_oi",
            "short_oi", "scope", "unit", "provider")
    payload = {k: r.get(k) for k in keys}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def valid_date(value):
    try:
        return isinstance(value, str) and dt.date.fromisoformat(value).isoformat() == value
    except (TypeError, ValueError):
        return False

def metric_dates(records, metric):
    return [r.get("date") for r in records if r.get("metric_id") == metric]

def market_history(metrics, key, expected):
    rows = metrics.get(key, {}).get("history", [])
    dates = [r.get("date") for r in rows if valid_date(r.get("date")) and
             isinstance(r.get("value"), (int, float)) and
             not isinstance(r.get("value"), bool) and math.isfinite(r["value"])]
    actual = set(d for d in dates if START <= d <= END)
    return {"history_records": len(rows), "valid_unique_dates": len(set(dates)),
            "first_date": min(dates) if dates else None,
            "last_date": max(dates) if dates else None,
            "dates_in_target_window": len(actual),
            "matching_tx_sessions": len(actual & expected),
            "missing_tx_sessions": len(expected - actual),
            "duplicate_history_dates": len(dates) - len(set(dates)),
            "is_historical_718_session_panel": expected <= actual}

def main():
    tx = read("storage/taifex_backfill.json").get("records", [])
    twse = read("storage/twse_backfill.json").get("records", [])
    verification = read("docs/taifex_source_verification.json")
    calendar_audit = read("docs/taifex_calendar_audit.json")
    evidence = read("docs/taifex_calendar_evidence.json")
    live = read("docs/data.json")
    model_report = read("docs/backtest.json")
    with (ROOT / "storage/official_calendar/trading_days.csv").open(encoding="utf-8-sig", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    twse_sessions = {r["date"] for r in csv_rows if r["is_trading_day"] == "1"
                     and START <= r["date"] <= END}
    tx_dates = [r.get("date") for r in tx]
    tx_set = {d for d in tx_dates if valid_date(d)}
    counts = collections.Counter(tx_dates)
    dup = sorted(d for d, n in counts.items() if n > 1 and isinstance(d, str))
    identity_errors, source_metadata_errors, invalid_dates = [], [], []
    verification_errors = []
    for r in tx:
        d = r.get("date")
        if not valid_date(d) or not START <= d <= END:
            invalid_dates.append(d)
            continue
        long_, short_, net = (r.get(x) for x in ("long_oi", "short_oi", "value"))
        if (any(type(x) is not int for x in (long_, short_, net)) or
                long_ < 0 or short_ < 0 or long_ - short_ != net):
            identity_errors.append(d)
        url = urlparse(r.get("source_url", ""))
        params = parse_qs(url.query)
        if (r.get("metric_id") != "inst.futures" or
                r.get("provider") != "TAIFEX" or r.get("unit") != "contracts" or
                r.get("scope") != "TX臺股期貨;外資及陸資;未平倉淨額" or
                url.scheme != "https" or url.netloc != "www.taifex.com.tw" or
                url.path != "/cht/3/futContractsDate" or
                params.get("commodityId") != ["TXF"] or
                params.get("queryDate") != [d.replace("-", "/")] or
                params.get("queryType") != ["1"] or
                not isinstance(r.get("source_sha256"), str) or
                len(r["source_sha256"]) != 64):
            source_metadata_errors.append(d)
        checked = verification.get("results", {}).get(d, {})
        if (checked.get("status") != "pass" or
                checked.get("record_fingerprint") != fingerprint(r) or
                checked.get("actual_sha256") != r.get("source_sha256") or
                checked.get("expected_sha256") != r.get("source_sha256")):
            verification_errors.append(d)

    tx_covered = len(tx) == len(tx_set) == len(twse_sessions) == 718 and tx_set == twse_sessions
    known = []
    all_known = set()
    for entry in evidence.get("special_dates", []):
        for date in entry.get("dates", []):
            if START <= date <= END:
                all_known.add(date)
                known.append({
                    "date": date, "reason": entry.get("reason"),
                    "no_tx_record": date not in tx_set,
                    "not_a_twse_session": date not in twse_sessions,
                    "evidence_status": entry.get("status"),
                    "evidence_url": entry.get("official_url"),
                    "evidence_is_annual_pdf": ".pdf" in entry.get("official_url", "").lower(),
                    "evidence_is_generic_listing": entry.get("official_url", "").rstrip("/") ==
                                                     "https://www.taifex.com.tw/cht/11/announcement",
                })
    known.sort(key=lambda x: x["date"])
    known_unexpected = [x["date"] for x in known if not x["no_tx_record"] or
                        not x["not_a_twse_session"]]
    known_generic = [x["date"] for x in known if x["evidence_is_generic_listing"]]
    twse_counts = {}
    for metric in ("margin.margin", "inst.cash_inst"):
        ds = metric_dates(twse, metric)
        in_window = [d for d in ds if isinstance(d, str) and START <= d <= END]
        observed = set(in_window)
        twse_counts[metric] = {
            "all_records": len(ds), "records_in_window": len(in_window),
            "dates_in_window": len(observed), "missing_tx_session_dates": sorted(tx_set - observed),
            "extra_vs_tx_session_dates": sorted(observed - tx_set),
            "duplicate_dates_in_window": len(in_window) - len(observed),
        }

    market = {k: market_history(live.get("metrics", {}), k, tx_set) for k in
              ("taiex", "fx", "hy", "ig", "vix", "indices", "us10y", "nfci")}
    # Cross-section of dates for inputs/labels; dates alone do NOT prove they were observable then.
    def history_set(key):
        return {r["date"] for r in live.get("metrics", {}).get(key, {}).get("history", [])
                if valid_date(r.get("date")) and START <= r["date"] <= END}
    taiex_fx_tx_intersection = tx_set & history_set("taiex") & history_set("fx")
    twse_join_ok = all(v["dates_in_window"] == 718 and
                       not v["missing_tx_session_dates"] and
                       not v["duplicate_dates_in_window"] and
                       not v["extra_vs_tx_session_dates"] for v in twse_counts.values())
    provenance_ok = (
        verification.get("status") == "pass" and
        verification.get("total_records") == len(tx) and
        verification.get("checked_records") == len(tx) and
        verification.get("counts", {}).get("pass") == len(tx) and
        not identity_errors and not source_metadata_errors and
        not invalid_dates and not verification_errors
    )

    blockers = []
    if not tx_covered or dup or invalid_dates:
        blockers.append("tx_session_dates_missing_or_extra")
    if identity_errors or source_metadata_errors:
        blockers.append("tx_numeric_or_source_metadata_invalid")
    if not provenance_ok:
        blockers.append("tx_official_source_verification_missing_or_stale")
    if not twse_join_ok:
        blockers.append("twse_margin_or_cash_institutional_session_alignment_gap")
    if known_unexpected or len(all_known) != 10:
        blockers.append("known_closure_dates_conflict_or_incomplete")
    if not market["taiex"]["is_historical_718_session_panel"]:
        blockers.append("taiex_historical_outcome_prices_incomplete")
    if not market["fx"]["is_historical_718_session_panel"]:
        blockers.append("fx_historical_signal_incomplete")
    # Needed for the planned *full* cross-market model, not for isolated TX-factor diagnostics.
    if any(not market[k]["is_historical_718_session_panel"] for k in ("hy", "ig", "vix", "indices", "us10y", "nfci")):
        blockers.append("global_risk_factor_histories_incomplete_for_full_model")
    blockers.append("point_in_time_release_lag_and_holdout_method_not_frozen")
    if not evidence.get("gate", {}).get("independent_taifex_calendar_verified", False):
        blockers.append("independent_taifex_calendar_evidence_not_finalized")

    report = {
        "status": "phase1_input_audit_complete",
        "scope": [START, END],
        "audit_type": "repository_snapshot_no_network_fetch",
        "input_sha256": {p: digest(p) for p in (
            "storage/taifex_backfill.json", "storage/twse_backfill.json",
            "storage/official_calendar/trading_days.csv",
            "docs/taifex_source_verification.json", "docs/taifex_calendar_evidence.json",
            "docs/data.json")},
        "tx_panel": {
            "raw_rows": len(tx), "distinct_dates": len(tx_set),
            "first_date": min(tx_set) if tx_set else None,
            "last_date": max(tx_set) if tx_set else None,
            "twse_reference_sessions": len(twse_sessions),
            "missing_vs_twse_reference": sorted(twse_sessions - tx_set),
            "extra_vs_twse_reference": sorted(tx_set - twse_sessions),
            "duplicate_dates": dup, "invalid_dates": invalid_dates,
            "oi_identity_errors": identity_errors,
            "metadata_or_source_url_errors": source_metadata_errors,
            "source_verification_report_status": verification.get("status"),
            "source_verified_records": verification.get("counts", {}).get("pass"),
            "fingerprint_or_value_hash_verification_failures": verification_errors,
            "every_current_tx_record_matches_persisted_verification": provenance_ok,
            "has_tx_futures_ohlc_prices": all(any(k in r for k in
                ("open", "high", "low", "close", "settlement_price")) for r in tx) if tx else False,
            "explanation": "This dataset stores foreign/China investor TXF long/short/net open interest, not TXF traded OHLC prices."
        },
        "trading_dates": {
            "candidate_718_dates_match_twse": tx_covered,
            "calendar_provisional_reconciliation_status": calendar_audit.get("status"),
            "independent_taifex_calendar_verified": evidence.get("gate", {}).get("independent_taifex_calendar_verified", False),
            "known_special_closed_days_count": len(all_known),
            "known_special_days": known,
            "special_dates_conflicting_with_observations_or_calendar": known_unexpected,
            "generic_listing_evidence_only_dates": known_generic,
            "annual_notice_archive_sweep_required_for_completeness_claim": True,
            "note": "TWSE date agreement is a cross-check, not independent proof of every TAIFEX exceptional closure."
        },
        "twse_overlap": twse_counts,
        "current_market_histories": market,
        "tx_taiex_fx_same_day_intersection": {
            "count": len(taiex_fx_tx_intersection),
            "first_date": min(taiex_fx_tx_intersection) if taiex_fx_tx_intersection else None,
            "last_date": max(taiex_fx_tx_intersection) if taiex_fx_tx_intersection else None,
            "note": "Same-date intersections alone do not ensure availability-time alignment or enough holdout samples."
        },
        "current_diagnostic_backtest": {
            "status": model_report.get("status"),
            "common_sessions": model_report.get("common_sessions"),
            "method": model_report.get("method")
        },
        "backtest_impacting_gaps": blockers,
        "risk_only_vs_trading_backtest": {
            "risk_prediction": "Needs full historical target TAIEX prices and contemporaneously available historical signals; TXF OHLC prices are not required solely to predict TAIEX drawdowns.",
            "tradeable_txf_strategy": "Additionally requires TXF settlement/tradable prices, contract roll rules, fees and slippage; not supplied by this OI panel."
        },
        "full_model_backtest_authorized": False,
        "live_threshold_changes_authorized": False
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PHASE1_AUDIT", report["status"])
    print("TX", len(tx), "source reverified/current fingerprint matches", len(tx) - len(verification_errors),
          "date alignment", len(tx_set & twse_sessions))
    print("TWSE signal alignment", twse_join_ok, "known closures", len(all_known),
          "conflicts", len(known_unexpected))
    print("TAIEX/FX/TX intersection", len(taiex_fx_tx_intersection))
    print("GAPS", blockers)

if __name__ == "__main__":
    main()
