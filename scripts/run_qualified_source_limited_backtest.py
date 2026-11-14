"""Run the existing fixed-method research backtest under explicitly limited provenance."""
import hashlib,json
from pathlib import Path
from backtest_phase2_research import evaluate, SOURCE
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"docs/qualified_source_limited_backtest.json"
CROSS=ROOT/"docs/taifex_20231113_secondary_crosscheck.json"
GATE=ROOT/"docs/taifex_prebacktest_gate.json"
def main():
 cross=json.loads(CROSS.read_text(encoding="utf-8"))
 gate=json.loads(GATE.read_text(encoding="utf-8"))
 panel=json.loads(SOURCE.read_text(encoding="utf-8"))
 row=next(x for x in panel["rows"] if x["date"]=="2023-11-13")
 expected={"tx_oi_long_contracts":cross["long_open_interest"],"tx_oi_short_contracts":cross["short_open_interest"],"tx_oi_net_contracts":cross["net_open_interest"]}
 assert all(type(row[k]) is int and row[k]==v for k,v in expected.items()),"Secondary crosscheck mismatch"
 assert expected["tx_oi_long_contracts"]-expected["tx_oi_short_contracts"]==expected["tx_oi_net_contracts"]
 assert cross["verification_status"]=="secondary_source_corroborated_not_officially_certified"
 assert cross["official_primary_source_authenticated"] is False
 assert gate["full_model_backtest_authorized"] is False
 assert len(panel["rows"])==718 and panel["formal_backtest_authorized"] is False
 result=evaluate()
 assert result["full_model_backtest_authorized"] is False
 report={"status":"source_limited_research_backtest","label":"有來源限制的研究回測（非正式模型認證）",
         "basis":"existing fixed six-factor phase2 research methodology, 70/30 chronological holdout",
         "sample_dates":[panel["rows"][0]["date"],panel["rows"][-1]["date"]],
         "sample_rows":len(panel["rows"]),"txf_exception":{"date":"2023-11-13","values":expected,
             "verification":"third_party_crosschecked_not_official","source_url":cross["source_url"],
             "crosscheck_sha256":hashlib.sha256(CROSS.read_bytes()).hexdigest()},
         "research_result":result,
         "limitations":["One TXF day is third-party corroborated, not official raw authenticated",
           "Full announcement archive sweep remains unverified",
           "Historical FRED publication/vintage timing remains unverified",
           "This is a fixed-factor risk-event research evaluation, not a transaction-cost-adjusted trading strategy",
           "No live threshold authorization or official full-model validation"],
         "full_model_backtest_authorized":False,"full_model_validated":False,"recommended_live_threshold":None}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("QUALIFIED_BACKTEST",result["status"],result.get("holdout"))
if __name__=="__main__":main()
