"""Check the effect of explicitly excluding two unused archived versions."""
from argparse import ArgumentParser
from bisect import bisect_right
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from audit_pit_full_replay import replay_audit
from dashboard_scores import reconstruct
from phase5_forward_ledger import frozen_distributions

ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = ROOT / "storage/phase4_publication_aware_panel.json"
VINTAGE_PATH = ROOT / "storage/phase3_fred_pit_vintages.json"
H10 = "https://www.federalreserve.gov/releases/h10/releaseDates.json"
VIX = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
NY = ZoneInfo("America/New_York")
EXCLUDED_DATE = "2023-11-13"
EXCLUDED_VINTAGE = "2024-01-15"
EXCLUDED_VALUES = {"hy": 4.03, "ig": 1.25}


def exclude_unused_versions(vintages):
    scoped = deepcopy(vintages)
    for factor, expected in EXCLUDED_VALUES.items():
        stream = scoped["series"][factor]
        if stream["bootstrap_date"] != EXCLUDED_VINTAGE:
            raise ValueError(f"Unexpected bootstrap date for {factor}")
        removed = [item for item in stream["bootstrap"] if item["date"] == EXCLUDED_DATE]
        if removed != [{"date": EXCLUDED_DATE, "value": expected}]:
            raise ValueError(f"Unexpected exclusion candidate for {factor}")
        stream["bootstrap"] = [item for item in stream["bootstrap"] if item["date"] != EXCLUDED_DATE]
    return scoped


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def download(url):
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as response:
        return response.read()


def audit_source_dates(panel, h10_raw, vix_raw):
    releases = sorted({
        datetime.strptime(stamp, "%Y%m%d").date()
        for year in json.loads(h10_raw) for month in year["Months"] for stamp in month["Dates"]
    })
    vix = {
        datetime.strptime(r["DATE"], "%m/%d/%Y").date().isoformat(): float(r["CLOSE"])
        for r in csv.DictReader(io.StringIO(vix_raw.decode("utf-8-sig")))
    }
    release_counts = {}
    fx_missing = []
    vix_differences = []
    checked_vix = 0
    for row in panel["rows"]:
        selected = row["us_previous_dated_observations"]
        fx = selected["fx"]
        if fx["value"] is not None:
            observed = date.fromisoformat(fx["observed_date"])
            friday = observed + timedelta(days=(4 - observed.weekday()) % 7)
            pos = bisect_right(releases, friday)
            release = releases[pos] if pos < len(releases) else None
            # The official calendar supplies an issue date; 16:15 is the published schedule.
            if (release is None or release > friday + timedelta(days=6) or
                    datetime.combine(release, time(16, 15), NY) >= datetime.fromisoformat(fx["decision_at_taipei"])):
                fx_missing.append(row["date"])
            else:
                release_counts[str(release)] = release_counts.get(str(release), 0) + 1
        selected_vix = selected["vix"]
        if selected_vix["value"] is not None:
            checked_vix += 1
            observed = selected_vix["observed_date"]
            if vix.get(observed) != selected_vix["value"]:
                vix_differences.append({"session": row["date"], "observed_date": observed})
    return {
        "h10": {"source": H10, "sha256": digest(h10_raw), "release_issue_dates": release_counts,
                "decisions_matched": sum(release_counts.values()), "unmatched_decisions": fx_missing,
                "scope": "Historical issue date plus announced 16:15 New York schedule; no actual posting-minute attestations."},
        "vix": {"source": VIX, "sha256": digest(vix_raw), "selected_values_checked": checked_vix,
                "differences": vix_differences, "scope": "Official daily closes; no publication timestamps."}
    }


def main():
    parser = ArgumentParser()
    parser.add_argument("--h10-response", type=Path)
    parser.add_argument("--vix-response", type=Path)
    args = parser.parse_args()
    panel_raw, vintage_raw = PANEL_PATH.read_bytes(), VINTAGE_PATH.read_bytes()
    panel, vintages = json.loads(panel_raw), json.loads(vintage_raw)
    scoped = exclude_unused_versions(vintages)
    original = replay_audit(panel, vintages)
    revised = replay_audit(panel, scoped)
    if original != revised or revised["mismatch_count"]:
        raise SystemExit("Exclusion changes the frozen selection replay")
    if any(row["us_previous_dated_observations"][factor]["observed_date"] == EXCLUDED_DATE
           for row in panel["rows"] for factor in EXCLUDED_VALUES):
        raise SystemExit("Excluded observation appears in the panel")
    frozen = json.loads((ROOT / "docs/phase4_frozen_prospective_protocol.json").read_bytes())
    actual = reconstruct(panel["rows"], frozen_distributions(), frozen["post_close_feature_action_lag_taiwan_sessions"])
    published = json.loads((ROOT / "docs/risk_dashboard.json").read_bytes())["taiwan_history"]
    if actual != published:
        raise SystemExit("Published Taiwan scores differ from the frozen reconstruction")
    sources = audit_source_dates(
        panel,
        args.h10_response.read_bytes() if args.h10_response else download(H10),
        args.vix_response.read_bytes() if args.vix_response else download(VIX),
    )
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "panel_sha256": digest(panel_raw), "raw_vintages_sha256": digest(vintage_raw),
        "excluded_versions": [{"factor": factor, "observation_date": EXCLUDED_DATE,
                                "bootstrap_effective_date": EXCLUDED_VINTAGE, "saved_value": value}
                               for factor, value in EXCLUDED_VALUES.items()],
        "excluded_versions_reason": "No value returned in official effective-date interval evidence; user authorized exclusion when unused.",
        "sessions": revised["sessions"], "replay_positions": revised["checks"],
        "replay_mismatches_after_exclusion": revised["mismatch_count"],
        "published_taiwan_score_rows_unchanged": len(actual),
        "valid_taiwan_scores": sum(row["score"] is not None for row in actual),
        "sources": sources,
        "actual_publication_timestamps_verified_for_all_718": False
    }
    out = ROOT / "docs/pit_publication_evidence_scope.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print({key: report[key] for key in ("sessions", "replay_positions", "replay_mismatches_after_exclusion", "valid_taiwan_scores")})
    print("H10", sources["h10"]["decisions_matched"], "VIX differences", len(sources["vix"]["differences"]))


if __name__ == "__main__":
    main()
