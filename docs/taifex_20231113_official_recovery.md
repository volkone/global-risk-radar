# TAIFEX TXF 2023-11-13 — official source recovery

Status: **blocked pending official source delivery**. Do not change `docs/taifex_prebacktest_gate.json` or authorize a full backtest based on provisional values.

## Requested official extract
- Trading date: **2023-11-13**
- Product: **臺股期貨 TX / TXF** (not mini futures, options, or an all-product aggregate)
- Investor classification: **外資及陸資** / foreign and mainland investors, consistent with the existing 718-day series
- Metrics: **未平倉多方口數、未平倉空方口數、多空淨額口數**
- Prefer a one-day historical extract. If unavailable, order **2023-11** from official E-Data Shop.
- Request the source's data schema, delivery timestamp, and original unmodified export.

## Official channels
- https://www.taifex.com.tw/cht/3/futContractsDateView — three-year query limit stated by exchange.
- https://edatashop.taifex.com.tw/zh/product/detail/40283ab78906834a018906bec6390000 — futures institutional data with OI; monthly product.
- https://www.taifex.com.tw/cht/3/hisAppForm — historical data application.

## Acceptance
1. Preserve the original unmodified official source file and SHA-256.
2. Confirm date, TX product, investor classification, units, and whether open interest includes all contract months.
3. Independently verify long-short=net and compare provisional 38,773 / 35,641 / +3,132; discrepancies must be reported, not silently overwritten.
4. Run `scripts/verify_taifex_20231113_official.py` on a CSV exported directly from the official file, passing explicit column mappings and source URL. The script creates a **candidate** evidence report, not a certification.
5. Independently inspect the official original and source provenance before marking the record verified and recomputing the PIT and calendar gates.

No purchase or application has been submitted automatically.
