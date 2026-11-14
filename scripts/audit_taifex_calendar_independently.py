"""Independent calendar evidence gate, separate from announcement archive completeness."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"docs/taifex_calendar_evidence.json"
ANNOUNCEMENTS=ROOT/"docs/taifex_announcement_three_year_audit.json"
OUT=ROOT/"docs/taifex_calendar_independent_audit.json"
VALID={"verified_primary","previously_verified_primary","verified_direct_page"}
def build(evidence,announcements):
    specials=evidence.get("special_dates",[])
    listings={tuple(x["dates"]):x for x in announcements.get("special_date_reconciliation",[])}
    rows=[]
    for entry in specials:
        key=tuple(entry["dates"])
        listing=listings.get(key,{})
        url=entry.get("official_url")
        status=entry.get("status")
        rows.append({"dates":list(key),"reason":entry.get("reason"),"official_url":url,
                     "official_evidence_recorded":bool(url and status in VALID),
                     "source_status":status,"listed_in_announcement_feed":bool(listing.get("matched")),
                     "listing_match_count":len(listing.get("matching_archive_records",[])),
                     "source_independently_retrieved_this_run":False})
    annual=evidence.get("annual_calendar",{}).get("sources",[])
    annual_rows=[{"year":s.get("year"),"official_url":s.get("official_url"),"source_status":s.get("status"),
                  "source_recorded":bool(s.get("official_url") and s.get("status")=="verified_pdf_text")} for s in annual]
    coverage=len(rows)>0 and all(x["official_evidence_recorded"] for x in rows)
    return {"schema_version":1,"method":"Separate preexisting primary-evidence ledger from archive-list matching; no live source reauthentication",
            "special_date_groups":rows,"special_date_group_count":len(rows),
            "special_groups_with_recorded_official_evidence":sum(x["official_evidence_recorded"] for x in rows),
            "special_groups_matched_in_announcement_feed":sum(x["listed_in_announcement_feed"] for x in rows),
            "annual_calendar_sources":annual_rows,
            "annual_calendar_sources_recorded":sum(x["source_recorded"] for x in annual_rows),
            "recorded_special_evidence_coverage":coverage,
            "archive_exhaustiveness_verified":False,
            "independent_calendar_verified":False,
            "full_model_backtest_authorized":False,
            "remaining_requirements":["Reauthenticate official source documents independently","Verify archive coverage by actual navigation or authoritative totals","Verify the single TXF source or explicitly adopt a separate lower-assurance backtest policy"]}
def main():
    evidence=json.loads(EVIDENCE.read_text(encoding="utf-8"))
    announcements=json.loads(ANNOUNCEMENTS.read_text(encoding="utf-8"))
    report=build(evidence,announcements)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    assert report["special_date_group_count"]==len(evidence["special_dates"])
    assert not report["full_model_backtest_authorized"]
    print("Calendar evidence groups:",report["special_groups_with_recorded_official_evidence"],"/",report["special_date_group_count"])
    print("Listing matches:",report["special_groups_matched_in_announcement_feed"],"/",report["special_date_group_count"])
if __name__=="__main__":main()
