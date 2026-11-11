# Historical acceptance status (updated 2026-11-11)

## TWSE listed market: PASS (limited to automated data-quality controls)

- Period: 2023-11-01 through 2026-10-31; 36 months.
- Independent official actual-session source: TWSE monthly FMTQIK.
- 726 official listed-market sessions; 726/726 margin and 726/726 institutional net cash; no missing or off-session dates.
- Final provenance/value/duplicate checks: PASS; 1,452 unique observations.
- Evidence: `docs/calendar_coverage_audit.json`, `docs/twse_final_quality_gate.json`, `storage/official_calendar/source_manifest.json`.
- Input SHA-256 fingerprints are recorded in the final quality report.
- Automated checks do **not** establish that every numeric value was manually reconciled against an independently retrieved official source.

## TAIFEX and full model: BLOCKED

- TX foreign/China investor futures open interest 2023-11 through 2026-10 not imported.
- Existing `scripts/import_taifex.py` is a strict **offline** importer with a proposed schema; do not treat the unconfirmed headers as official.
- Next: obtain genuine TAIFEX historical export, inspect actual headers and product/investor definitions, normalize long/short/net contracts, verify identity and unique dates, compare against futures trading sessions.
- No invented historical observations, no forward fill of missing futures dates.
- Full multi-factor out-of-sample backtest and live risk threshold changes remain unauthorized until all data gates pass.

## Sequence
1. Verify official TAIFEX TX futures data export schema and retrieve dated historical source files.
2. Import and audit historical foreign TX open interest, including exceptional futures sessions.
3. Freeze joined TWSE/TAIFEX source snapshots and validate availability dates.
4. Execute chronological holdout and documented-cost backtest only after the complete input panel passes.
5. Require separate authorization before changing live risk weights or thresholds.
