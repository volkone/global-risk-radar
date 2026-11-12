"""Compare year-scoped notice discovery with primary-evidence closure dates.
This is a discovery diagnostic, not a completeness certificate.
"""
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT=Path(__file__).resolve().parents[1]
scan=json.loads((ROOT/"docs/taifex_notice_archive_scan.json").read_text(encoding="utf-8"))
evidence=json.loads((ROOT/"docs/taifex_calendar_evidence.json").read_text(encoding="utf-8"))
rows=[]
for part in scan["partitions"]:
    year=part["year"]
    candidates=part.get("candidates",[])
    ids=[]
    for item in candidates:
        u=urlparse(item["url"])
        ids.extend(parse_qs(u.query).get("idx",[]))
    rows.append({"year":year,"http_status":part.get("http_status"),"selected_year":part.get("selected_year"),"candidate_count":len(candidates),"all_official_notice_link_count":part.get("official_notice_link_count"),"announcement_page_controls":part.get("announcement_page_controls",[]),"candidate_notice_ids":ids,"pagination_exhaustiveness_verified":False,"limitations":"The selected-year response may be truncated or use server-side limits. No announcement-specific page control was discovered; listing completeness remains unproven."})
known=[]
for entry in evidence.get("special_dates",[]):
    url=entry.get("official_url","")
    for date in entry.get("dates",[]):
        if "2023-11-11"<=date<="2026-10-31":
            evidence_ids=set(parse_qs(urlparse(url).query).get("idx",[]))
            matches=[p["year"] for p in scan["partitions"] if any(x["url"]==url or (evidence_ids and evidence_ids.intersection(parse_qs(urlparse(x["url"]).query).get("idx",[]))) for x in p.get("official_notice_links",p.get("candidates",[])))]
            known.append({"date":date,"evidence_url":url,"found_in_candidate_listing":bool(matches),"found_in_all_official_links":bool(matches),"listing_years":matches,"matching_rule":"exact_url_or_official_notice_idx_against_all_official_links","warning":"Listing absence does not invalidate direct primary evidence"})
assert known, "Expected known special closure dates from evidence ledger"
report={"window":scan["window"],"year_summary":rows,"known_special_dates":known,"known_dates_total":len(known),"known_dates_in_listing":sum(x["found_in_candidate_listing"] for x in known),"known_dates_in_all_official_links":sum(x["found_in_all_official_links"] for x in known),"year_listing_completeness_verified":False,"full_notice_sweep_verified":False,"primary_evidence_complete":False,"independent_taifex_calendar_verified":False,"full_model_backtest_authorized":False,"next_required":"Verify whether each year listing is exhaustive using total notice counts or documented archive paging; reconcile known notices via direct evidence independently of keyword matches."}
out=ROOT/"docs/taifex_notice_coverage_audit.json"
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"Year-scoped candidates: {sum(r['candidate_count'] for r in rows)}; known closure dates surfaced in listings: {report['known_dates_in_listing']}/{report['known_dates_total']}; exhaustive coverage unverified")
