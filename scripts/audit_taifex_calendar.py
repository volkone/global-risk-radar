"""Independent TAIFEX TXF session-date audit; no changes to source observations.
Annual official TAIFEX open/closed market notices are the source of holiday exclusions.
Ad-hoc closures must be independently checked before authorization.
"""
import csv
import datetime as dt
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
START=dt.date(2023,11,11)
END=dt.date(2026,10,31)
SOURCES={
  2023:"https://www.taifex.com.tw/file/taifex/CHINESE/11/attach/%E5%8F%B0%E6%9C%9F%E4%BA%A4%E5%AD%97%E7%AC%AC1110003783%E8%99%9F%E5%87%BD.pdf",
  2024:"https://www.taifex.com.tw/file/taifex/CHINESE/11/attach/%E5%8F%B0%E6%9C%9F%E4%BA%A4%E5%AD%97%E7%AC%AC1120003542%E8%99%9F%E5%87%BD.pdf",
  2025:"https://www.taifex.com.tw/file/taifex/CHINESE/11/attach/%E5%8F%B0%E6%9C%9F%E4%BA%A4%E5%AD%97%E7%AC%AC1140001929%E8%99%9F%E5%87%BD.pdf",
  2026:"https://www.taifex.com.tw/file/taifex/CHINESE/11/attach/%E5%8F%B0%E6%9C%9F%E4%BA%A4%E5%AD%97%E7%AC%AC1140003036%E8%99%9F%E5%87%BD.pdf",
}
# Weekday holidays, including Lunar New Year market closure before/after statutory holidays.
CLOSED={
  2023:[],
  2024:["01-01","02-06","02-07","02-08","02-09","02-12","02-13","02-14","02-28","04-04","04-05","05-01","06-10","09-17","10-10"],
  2025:["09-29","10-24","12-25","01-01","01-23","01-24","01-27","01-28","01-29","01-30","01-31","02-28","04-03","04-04","05-01","05-30","10-06","10-10"],
  2026:["01-01","02-12","02-13","02-16","02-17","02-18","02-19","02-20","02-27","04-03","04-06","05-01","06-19","09-25","09-28","10-09","10-26"],
}
def main():
    records=json.loads((ROOT/"storage/taifex_backfill.json").read_text(encoding="utf-8"))["records"]
    with (ROOT/"storage/official_calendar/trading_days.csv").open(encoding="utf-8-sig",newline="") as f:
        twse={r["date"] for r in csv.DictReader(f) if r["is_trading_day"]=="1"}
    observed={r["date"] for r in records}
    holidays={f"{y}-{d}" for y,days in CLOSED.items() for d in days}
    ad_hoc_closed={"2024-07-24","2024-07-25","2024-10-02","2024-10-03","2024-10-31","2026-07-10","2026-10-23"}
    days=set()
    d=START
    while d<=END:
        if d.weekday()<5 and d.isoformat() not in holidays and d.isoformat() not in ad_hoc_closed:
            days.add(d.isoformat())
        d+=dt.timedelta(days=1)
    result={
      "status":"calendar_dates_reconciled_pending_documentary_audit",
      "window":[START.isoformat(),END.isoformat()],
      "annual_official_sources":SOURCES,
      "observed_count":len(records),
      "annual_calendar_candidate_count":len(days),
      "missing_from_observations":sorted(days-observed),
      "unexpected_observations":sorted(observed-days),
      "twse_reference_only_discrepancies":sorted(days^twse),
      "duplicate_observation_dates":sorted(d for d in observed if sum(r["date"]==d for r in records)>1),
      "independent_taifex_calendar_verified":False,
      "full_model_backtest_authorized":False,
      "note":"Annual notices alone do not prove absence of typhoon or ad-hoc closures. Resolve all exceptions with dated TAIFEX notices before enabling backtest."
    }
    out=ROOT/"docs/taifex_calendar_audit.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("annual_official_sources","note")},ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
