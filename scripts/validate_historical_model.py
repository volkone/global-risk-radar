"""Time-ordered historical validation with the existing six-factor model."""
import hashlib
import json

from audit_phase3_robustness import outcome, scorer, summarize, block_bootstrap
from dashboard_scores import PANEL, ROOT, clean_rows
from backtest_phase2_research import prepare
from phase5_forward_capture import verify_frozen
from model_gate import historical_horizon_passed

REPORT = ROOT / "docs/historical_model_validation.json"
SCHEME = "historical_expanding_window"
FOLD_SESSIONS = 60
HORIZONS = ("5d", "20d")


def main():
    panel = PANEL.read_bytes()
    protocol = ROOT / "docs/phase4_frozen_prospective_protocol.json"
    frozen = verify_frozen()
    calendar = json.loads((ROOT / "docs/taifex_prebacktest_gate.json").read_bytes())
    excluded = calendar["excluded_dates"]
    rows = clean_rows([row for row in json.loads(panel)["rows"] if row["date"] not in excluded])
    features = prepare(rows)
    lag = frozen["post_close_feature_action_lag_taiwan_sessions"]
    # Starting at the first usable fit preserves the existing 120-observation
    # calibration minimum. Each subsequent block uses a new expanding fit.
    fits = []
    for start in range(120, len(rows)):
        fitted = scorer(features, start, lag)
        if fitted is not None:
            fits.append((start, fitted))
            break
    if not fits:
        raise SystemExit("Not enough verified data for the existing historical fit")
    for start in range(fits[0][0] + FOLD_SESSIONS, len(rows), FOLD_SESSIONS):
        fitted = scorer(features, start, lag)
        if fitted is None:
            raise SystemExit("Unexpected calibration failure in an expanding fold")
        fits.append((start, fitted))

    horizons = {}
    for label, cutoff in frozen["warning_events_taiwan_trading_days_worst_forward_close_drawdown_pct"].items():
        horizon = int(label[:-1])
        cases, folds = [], []
        for start, (scores, threshold, _) in fits:
            end = min(start + FOLD_SESSIONS, len(rows) - horizon)
            if end <= start:
                continue
            block = [case for case in outcome(rows[:end + horizon], scores, threshold, start, horizon, cutoff)
                     if case["index"] < end]
            cases.extend(block)
            folds.append({"train_end": rows[start - 1]["date"], "test_start": rows[start]["date"],
                          "test_end": rows[end - 1]["date"], "threshold": threshold, **summarize(block)})

        disjoint, last_end = [], -1
        for case in cases:
            if case["index"] > last_end:
                disjoint.append(case)
                last_end = case["index"] + horizon
        horizons[label] = {
            "metrics": summarize(cases),
            "nonoverlapping": summarize(disjoint),
            "block_bootstrap": block_bootstrap(cases, horizon),
            "folds": folds,
        }

    passed = all(historical_horizon_passed(horizons[key]["metrics"]) for key in HORIZONS)
    result = {
        "schema_version": 1,
        "validation_mode": SCHEME,
        "historical_validation_passed": passed,
        "source_panel_sha256": hashlib.sha256(panel).hexdigest(),
        "frozen_protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(),
        "excluded_dates": excluded,
        "historical_sessions": len(rows),
        "horizons": horizons,
        "acceptance": "30 mature historical windows per horizon and alert precision above the historical event base rate in each horizon.",
        "method": "Expanding fits calibrated only on earlier dated features, 60-session evaluation blocks, two-session feature lag. No outcomes enter calibration.",
        "limitations": "Historical dates were previously examined. Forward windows may overlap; disjoint results and horizon-length block bootstrap are shown alongside the point estimates. This is retrospective evidence.",
    }
    REPORT.write_text(json.dumps(result, indent=2) + "\n")
    for key, item in horizons.items():
        print(key, item["metrics"], "disjoint:", item["nonoverlapping"])
    print("Historical validation:", "PASS" if passed else "BLOCKED")


if __name__ == "__main__":
    main()
