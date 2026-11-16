"""Replay the frozen research model under stricter daily vintage cutoffs."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from statistics import mean

from audit_phase4_publication_timing import source_eligibility
from audit_publication_evidence_scope import digest, exclude_unused_versions, PANEL_PATH, VINTAGE_PATH
from dashboard_scores import reconstruct
from phase5_forward_ledger import frozen_distributions

ROOT = Path(__file__).resolve().parents[1]
DELAYS = (1, 2, 3)
OUTCOMES = {5: -0.03, 20: -0.05}


def select_delayed(rows, vintages, delay):
    revised = deepcopy(rows)
    for factor, stream in vintages["series"].items():
        bootstrap = stream["bootstrap_date"]
        state = {item["date"]: item["value"] for item in stream["bootstrap"]}
        events = iter(stream["changes"])
        event = next(events, None)
        if stream["changes"] != sorted(stream["changes"], key=lambda item: item["vintage_date"]):
            raise ValueError(f"Unordered vintage changes for {factor}")
        for row in revised:
            selected = row["us_previous_dated_observations"][factor]
            cutoff = (date.fromisoformat(selected["asof_us_calendar_date"]) - timedelta(days=delay)).isoformat()
            decision = datetime.fromisoformat(selected["decision_at_taipei"])
            while event and event["vintage_date"] <= cutoff:
                observed, value = event["observed_date"], event["value"]
                if value is None:
                    state.pop(observed, None)
                else:
                    state[observed] = value
                event = next(events, None)
            earliest = (date.fromisoformat(row["date"]) - timedelta(days=21)).isoformat()
            observed = None
            release = None
            if cutoff >= bootstrap:
                for candidate in sorted((d for d in state if earliest <= d <= cutoff), reverse=True):
                    schedule, _ = source_eligibility(factor, candidate)
                    if schedule is None or schedule < decision:
                        observed, release = candidate, schedule
                        break
            selected.update({
                "asof_us_calendar_date": cutoff,
                "observed_date": observed,
                "value": state[observed] if observed else None,
                "age_calendar_days": (date.fromisoformat(row["date"]) - date.fromisoformat(observed)).days if observed else None,
                "stale": False,
                "time_gate_passed": observed is not None,
                "conservative_earliest_use_at_taipei": release.astimezone(decision.tzinfo).isoformat() if release else None,
                "actual_historical_release_timestamp_verified": False,
            })
    return revised


def summarize(original, delayed, rows, threshold):
    paired = [(i, a["score"], b["score"]) for i, (a, b) in enumerate(zip(original, delayed))
              if a["score"] is not None and b["score"] is not None]
    differences = [abs(a - b) for _, a, b in paired]
    changed_threshold = [
        {"date": rows[i]["date"], "frozen_score": a, "delayed_score": b}
        for i, a, b in paired if (a >= threshold) != (b >= threshold)
    ]
    outcomes = {}
    closes = [row["taiex_price_index_close"] for row in rows]
    for days, cutoff in OUTCOMES.items():
        cohorts = [(a, b, min(closes[i+1:i+1+days]) / closes[i] - 1 <= cutoff)
                   for i, a, b in paired if i + days < len(closes)]
        def evaluate(column):
            alerts = [entry[2] for entry in cohorts if entry[column] >= threshold]
            return {"alerts": len(alerts), "hits": sum(alerts),
                    "precision": round(sum(alerts) / len(alerts), 6) if alerts else None}
        outcomes[f"{days}d"] = {"common_matured_dates": len(cohorts), "events": sum(c[2] for c in cohorts),
                               "frozen": evaluate(0), "delayed": evaluate(1)}
    return {
        "valid_scores": sum(row["score"] is not None for row in delayed),
        "paired_scores": len(paired),
        "mean_absolute_difference": round(mean(differences), 5),
        "max_absolute_difference": round(max(differences), 5),
        "research_threshold_disagreements": len(changed_threshold),
        "changed_threshold_dates": changed_threshold,
        "historical_event_diagnostics": outcomes,
    }


def main():
    panel_raw, vintage_raw = PANEL_PATH.read_bytes(), VINTAGE_PATH.read_bytes()
    rows = json.loads(panel_raw)["rows"]
    vintages = exclude_unused_versions(json.loads(vintage_raw))
    independent = json.loads((ROOT / "docs/alfred_vintage_interval_verification.json").read_bytes())
    if not (independent["effective_date_intervals_verified_after_scoped_exclusion"] and
            independent["source_panel_sha256"] == digest(panel_raw) and
            independent["source_vintage_sha256"] == digest(vintage_raw)):
        raise SystemExit("ALFRED version evidence does not match the frozen inputs")
    frozen = json.loads((ROOT / "docs/phase4_frozen_prospective_protocol.json").read_bytes())
    distributions = frozen_distributions()
    lag = frozen["post_close_feature_action_lag_taiwan_sessions"]
    baseline = reconstruct(rows, distributions, lag)
    threshold = frozen["alert_score_threshold_frozen_before_future_outcomes"]
    zero = reconstruct(select_delayed(rows, vintages, 0), distributions, lag)
    published = json.loads((ROOT / "docs/risk_dashboard.json").read_bytes())["taiwan_history"]
    if zero != baseline or published != baseline:
        raise SystemExit("Zero-delay replay differs from the frozen model")
    scenarios = {}
    for delay in DELAYS:
        adjusted = select_delayed(rows, vintages, delay)
        scenarios[str(delay)] = summarize(baseline, reconstruct(adjusted, distributions, lag), rows, threshold)
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "panel_sha256": digest(panel_raw),
        "vintages_sha256": digest(vintage_raw),
        "sessions": len(rows),
        "frozen_valid_scores": sum(row["score"] is not None for row in baseline),
        "zero_delay_replay_identical": True,
        "research_threshold": threshold,
        "rule": "Shift each of six original US as-of date cutoffs backward by extra calendar days. Keep the original source schedule checks, 21-day maximum observation age, frozen distributions and two-session model lag.",
        "additional_calendar_days": scenarios,
        "scope": "Descriptive sensitivity analysis on previously viewed data; does not attest to original publication timestamps or provide independent validation.",
        "formal_publication_timestamp_attested": False,
    }
    (ROOT / "docs/pit_availability_delay_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({delay: {key: value for key, value in scenario.items() if key != "changed_threshold_dates"}
                      for delay, scenario in scenarios.items()}, indent=2))


if __name__ == "__main__":
    main()
