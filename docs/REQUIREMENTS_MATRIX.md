# Mapping to TBO's Agentic Real-Time DAST problem statement

From the user-provided TBO Security Hackathon 2026 participant pack (5 pages).

| TBO expectation | Implemented in this MVP | Evidence/next step |
|---|---|---|
| Detect deployment changes | Yes, synthetic | `POST /api/agent/start` or `/api/demo/deploy` records version and changed routes |
| Discover API without an OpenAPI document | Partial, controlled fixtures | Old JS + gateway observations + SQL traffic; real traffic/browser crawl is later integration |
| Find active, zombie, shadow APIs | Yes, synthetic | `services/inventory.py` + API landscape UI |
| Plan targeted tests | Yes | ML priority + route-aware approved invariant registry |
| Execute safely | Yes | Exact path allowlist, test accounts, in-process ASGI only, 40-request cap, kill switch |
| Verify each finding | Yes | SQL state oracle + fresh universe reproduction |
| Business-context severity | Yes, preset case severity | Explicit owner and business-risk descriptions; real calibration later |
| Report fix-ready issue | Yes | Finding + local ticket + JSON export |
| Retest after developer fix | Yes | Secure deployment + specific finding retest |
| Human-in-the-loop | Yes | Human-review ticket; no external escalation |
| Report detection latency, false positives | Partly | Scan event timestamps, safe-run tests; true benchmark requires labelled organizer staging |
| Find undocumented live TBO bugs | Not yet | Requires approved staging app and scoped adaptation |
| No real data and no destruction | Yes by construction | Fixture-only data; local simulator; no real transactions |

**Judging categories from the user-supplied security brief:** Valid findings/severity 30%; precision 20%; safety 20%; post-change speed 10%; report quality 10%; API inventory 10%. The project is scoped around reproducible safe findings instead of volume-based alert generation.
