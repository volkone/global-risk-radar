"""Phase 2: research-only, auditable TX/TWSE/TAIEX/FX trading-session panel.
Daily Taiwan features are end-of-day observations: eligible from next TX session.
US noon FX/market factors must be strictly earlier-dated. Weekly NFCI is NOT
mapped to trading days until publication timestamps are independently established.
No prediction, execution price, PnL, or full-model backtest is computed.
"""
import bisect
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "2023-11-11", "2026-10-31"
PANEL = ROOT / "storage/phase2_joined_panel.json"
REPORT = ROOT / "docs/phase2_join_audit.json"
MARKETS = ("fx", "hy", "ig", "vix", "us10y")

def read(path, fallback):
    file = ROOT / path
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else fallback

def main():
    tx = read("storage/taifex_backfill.json", {})["records"]
    twse = read("storage/twse_backfill.json", {})["records"]
    taiex = read("storage/historical_taiex_close.json", {"records": []}).get("records", [])
    factors = read("storage/historical_fred_factors.json", {"series": {}}).get("series", {})
    verified = read("docs/taifex_source_verification.json", {})
    with (ROOT / "storage/official_calendar/trading_days.csv").open(
            encoding="utf-8-sig", newline="") as f:
        sessions = sorted(r["date"] for r in csv.DictReader(f)
                          if r["is_trading_day"] == "1" and START <= r["date"] <= END)
    assert len(sessions) == len(set(sessions)) == 718, "unexpected TWSE session list"
    assert len(tx) == 718 and verified.get("counts", {}).get("pass") == 718, "TX base incomplete"
    txidx = {r["date"]: r for r in tx}
    assert set(txidx) == set(sessions), "TX dates must equal selected reference sessions"
    twseidx = {(r["metric_id"], r["date"]): r for r in twse}
    priceidx = {r["date"]: r for r in taiex}
    daily = {}
    for name in MARKETS:
        series = factors.get(name, {}).get("history", [])
        dates = sorted(r["date"] for r in series)
        assert len(dates) == len(set(dates)), "FRED duplicate dates " + name
        daily[name] = (dates, {r["date"]: r["value"] for r in series})

    def asof(name, session_date, max_stale_days=7):
        dates, mapping = daily[name]
        index = bisect.bisect_left(dates, session_date) - 1
        if index < 0:
            return {"value": None, "observed_date": None, "age_calendar_days": None,
                    "missing_reason": "no_prior_publication_date"}
        srcdate = dates[index]
        days = (dt.date.fromisoformat(session_date) - dt.date.fromisoformat(srcdate)).days
        if not 1 <= days <= max_stale_days:
            return {"value": None, "observed_date": srcdate, "age_calendar_days": days,
                    "missing_reason": "stale_source_observation"}
        return {"value": mapping[srcdate], "observed_date": srcdate,
                "age_calendar_days": days, "missing_reason": None}

    result = []
    count = {"tx_oi": 0, "margin": 0, "cash_inst": 0, "taiex_close": 0}
    count.update({k: 0 for k in MARKETS})
    missing_price = []
    missing_twse = []
    for i, date in enumerate(sessions):
        t = txidx[date]
        cash = twseidx.get(("inst.cash_inst", date))
        margin = twseidx.get(("margin.margin", date))
        price = priceidx.get(date)
        if not cash or not margin:
            missing_twse.append(date)
        if price is None:
            missing_price.append(date)
        features = {name: asof(name, date) for name in MARKETS}
        row = {
            "date": date, "tx_oi_net_contracts": t["value"],
            "tx_oi_long_contracts": t["long_oi"],
            "tx_oi_short_contracts": t["short_oi"],
            "margin_balance_twd": margin["value"] if margin else None,
            "cash_institutional_net_twd": cash["value"] if cash else None,
            "taiex_price_index_close": price["value"] if price else None,
            "us_previous_dated_observations": features,
            "tw_end_of_day_signals_eligible_from_session": sessions[i + 1]
            if i + 1 < len(sessions) else None,
            "signal_time_assumption": "TX_OI/TWSE_margin_and_cash_available_after_same_date_close",
        }
        result.append(row)
        for key, cond in {
                "tx_oi": True, "margin": margin is not None,
                "cash_inst": cash is not None, "taiex_close": price is not None}.items():
            if cond:
                count[key] += 1
        for name, item in features.items():
            if item["value"] is not None:
                count[name] += 1

    joined_minimal = sum(1 for r in result if r["taiex_price_index_close"] is not None and
                         r["us_previous_dated_observations"]["fx"]["value"] is not None and
                         r["margin_balance_twd"] is not None and
                         r["cash_institutional_net_twd"] is not None)
    issues = []
    if missing_price:
        issues.append("taiex_prices_missing_" + str(len(missing_price)) + "_sessions")
    if missing_twse:
        issues.append("twse_features_missing_" + str(len(missing_twse)) + "_sessions")
    if count["fx"] < 700:
        issues.append("prior_dated_usd_twd_fx_asof_coverage_inadequate_" + str(count["fx"]))
    if any(count[k] < 700 for k in ("hy", "ig", "vix", "us10y")):
        issues.append("us_daily_factors_asof_coverage_inadequate")
    issues.extend(["FRED_historical_vintage_and_actual_release_time_not_certified",
                   "NFCI_weekly_publication_date_join_not_certified",
                   "out_of_sample_holdout_and_transaction_cost_contract_not_approved",
                   "independent_taifex_calendar_evidence_not_finalized"])
    snapshot = {"schema_version": 1, "window": [START, END],
                "scope": "Research-only EOD Taiwan TX/TWSE with US prior-dated factor candidates",
                "rows": result, "formal_backtest_authorized": False}
    PANEL.parent.mkdir(parents=True, exist_ok=True)
    PANEL.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "status": "aligned_research_panel" if not missing_price and count["fx"] >= 700 else "incomplete_research_panel",
        "window": [START, END], "calendar_reference": "TWSE monthly FMTQIK verified trading dates",
        "trading_sessions": len(sessions), "field_coverage_count": count,
        "full_tx_twse_price_fx_candidate_sessions": joined_minimal,
        "missing_taiex_price_dates": missing_price, "missing_twse_dates": missing_twse,
        "blocking_gaps": issues,
        "point_in_time_safeguards": {
            "same_day_TWSE_TX_data_not_tradable_at_same_day_close": True,
            "us_market_and_fx_observations_strictly_earlier_calendar_date": True,
            "prior_us_data_max_age_calendar_days": 7,
            "NFCI_weekly_factor_joined": False,
            "FRED_anti_revision_vintage_check_passed": False,
            "futures_roll_and_executable_prices_present": False,
        },
        "snapshot_sha256": hashlib.sha256(PANEL.read_bytes()).hexdigest(),
        "full_model_backtest_authorized": False, "live_threshold_changes_authorized": False,
        "note": "Lagged same-date semantics are preliminary; source's actual posting lag remains unverified. No PnL computed."
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PHASE2_PANEL", report["status"], len(result), "price", count["taiex_close"],
          "fx_prior", count["fx"], "full_minimal", joined_minimal)
    print("BLOCKERS", issues)

if __name__ == "__main__":
    main()
