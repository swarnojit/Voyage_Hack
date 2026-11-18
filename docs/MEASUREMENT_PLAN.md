# Measuring TripParadox without inflated claims

## Metrics required by the security brief

1. **Change-to-confirmation latency**: `finding.discovered_at - deploy.created_at` for an automatically triggered scan, measured on a controlled deployment.
2. **Valid findings**: fraction of planted vulnerabilities found and reproducible on a fresh clone. Report both numerator and denominator.
3. **False-positive count**: count of confirmed findings on the known secure baseline (should be 0 in the supplied three-rule suite; broader trials need more scenarios).
4. **Request budget compliance**: all scanner runs must have `requests_sent <= 40`.
5. **Precision (if suitable labelled tests exist)**: `true_positive / (true_positive+false_positive)`. Do not imply 100% security coverage because one seeded test passes.
6. **Inventory accuracy**: compare predicted active/zombie/shadow labels against a manually curated mock manifest.
7. **Retest closure**: confirmed prior finding changes to `fixed` only after passing the same invariant on a secure version.
8. **Report completeness**: every confirmed finding has severity, owner, expected/observed proof and proposed mitigation.

## Reproducible evaluation experiments

| Experiment | Input | Expected minimum result |
|---|---|---|
| Secure baseline | Deploy `secure`, manual full scan | 3 checks; 0 confirmed findings |
| Access-control regression | Deploy `cross_agency`, auto scan | 1 affected check; 1 reproduced finding |
| Financial replay regression | Deploy `double_refund`, auto scan | 1 affected check; 1 reproduced finding |
| Legacy regression | Deploy `legacy_bypass`, auto scan | 1 affected check; 1 reproduced finding |
| Combined incident | Deploy `all`, manual full scan | 3 checks; 3 reproduced findings |
| Resolution | Deploy `secure`, retest selected older finding | Original finding moves to `fixed` |
| Scope abuse | Call `SafetyGate` with an external URL | Blocked before any HTTP call |
| Kill switch | Pause and trigger scan | No new scan allowed |
| Inventory check | Load bundled synthetic logs + old JS | Initial four fixture routes include active/zombie/shadow; additional live synthetic holds/pay/cancel calls become new shadow-route candidates |

## Limitations to disclose

- These are synthetic planted cases; success on them does not prove low false-positive rates on unknown TBO changes.
- The duplicate-refund test is sequential retry, not an adversarial concurrent race.
- Endpoints and application logic are demo-scale. The implementation does not yet crawl unknown real-world JavaScript bundles or live mobile APIs.
- Future improvement: blinded planted-bug evaluation, controlled staging integrations, coverage tracking, an adversarial red-team benchmark, and statistical confidence intervals over repeated runs.
