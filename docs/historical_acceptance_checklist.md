# Historical data acceptance gate (2023-11 through 2026-10)

Status: **BLOCKED — do not start out-of-sample backtest or alter live thresholds.**

## Evidence at 2026-11-11 12:54 Asia/Taipei
- All 36 target months attempted; 1,448 distinct TWSE metric/date observations; no duplicates.
- Workflow run 42961224769 completed successfully.
- Cross-source gaps: 2023-12-29 cash institutional, 2024-01-24 margin.
- Official TWSE listed-market session calendar has not been joined. A weekday count is **not** an exchange calendar.
- TAIFEX TX foreign futures history has not been imported.

## Ordered acceptance checklist

- [x] Backfill requests attempted for every target month, 2023-11 through 2026-10.
- [x] Regression tests and current provenance audit run successfully.
- [x] Zero duplicate (metric_id, date) records in the current audit.
- [ ] Obtain an authoritative TWSE *listed-market actual trading session* calendar for 2023-11-01 through 2026-10-31. Preserve its source URL, retrieval timestamp, coverage, and any exceptional sessions.
- [ ] Join calendar to each metric separately. Report monthly expected trading sessions, observed valid sessions, missing sessions, unexpected off-calendar dates, and coverage ratio. **Do not** treat rejected HTTP responses as holidays.
- [ ] Repair cash institutional observation for 2023-12-29 and margin observation for 2024-01-24 using date-specific official source data. Confirm response date exactly matches requested date, units/scope, and provenance; never substitute another day's response.
- [ ] Repeat monthly calendar coverage audit; require zero missing official sessions and zero unexpected off-calendar observations for each required TWSE metric (or record a formally reviewed, source-supported exception).
- [ ] Acquire official TAIFEX TX foreign/China institutional futures open-interest history for the same calendar span. Inspect actual CSV headers and definitions before import; validate long OI minus short OI equals net OI and dates are unique.
- [ ] Join TWSE and TAIFEX observations using explicit session-date rules; quantify missing futures dates rather than forward-filling silently.
- [ ] Freeze immutable input snapshot, source metadata, and audit outputs. Re-run regression tests and data-quality gate.
- [ ] Only then execute chronological, leakage-free out-of-sample backtest, with a separate holdout period and documented transaction costs.
- [ ] Review backtest and calibration; changing live risk thresholds requires separate authorization.

## Operational notes
The scheduled backfill workflow currently continues to invoke `scripts.backfill_batch`. After the 36-month queue is exhausted, inspect its behavior before deciding whether to retain, disable, or replace the schedule with incremental daily collection. Avoid overlapping manual and scheduled runs.

## Primary artifacts
- `storage/backfill_progress.json`
- `storage/twse_backfill.json`
- `docs/backfill_audit.json`
- `scripts/audit_backfill.py`
- `scripts/import_taifex.py`
