"""Independently compare the saved ALFRED change feed to effective-date intervals."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from audit_publication_evidence_scope import exclude_unused_versions

ROOT = Path(__file__).resolve().parents[1]
VINTAGES = ROOT / "storage/phase3_fred_pit_vintages.json"
PANEL = ROOT / "storage/phase4_publication_aware_panel.json"
URL = "https://api.stlouisfed.org/fred/series/observations"
DAY = timedelta(days=1)


def value(raw):
    return None if raw in (None, ".") else Decimal(str(raw))


def download(series, start, end, earliest, cache, api_key):
    offset, count = 0, None
    intervals = defaultdict(list)
    hashes = []
    while count is None or offset < count:
        params = urlencode(dict(api_key=api_key, series_id=series, file_type="json",
                               output_type=1, realtime_start=start, realtime_end=end,
                               observation_start=earliest, observation_end=end, limit=10000, offset=offset))
        with urlopen(URL + "?" + params, timeout=45) as response:
            raw = response.read()
        obj = json.loads(raw)
        records = obj["observations"]
        if (obj["output_type"] != 1 or obj["offset"] != offset or
                obj["realtime_start"] != str(start) or obj["realtime_end"] != str(end) or
                (count is not None and count != obj["count"]) or not records):
            raise ValueError("inconsistent ALFRED response or pagination")
        count = obj["count"]
        hashes.append(hashlib.sha256(raw).hexdigest())
        (cache / f"{series}-{offset}.json.gz").write_bytes(gzip.compress(raw, mtime=0))
        for row in records:
            first = max(start, date.fromisoformat(row["realtime_start"]))
            last = min(end, date.fromisoformat(row["realtime_end"]))
            if first <= last:
                intervals[row["date"]].append((first, last, value(row["value"])))
        offset += len(records)
    if offset != count:
        raise ValueError("ALFRED returned more records than reported")
    return intervals, count, hashes


def compare(archive, stored, start, end):
    changes = defaultdict(dict)
    for row in stored["bootstrap"]:
        changes[row["date"]][start] = value(row["value"])
    for row in stored["changes"]:
        if row["observed_date"] <= str(end):
            changes[row["observed_date"]][date.fromisoformat(row["vintage_date"])] = value(row["value"])
    differences, checked = [], 0
    for observed in sorted(archive.keys() | changes.keys()):
        intervals = sorted(archive.get(observed, []))
        if any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
            raise ValueError("ALFRED interval overlap for " + observed)
        expected = {first: val for first, _, val in intervals}
        for _, last, _ in intervals:
            if last < end:
                expected.setdefault(last + DAY, None)
        stored_changes = changes.get(observed, {})
        actual_value = expected_value = None
        for boundary in sorted(expected.keys() | stored_changes.keys()):
            actual_value = stored_changes.get(boundary, actual_value)
            expected_value = expected.get(boundary, expected_value)
            checked += 1
            if actual_value != expected_value:
                differences.append({"observation_date": observed, "effective_date": str(boundary),
                                    "stored": str(actual_value), "official": str(expected_value)})
    return checked, differences


def compare_selected_panel_values(panel, factor, archive):
    checked = missing = 0
    differences = []
    for row in panel["rows"]:
        field = row["us_previous_dated_observations"][factor]
        if field["value"] is None:
            missing += 1
            continue
        checked += 1
        day = date.fromisoformat(field["asof_us_calendar_date"])
        values = [val for first, last, val in archive.get(field["observed_date"], [])
                  if first <= day <= last]
        if values != [value(field["value"])]:
            differences.append({"decision_date": row["date"], "observation_date": field["observed_date"],
                                "asof_date": str(day)})
    return checked, missing, differences


def main():
    api_key = os.environ["FRED_API_KEY"].strip()
    if not api_key:
        raise SystemExit("FRED_API_KEY is empty")
    cache = ROOT / "alfred_interval_evidence"
    cache.mkdir(exist_ok=True)
    raw = VINTAGES.read_bytes()
    vintages = json.loads(raw)
    end = date.fromisoformat(vintages["window"][1])
    panel = json.loads(PANEL.read_bytes())
    scoped = exclude_unused_versions(vintages)
    scope_path = ROOT / "docs/pit_publication_evidence_scope.json"
    scope = json.loads(scope_path.read_bytes())
    if (scope["raw_vintages_sha256"] != hashlib.sha256(raw).hexdigest() or
            scope["panel_sha256"] != hashlib.sha256(PANEL.read_bytes()).hexdigest() or
            scope["replay_mismatches_after_exclusion"] != 0):
        raise SystemExit("Exclusion evidence does not match the frozen archive and panel")
    report = {}
    for factor, stored in vintages["series"].items():
        start = date.fromisoformat(stored["bootstrap_date"])
        earliest = min([r["date"] for r in stored["bootstrap"]] +
                       [r["observed_date"] for r in stored["changes"]])
        series = stored["series_id"]
        try:
            archive, count, hashes = download(series, start, end, earliest, cache, api_key)
            checked, differences = compare(archive, stored, start, end)
            _, scoped_differences = compare(archive, scoped["series"][factor], start, end)
            used, missing, panel_differences = compare_selected_panel_values(panel, factor, archive)
            report[factor] = {"series": series, "start": str(start), "end": str(end),
                              "observation_start": earliest, "response_rows": count,
                              "boundaries_checked": checked, "differences": len(differences),
                              "differences_after_exclusion": len(scoped_differences),
                              "examples": differences[:20], "response_sha256": hashes,
                              "panel_values_checked": used, "panel_missing_values": missing,
                              "panel_value_differences": panel_differences,
                              "status": "matched" if not differences and not panel_differences else "mismatch"}
            if differences:
                (cache / f"{series}-differences.json").write_text(json.dumps(differences, indent=2))
        except (OSError, ValueError, KeyError, TypeError) as error:
            report[factor] = {"series": series, "status": "failed", "error_type": type(error).__name__}
        print(f"{series}: {report[factor]['status']}", flush=True)
    passed = len(report) == 6 and all(item["status"] == "matched" for item in report.values())
    scope_passed = len(report) == 6 and all(
        x.get("differences_after_exclusion") == 0 and x.get("panel_value_differences") == []
        for x in report.values())
    output = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "source": URL, "source_vintage_sha256": hashlib.sha256(raw).hexdigest(),
              "source_panel_sha256": hashlib.sha256(PANEL.read_bytes()).hexdigest(),
              "series": report, "effective_date_intervals_verified": passed,
              "panel_nonmissing_values_verified": len(report) == 6 and all(
                  entry.get("panel_value_differences") == [] for entry in report.values()),
              "effective_date_intervals_verified_after_scoped_exclusion": scope_passed,
              "exclusion_evidence": "docs/pit_publication_evidence_scope.json",
              "intraday_publication_timestamps_verified": False}
    (ROOT / "docs/alfred_vintage_interval_verification.json").write_text(json.dumps(output, indent=2) + "\n")
    return 0 if scope_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
