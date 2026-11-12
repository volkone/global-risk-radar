"""Phase 2: bounded acquisition of historical TAIEX close and US risk series.
TWSE FMTQIK month tables provide the *price index*, not a total-return index.
FRED FX series DEXTAUS is a New York noon rate, not a Taiwan exchange close.
Do not change the live dashboard, official TX OI records, or any backtest gates.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "2023-11-11", "2026-10-31"
PRICE = ROOT / "storage/historical_taiex_close.json"
FACTORS = ROOT / "storage/historical_fred_factors.json"
REPORT = ROOT / "docs/phase2_historical_collection.json"
CALENDAR = ROOT / "storage/official_calendar/trading_days.csv"
MANIFEST = ROOT / "storage/official_calendar/source_manifest.json"
FRED_SERIES = {
    "fx": "DEXTAUS", "hy": "BAMLH0A0HYM2", "ig": "BAMLC0A0CM",
    "vix": "VIXCLS", "us10y": "DGS10", "nfci": "NFCI"
}
LIMIT_RETRIES = 2
DELAY = 1.5

def atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)

def get(url):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; historic risk research)",
               "Accept": "application/json,text/csv,*/*"}
    for attempt in range(LIMIT_RETRIES + 1):
        time.sleep(DELAY)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status != 200:
                    raise ValueError("HTTP status " + str(response.status))
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError("response_exceeds_4mb")
            return raw
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            if attempt == LIMIT_RETRIES:
                raise
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (400, 401, 403, 404):
                raise
            time.sleep(3 * (attempt + 1))
    raise AssertionError("unreachable")

def month_expected():
    with CALENDAR.open(encoding="utf-8-sig", newline="") as f:
        actual = [r["date"] for r in csv.DictReader(f) if r["is_trading_day"] == "1"]
    result = {}
    for day in actual:
        result.setdefault(day[:7], set()).add(day)
    return result

def roc_date(raw):
    parts = str(raw).strip().replace("-", "/").split("/")
    if len(parts) != 3:
        raise ValueError("unknown_date_format")
    year, mo, day = (int(x) for x in parts)
    if year < 1911:
        year += 1911
    return dt.date(year, mo, day).isoformat()

def number(raw):
    v = float(str(raw).replace(",", "").strip())
    if not 1000 < v < 100000:
        raise ValueError("index_value_out_of_bounds")
    return round(v, 2)

def parse_month(raw, month, expected):
    obj = json.loads(raw.decode("utf-8-sig"))
    fields = obj.get("fields")
    rows = obj.get("data")
    if not isinstance(fields, list) or not isinstance(rows, list):
        raise ValueError("invalid_FMTQIK_structure")
    date_col = next((i for i, name in enumerate(fields) if str(name).strip() == "日期"), None)
    index_col = next((i for i, name in enumerate(fields) if "發行量加權股價指數" in str(name)), None)
    if date_col is None or index_col is None:
        raise ValueError("TWSE_index_or_date_field_missing:" + repr(fields)[:240])
    observations = {}
    for row in rows:
        if not isinstance(row, list) or len(row) <= max(date_col, index_col):
            raise ValueError("FMTQIK_row_schema_invalid")
        date = roc_date(row[date_col])
        if not date.startswith(month):
            raise ValueError("FMTQIK_month_mismatch:" + date)
        if date in observations:
            raise ValueError("FMTQIK_duplicate_date:" + date)
        observations[date] = number(row[index_col])
    if set(observations) != expected:
        raise ValueError("FMTQIK_session_mismatch missing=" + str(len(expected - set(observations))) +
                         " extra=" + str(len(set(observations) - expected)))
    return observations

def collect_twse():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["months"]
    expected = month_expected()
    existing = json.loads(PRICE.read_text(encoding="utf-8")) if PRICE.exists() else {"records": []}
    bydate = {r["date"]: r for r in existing.get("records", []) if START <= r["date"] <= END}
    audit = {}
    for month, meta in sorted(manifest.items()):
        if month < START[:7] or month > END[:7]:
            continue
        needed = expected.get(month, set())
        needed = {d for d in needed if START <= d <= END}
        previous = {d for d in bydate if d.startswith(month)}
        if previous == needed and all("source_sha256" in bydate[d] and
                                     bydate[d].get("metric_id") == "taiex.close" for d in previous):
            audit[month] = {"status": "cached_verified_schema", "rows": len(previous)}
            continue
        url = meta["source_url"]
        if not url.startswith("https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?"):
            raise ValueError("untrusted_TWSE_manifest_url")
        try:
            raw = get(url)
            all_needed = expected.get(month, set())
            obs = parse_month(raw, month, all_needed)
            sha = hashlib.sha256(raw).hexdigest()
            for date in needed:
                bydate[date] = {"metric_id": "taiex.close", "date": date, "value": obs[date],
                                "unit": "index_points", "provider": "TWSE",
                                "price_type": "unadjusted_TAIEX_close",
                                "source_url": url, "source_sha256": sha}
            audit[month] = {"status": "pass", "rows": len(needed),
                            "source_rows": len(obs), "sha256": sha}
            atomic(PRICE, {"schema_version": 1, "window": [START, END], "records":
                           [bydate[d] for d in sorted(bydate)], "source": "TWSE FMTQIK monthly index levels"})
            print("TWSE_MONTH", month, len(needed), flush=True)
        except Exception as exc:
            audit[month] = {"status": "blocked", "error": type(exc).__name__ + ":" + str(exc)[:250]}
            print("TWSE_MONTH_FAILED", month, audit[month]["error"], flush=True)
    if not PRICE.exists():
        atomic(PRICE, {"schema_version": 1, "window": [START, END],
                       "records": [], "source": "TWSE FMTQIK monthly index levels"})
    expected_window = {d for dates in expected.values() for d in dates if START <= d <= END}
    return audit, len(set(bydate) & expected_window), sorted(expected_window - set(bydate))

def parse_fred(raw, series, source_method):
    if source_method == "fred_api":
        obj = json.loads(raw.decode("utf-8-sig"))
        if "error_code" in obj:
            raise ValueError("fred_api_error_" + str(obj["error_code"]))
        rows = [(x.get("date"), x.get("value")) for x in obj.get("observations", [])]
    else:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if not reader.fieldnames or series not in reader.fieldnames:
            raise ValueError("FRED_CSV_header_missing:" + str(reader.fieldnames))
        date_col = "DATE" if "DATE" in reader.fieldnames else "observation_date"
        if date_col not in reader.fieldnames:
            raise ValueError("FRED_CSV_date_header_missing")
        rows = [(x.get(date_col), x.get(series)) for x in reader]
    values = {}
    for date, v in rows:
        if not date or not START <= date <= END or v in ("", ".", None):
            continue
        dt.date.fromisoformat(date)
        value = float(v)
        if value != value or abs(value) > 100000:
            raise ValueError("FRED_nonfinite_or_out_of_bounds")
        if date in values:
            raise ValueError("FRED_duplicate_observation_date")
        values[date] = value
    return [{"date": d, "value": values[d]} for d in sorted(values)]

def collect_fred():
    existing = json.loads(FACTORS.read_text(encoding="utf-8")) if FACTORS.exists() else {}
    stored = existing.get("series", {})
    audit = {}
    secret = os.getenv("FRED_API_KEY", "").strip()
    for name, series_id in FRED_SERIES.items():
        previous = stored.get(name, {})
        if previous.get("series_id") == series_id and len(previous.get("history", [])) >= (
                130 if name == "nfci" else 500):
            audit[name] = {"status": "cached", "observations": len(previous["history"])}
            continue
        params = {"series_id": series_id, "observation_start": START, "observation_end": END,
                  "file_type": "json"}
        if secret:
            params["api_key"] = secret
            url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(params)
            public_url = "https://fred.stlouisfed.org/series/" + series_id
            method = "fred_api"
        else:
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + urllib.parse.urlencode(
                {"id": series_id, "cosd": START, "coed": END})
            public_url = url
            method = "fred_graph_csv"
        try:
            raw = get(url)
            rows = parse_fred(raw, series_id, method)
            minimum = 130 if name == "nfci" else 500
            if len(rows) < minimum:
                raise ValueError("too_few_FRED_observations:" + str(len(rows)))
            stored[name] = {"series_id": series_id, "history": rows,
                            "source_url": public_url, "source_method": method,
                            "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                            "response_sha256": hashlib.sha256(raw).hexdigest(),
                            "historical_vintage_certified": False}
            atomic(FACTORS, {"schema_version": 1, "window": [START, END],
                             "series": stored, "publication_lags_not_verified": True})
            audit[name] = {"status": "pass", "observations": len(rows),
                           "first": rows[0]["date"], "last": rows[-1]["date"],
                           "method": method}
            print("FRED_SERIES", name, len(rows), flush=True)
        except Exception as exc:
            audit[name] = {"status": "blocked",
                           "error": type(exc).__name__ + ":" + str(exc)[:250]}
            print("FRED_FAILED", name, audit[name]["error"], flush=True)
    if not FACTORS.exists():
        atomic(FACTORS, {"schema_version": 1, "window": [START, END],
                         "series": stored, "publication_lags_not_verified": True})
    return audit

def main():
    twse_audit, covered, missing = collect_twse()
    fred_audit = collect_fred()
    report = {"phase": 2, "status": "data_collection_pass" if not missing and
              all(x.get("status") in ("pass", "cached") for x in fred_audit.values())
              else "partial_needs_followup",
              "window": [START, END], "twse": {"months": twse_audit,
              "matched_target_sessions": covered, "missing_target_sessions": missing},
              "fred": fred_audit,
              "source_notes": {
                  "taiex": "TWSE price-only index, dividends not reinvested; FMTQIK monthly rows must equal official TWSE session dates.",
                  "fx": "DEXTAUS is Federal Reserve NY noon USD/TWD rate; do NOT join same calendar day to Taipei market close without checking timezone.",
                  "crossmarket": "Missing US days/weekend/weekly observations are not Taiwan data errors. Use lagged as-of align and point-in-time availability audit.",
                  "history_vintage": "FRED present-day history has NOT been independently validated for revisions or as-of release timing."
              },
              "full_model_backtest_authorized": False,
              "live_threshold_changes_authorized": False,
              "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    atomic(REPORT, report)
    print("PHASE2_COLLECT", report["status"], "TWSE", covered, "of", covered + len(missing),
          "FRED", {k: v["status"] for k, v in fred_audit.items()}, flush=True)

if __name__ == "__main__":
    main()
