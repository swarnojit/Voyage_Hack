# Security review checklist — tested synthetic lab

## Checked or enforced controls

| Category | Status | Concrete evidence |
|---|---|---|
| API authentication | Implemented + tested | Bearer JWT with audience, expiry, role and agency consistency |
| Password protection | Implemented | Argon2 salt + hash, bootstrap random passwords and key |
| Role & tenant separation | Unit/integration-tested | Unauthorized agency cannot access, pay or cancel another agency's normal booking |
| Management isolation | Tested | Admin endpoints return 401 without token and 403 to agency roles |
| SQL safety | Implemented | SQLAlchemy parameterized ORM, SQLite foreign keys and WAL; optional PostgreSQL |
| Scanner scope | Tested | Exact three method/path patterns, only in-process HTTPX ASGI transport |
| Budget/switch | Tested | 40 requests max, sequential pacing, persisted kill switch; post-change event audit |
| Browser | Tested | Host allowlist, CSP, X-Frame-Options, nosniff, no-store, Permissions-Policy |
| Input validation | Implemented | Pydantic field types, lengths, amounts and fixed scenario enum |
| Login abuse protection | Partial | In-memory 60-second throttle after six failed attempts (not distributed) |
| Data classification | Implemented | Fictional agencies/hotels; no live customer data or real payment processor |
| Proof confirmation | Tested | Violations are reproduced on new SQL booking clone before filing |
| Fix verification | Tested | Retest after secure deployment marks finding fixed only after passing check |
| Logs & review | Implemented | SQL audit records of synthetic calls, deployment and human decision |
| SSRF/target injection | Architecture blocks | No arbitrary URL or outbound scanner transport; fixed local ASGI app |

## Important limitations

- This software intentionally contains vulnerable code behind admin-only **fictional deployment switches**. The correct safety measure is **local isolated deployment**, not claiming the vulnerabilities don't exist.
- It does NOT provide a universal guarantee of security or unbreakability.
- The proof engine tests only three registered business-rule invariants, not every OWASP category. It does not guarantee detection of unknown flaws, authentication implementation bugs, concurrency races, SSRF, XSS, or SQL injection.
- Current inventory consumes synthetic input fixtures; it does not crawl the internet or discover real undocumented TBO APIs.
- No actual independently run penetration test, dependency CVE audit, model red-teaming, formal application threat model sign-off, or production integration has been performed.
- Rate limiting is currently in-process; multi-worker deployments need Redis/database-backed shared limits and durable distributed worker locks.
- Database migration files are not included; the MVP uses `Base.metadata.create_all()` at startup. Use Alembic and schema-change approvals before running on production-like persistent data.
- Session revocation, HTTPS termination, provider SSO, secrets vault/KMS, runtime service isolation and structured SIEM forwarding are future requirements.
- Any authorized staging integration must use explicit TBO permission, dedicated synthetic credentials, a written domain/path allowlist, load controls, and named approvers.

## How to check locally

```bash
cd backend
python -m pytest tests -q
```

Then sign into `/lab`, visit **Controls & audit**, confirm each configuration state and exercise the kill switch. Use `GET /api/db/status` (admin JWT required) to confirm SQL-backed data. The status panel is **self-reported runtime config**, not a certificate of security.


## Model Laboratory and PostgreSQL edition (2026-11)

- Models use synthetic data and are used **only for risk-based scheduling**; no decision based on their output grants privileges, moves money, selects arbitrary URL targets or establishes a confirmed vulnerability.
- Admin-only API `/api/ml/preview` uses Pydantic with strict 8-feature binary schema and forbids unknown fields; no executable payload field exists.
- Model scores and limited synthetic description-derived features are persisted in `model_predictions` and require a documented retention policy before any real deployment. Do not insert genuine PII or customer records.
- PostgreSQL Compose initializes a non-superuser app role, binds HTTP to host loopback, and does not publish the DB port; dynamic SQL is parameterized by SQLAlchemy.
- Schema changes still use SQLAlchemy `create_all` for demonstration; Alembic migrations, credential rotation, backup validation, TLS, audited hardening and full staging authorization remain prerequisites for any production deployment.
- Docker/PostgreSQL connection was not executed in the generation workspace; static configuration and SQL dialect checks pass only.
