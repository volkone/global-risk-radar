"""Fail-closed evidence and calendar gate. Run before any backtest."""
import hashlib
import json
import sys
from pathlib import Path

from dashboard_scores import reconstruct
from phase5_forward_ledger import frozen_distributions
from verify_taifex_sources import fingerprint

ROOT=Path(__file__).resolve().parents[1]
e=json.loads((ROOT/"docs/taifex_calendar_evidence.json").read_text(encoding="utf-8"))
a=json.loads((ROOT/"docs/taifex_calendar_audit.json").read_text(encoding="utf-8"))
r=json.loads((ROOT/"storage/taifex_backfill.json").read_text(encoding="utf-8"))["records"]
dates=[x["date"] for x in r]
annual=e.get("annual_calendar",{}).get("sources",[])
special=e.get("special_dates",[])
expected={"2024-07-24","2024-07-25","2024-10-02","2024-10-03","2024-10-31","2025-09-29","2025-10-24","2025-12-25","2026-07-10","2026-10-23"}
covered={d for item in special for d in item.get("dates",[])}
source_coverage=len(annual)==4 and all(x.get("official_url","").startswith("https://www.taifex.com.tw/") for x in annual)
special_coverage=expected==covered and all(x.get("official_url","").startswith("https://www.taifex.com.tw/") for x in special)
data_consistent=(len(dates)==718 and len(set(dates))==718 and len(set(dates)&expected)==0 and not a.get("missing_from_observations") and not a.get("unexpected_observations") and not a.get("duplicate_observation_dates"))
# User-authorized exception applies to this session only.
excluded = "2023-11-13"
scope = [record for record in r if record["date"] != excluded]
archive = json.loads((ROOT / "docs/taifex_hisnews_coverage.json").read_text(encoding="utf-8"))
full_notice_sweep = (
    archive["public_archive_coverage_verified"] is True
    and archive["window"] == a["window"]
    and archive["months_matched"] == archive["months_total"] == 36
    and all(partition["matched"] for partition in archive["partitions"])
    and len(archive["closure_positive_controls"]) == 5
    and all(archive["closure_positive_controls"].values())
)
results = json.loads((ROOT / "docs/taifex_source_verification.json").read_text(encoding="utf-8"))["results"]
def source_verified(record):
    evidence = results.get(record["date"], {})
    return (
        evidence.get("status") == "pass"
        and evidence.get("record_fingerprint") == fingerprint(record)
        and bool(record.get("source_sha256"))
        and evidence.get("actual_sha256") == evidence.get("expected_sha256") == record["source_sha256"]
    )

unverified = [record["date"] for record in scope if not source_verified(record)]
documents_verified = (
    all(item.get("status") == "verified_pdf_text" for item in annual)
    and all(item.get("status") in {"verified_primary", "previously_verified_primary", "verified_direct_page"}
            for item in special)
)
primary_evidence_complete = len(scope) == 717 and not unverified and documents_verified

panel_path = ROOT / "storage/phase4_publication_aware_panel.json"
panel_bytes = panel_path.read_bytes()
rows = json.loads(panel_bytes)["rows"]
frozen = json.loads((ROOT / "docs/phase4_frozen_prospective_protocol.json").read_text(encoding="utf-8"))
lag = frozen["post_close_feature_action_lag_taiwan_sessions"]
threshold = frozen["alert_score_threshold_frozen_before_future_outcomes"]
distribution = frozen_distributions()
baseline = {row["date"]: row["score"] for row in reconstruct(rows, distribution, lag)}
scoped_scores = reconstruct([row for row in rows if row["date"] != excluded], distribution, lag)
changed = [{"date": row["date"], "original_score": baseline[row["date"]], "scoped_score": row["score"]}
           for row in scoped_scores if row["score"] != baseline[row["date"]]]
threshold_changes = [
    row["date"] for row in changed
    if (row["original_score"] is not None and row["original_score"] >= threshold)
    != (row["scoped_score"] is not None and row["scoped_score"] >= threshold)
]

url_check_path=ROOT/"docs/taifex_evidence_url_check.json"
url_report=json.loads(url_check_path.read_text(encoding="utf-8")) if url_check_path.exists() else {}
urls_ok=bool(url_report.get("unique_urls")) and url_report.get("failed")==0 and url_report.get("ok")==url_report.get("unique_urls")
blockers=[]
if not source_coverage:blockers.append("annual_source_links_missing")
if not special_coverage:blockers.append("special_date_evidence_missing")
if not data_consistent:blockers.append("calendar_data_mismatch")
if not urls_ok:blockers.append("official_evidence_urls_failed_or_not_checked")
if not full_notice_sweep:blockers.append("full_notice_sweep_not_verified")
if not primary_evidence_complete:blockers.append("primary_evidence_not_complete")
if set(baseline) != set(dates) or len(scoped_scores) != 717:
    blockers.append("scope_does_not_match_frozen_panel")
report={"blockers":blockers,"evidence_urls_accessible":urls_ok,"record_count":len(dates),"annual_source_links_present":source_coverage,"special_source_links_present":special_coverage,"special_date_coverage":len(covered&expected),"calendar_data_consistent":data_consistent,"full_notice_sweep_verified":full_notice_sweep,"primary_evidence_complete":primary_evidence_complete,"independent_taifex_calendar_verified":bool(not blockers),"full_model_backtest_authorized":False}
report.update(
    certification_scope="Official daily TXF records and publicly reconciled calendar, excluding 2023-11-13",
    excluded_dates=[excluded],
    source_panel_sha256=hashlib.sha256(panel_bytes).hexdigest(),
    raw_source_values_verified=len(scope) - len(unverified),
    raw_source_values_expected=len(scope),
    raw_source_unverified_dates=unverified,
    official_historical_data_request_required=False,
    official_historical_extract_acquired=False,
    official_archive_audit={"evidence": "docs/taifex_hisnews_coverage.json",
                            "notice_count": archive["notice_count"],
                            "months_verified": archive["months_matched"]},
    exclusion_replay={"valid_scores_original": sum(value is not None for value in baseline.values()),
                      "valid_scores_in_scope": sum(row["score"] is not None for row in scoped_scores),
                      "changed_scores_on_retained_sessions": changed,
                      "changed_research_threshold_dates": threshold_changes,
                      "uses_frozen_reference_distribution": True},
)
(ROOT/"docs/taifex_prebacktest_gate.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
if not report["independent_taifex_calendar_verified"]:
    print("BLOCKED: "+", ".join(blockers),file=sys.stderr)
    sys.exit(2)
