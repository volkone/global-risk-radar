"""Phase 3A-02: versioned, deduplicated risk-indicator observations.

Only verified, dated numeric observations enter history. The SQLite database stays
outside the public GitHub Pages docs directory.
"""
import datetime as dt
import json
import math
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "data.json"
DATABASE = ROOT / "storage" / "history.sqlite"
EXPORT = ROOT / "docs" / "history" / "observations.json"
SCHEMA_VERSION = 1


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def observations(snapshot):
    for metric_id, metric in snapshot.get("metrics", {}).items():
        if not isinstance(metric, dict):
            continue
        candidates = [(metric_id, metric)]
        for source_id, record in metric.get("official_sources", {}).items():
            if isinstance(record, dict):
                candidates.append((metric_id + "." + source_id, record))
        for key, record in candidates:
            if record.get("status") != "ok" or record.get("cache_status") == "stale":
                continue
            date = parse_date(record.get("date"))
            value = record.get("value")
            unit = record.get("unit")
            if not date or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not unit:
                continue
            provider = str(record.get("provider") or metric.get("source") or "unknown")
            scope = str(record.get("scope") or "")
            source_url = str(record.get("source_url") or "")
            yield (key, provider, scope, date, float(value), str(unit), source_url,
                   str(record.get("checked_at") or snapshot.get("updated_utc") or ""))


def run():
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    EXPORT.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS observations (
            metric_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            scope TEXT NOT NULL,
            observation_date TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            source_url TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (metric_id, provider, scope, observation_date)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            scope TEXT NOT NULL,
            observation_date TEXT NOT NULL,
            old_value REAL NOT NULL,
            new_value REAL NOT NULL,
            changed_at TEXT NOT NULL
        )""")
        changed_at = dt.datetime.now(dt.timezone.utc).isoformat()
        for row in observations(snapshot):
            key = row[:4]
            old = db.execute(
                "SELECT value, unit FROM observations WHERE metric_id=? AND provider=? AND scope=? AND observation_date=?",
                key,
            ).fetchone()
            if old is not None and (old[0] != row[4] or old[1] != row[5]):
                db.execute(
                    "INSERT INTO revisions(metric_id,provider,scope,observation_date,old_value,new_value,changed_at) VALUES (?,?,?,?,?,?,?)",
                    (*key, old[0], row[4], changed_at),
                )
            db.execute("""INSERT INTO observations
                (metric_id,provider,scope,observation_date,value,unit,source_url,fetched_at,schema_version)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(metric_id,provider,scope,observation_date) DO UPDATE SET
                value=excluded.value,unit=excluded.unit,source_url=excluded.source_url,
                fetched_at=excluded.fetched_at""", (*row, SCHEMA_VERSION))
        records = db.execute("""SELECT metric_id,provider,scope,observation_date,value,unit,source_url
            FROM observations ORDER BY observation_date DESC,metric_id LIMIT 10000""").fetchall()
        revisions = db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0]
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError("history_integrity_check_failed: " + integrity)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": changed_at,
        "record_count": len(records),
        "revision_count": revisions,
        "observations": [
            dict(zip(("metric_id","provider","scope","observation_date","value","unit","source_url"), row))
            for row in records
        ],
    }
    EXPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("History:", len(records), "records;", revisions, "revisions")


if __name__ == "__main__":
    run()
