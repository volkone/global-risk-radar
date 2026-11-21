"""Cross-check the publication bundle before uploading it to GitHub Pages."""
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = "storage/phase4_publication_aware_panel.json"


def read(name):
    return json.loads((ROOT / "docs" / f"{name}.json").read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise SystemExit(f"Research bundle validation failed: {message}")


def verify_series(rows, name):
    dates = [datetime.fromisoformat(row["date"].replace("Z", "+00:00")) for row in rows]
    require(all(a < b for a, b in zip(dates, dates[1:])), f"{name}: dates must increase")
    for row in rows:
        score = row["score"]
        require(score is None or (type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 100),
                f"{name}: invalid score for {row['date']}")
        require(isinstance(row["components"], list), f"{name}: missing factors for {row['date']}")
    return sum(row["score"] is not None for row in rows)


def main():
    snapshot, quality = read("data"), read("quality")
    dashboard, scores = read("risk_dashboard"), read("scores")
    calibration, replay = read("calibration"), read("pit_full_replay_audit")
    global_archive, readiness = read("global_history"), read("model_readiness")
    health = read("forward_health")
    digest = hashlib.sha256((ROOT / PANEL).read_bytes()).hexdigest()
    require(snapshot["metrics"] and snapshot["updated_utc"] == quality["snapshot_updated_at"],
            "market quality must refer to the published snapshot")
    watch = snapshot["taiwan_crash_watch"]
    credit = watch.get("credit") or {}
    if credit.get("date"):
        source = read("taiwan_credit_history")["records"][credit["date"]]
        maintenance = snapshot["metrics"]["maint"]
        require(maintenance["date"] == credit["date"] and maintenance["value"] == credit["maintenance_pct"],
                "official maintenance metric and credit panel disagree")
        require(all(credit[key] == value for key, value in source.items()),
                "credit panel and official archive disagree")
    breadth = watch.get("trend_breadth") or {}
    history = read("taiwan_market_breadth")["records"]
    for market, item in breadth.get("markets", {}).items():
        source = history[item["date"]][market]
        for window in ("ma20", "ma60"):
            if window not in item:
                continue
            measure = item[window]
            require(measure == source[window] and 0 <= measure["above"] <= measure["eligible"]
                    <= item["stocks_with_close"] and
                    measure["pct"] == round(100 * measure["above"] / measure["eligible"], 4),
                    f"{market} {window}: invalid breadth observation")
    require(dashboard["generated_at"] == scores["generated_at"] and
            all(dashboard[key] == scores[key] for key in ("global", "taiwan", "formal_model_status")),
            "dashboard and scores disagree")
    require(all(panel_hash == digest for panel_hash in (
        dashboard["source_panel_sha256"], calibration["source_panel_sha256"],
        replay["input_sha256"][PANEL], global_archive["input_sha256"][PANEL])),
        "panel SHA-256 mismatch")
    rows = dashboard["taiwan_history"]
    valid = verify_series(rows, "Taiwan reconstruction")
    require(len(rows) == dashboard["historical_sessions"] == calibration["historical_sessions"] == replay["sessions"],
            "Taiwan historical session count mismatch")
    require(valid == dashboard["valid_historical_scores"] == calibration["valid_historical_scores"],
            "Taiwan valid score count mismatch")
    require(replay["mismatch_count"] == 0, "PIT replay differences detected")
    archive_rows = global_archive["records"]
    require(len(archive_rows) == global_archive["sessions"] and
            verify_series(archive_rows, "Global reconstruction") == global_archive["valid_scores"],
            "global reconstruction count mismatch")
    verify_series(dashboard["global_history"], "Archived global snapshots")
    verify_series(dashboard["prospective_history"], "Prospective predictions")
    require(dashboard["taiwan"]["quality_gate"] == readiness and
            dashboard["formal_model_status"] == readiness["status"], "formal gate mismatch")
    require(readiness["status"] == "PASS" or dashboard["taiwan"]["score"] is None,
            "unapproved formal score")
    require(all(type(health[key]) is int and health[key] >= 0 for key in ("snapshots", "predictions", "outcomes")),
            "invalid forward collection counters")
    print(f"Research bundle PASS: Taiwan {valid}/{len(rows)}, global "
          f"{global_archive['valid_scores']}/{len(archive_rows)}, PIT {replay['checks']} checks, "
          f"formal gate {readiness['status']}")


if __name__ == "__main__":
    main()
