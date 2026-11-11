# TAIFEX rolling three-year scope (2026-11-11)
User decision: **do not request or purchase older-than-three-year records**.

- Official form reported earliest allowed date: **2023-11-11** (rolling boundary).
- Official form reported latest allowed date: **2026-11-11**.
- Project historical panel cutoff: **2026-10-31**, matching completed TWSE audit.
- Requested TAIFEX TX foreign/China institutional futures open interest: **2023-11-11 through 2026-10-31**.
- Do not request **2023-11-01 through 2023-11-10** and do not infer their values.
- Use official TAIFEX dates actually returned; compare to TWSE sessions on the overlap only.
- Never use a successful HTTP response alone as evidence that historical observations were downloaded.
- The previously tested `futContractsDateExcel` GET/POST request returned HTML, not verified Excel or TX rows. This endpoint is **not confirmed**.
- Actual raw source extraction, independent futures-session calendar, and complete futures audit remain **blocked**.
- If the official rolling cutoff advances before download, derive the new lower bound from the live official form and never request expired dates.

Full-model out-of-sample backtesting and live threshold changes remain blocked pending real TAIFEX observations and independent futures session validation.
