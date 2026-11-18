# Security, privacy and safety model

## Purpose and risk

TripParadox is a **synthetic intentionally vulnerable training environment** for the 2026 TBO Agentic Real-Time DAST challenge. Its role is to validate a security-testing *approach*. It is **not** an independent penetration-test authorization for TBO or any other business.

## Assets

- Synthetic B2B agency IDs and bookings
- Synthetic financial transactions
- Local administrator secrets and signed session tokens
- Evidence traces and audit entries
- Synthetic endpoint/route metadata

No real customer, card, passport, traveller or employee data belongs here.

## Threats and mitigations

| Threat | Mitigation in code | Remaining limitation |
|---|---|---|
| Scanner targets an unauthorized host | HTTPX in-memory ASGI transport, no user-provided hosts, path/method allowlist | Changing code could remove the boundary; review contributions |
| Scanner produces excessive load | Max 40 requests/run, sequential calls, minimum 15 ms interval | No holistic resource telemetry; add for staging |
| Simulator exposed publicly | Default process and Docker bindings are 127.0.0.1 only | User could mistakenly override bind; never do so |
| Unknown callers access scans | Signed JWT + admin role checks | Single-worker in-memory login throttle; use a shared limiter behind real ingress |
| Agency reads another's booking | Server-side ownership enforcement in secure mode | Demo can intentionally toggle a bug: isolate the lab |
| Leaked passwords or JWT signing key | Bootstrap random credentials, env-only, Argon2 password hashing, Git ignore `.env` | No secret vault or automatic key rotation |
| Stored XSS in evidence | Zero-dependency UI escapes server-supplied text | Dynamic content is escaped by the custom vanilla JavaScript client; still perform an independent XSS review |
| Browser token theft | Token held in JS memory, no browser local/session storage | Browser XSS remains a relevant general risk |
| False positives | Explicit policy and fresh-clone reproduction | Only three invariants; does not prove high precision in the wild |
| Fake proof / evidence fabrication | Typed results derived from actual mock API responses and DB totals | No cryptographic signing of reports |
| High-impact autonomous reporting | Ticket must be approved by a named authenticated reviewer | Admin and reviewer roles are combined in demo |
| Audit data exposure | Read restricted to admin, no token log | No tamper-evident log or retention policy in demo |
| Scan continues after emergency stop | Safety gate checks persistent stop flag before each new request | In-flight request may finish before stop is observed |
| Duplicate booking/refund actions | Financial invariant check; secure sequential replay is idempotent | Distributed race-safety needs unique constraints and transactions |

## Operational rules

1. Use only bundled synthetic data or mock APIs that TBO expressly authorizes for a particular evaluation.
2. Never set a target URL from arbitrary user input or run the demo scanner on a real domain.
3. Never store real personal data, API keys or production login cookies in the database or fixtures.
4. Do not run denial of service, destructive cleanup, privilege persistence or mass extraction.
5. Require a human to verify business severity before external escalation.
6. Stop testing immediately if the kill switch is activated or if the local app shows strain.
7. Review dependency licenses and lock versions before any use beyond this demonstration.

## Challenge brief mapping

The user's supplied *Fraud Prevention & Security.pdf*, pages 1–5, expressly calls for safe scope, rate limiting, minimal proof, ownership, zombie/shadow reporting, a human reviewer, and retesting. The scoring weights are valid findings/severity 30%, precision/noise 20%, safety 20%, speed after change 10%, report quality 10%, and discovery/inventory 10%. This prototype's design explicitly prioritizes the first three categories and demonstrates the rest at a bounded synthetic scope.

## External technical references

- OWASP API Security Top 10: https://api-security.owasp.org/editions/2023/en/0x11-t10/
- OWASP Broken Object Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- HTTPX ASGITransport (no network): https://www.python-httpx.org/advanced/transports/
