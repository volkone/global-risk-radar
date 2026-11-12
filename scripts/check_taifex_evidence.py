"""Fail-closed evidence and calendar gate. Run before any backtest."""
import json
from pathlib import Path

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
full_notice_sweep=e.get("gate",{}).get("full_notice_sweep_verified",False) is True
report={"record_count":len(dates),"annual_source_links_present":source_coverage,"special_source_links_present":special_coverage,"special_date_coverage":len(covered&expected),"calendar_data_consistent":data_consistent,"full_notice_sweep_verified":full_notice_sweep,"independent_taifex_calendar_verified":bool(source_coverage and special_coverage and data_consistent and full_notice_sweep),"full_model_backtest_authorized":False}
(ROOT/"docs/taifex_prebacktest_gate.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
