# Optional TBO Round 1 pitch outline — 2 content slides

Do not claim real TBO findings. Include cover and thank-you separately if the portal permits those extras, as indicated in the user's earlier screenshots.

## Slide 1: Problem, innovation, and impact

**Title:** TripParadox AI — A security time machine for B2B travel business logic

**Problem:** TBO's supplied brief highlights cross-agency booking access, fare/markup tampering, duplicate refunds, role escalation and legacy APIs, and asks agents to detect newly introduced vulnerabilities after changes.

**Innovation:** Business Physics Engine + two counterfactual journeys + database-state oracle + fresh-clone confirmation + automatic regression-test record.

**Potential impact (testable, not proven):** Faster verified findings after deployments, fewer noisy alerts, reduced risk of unauthorized cross-agency access and financial logic errors, and traceable engineering remediation.

**Proof visual:** Booking amount 10,000 synthetic rupees → universe A refund 10,000, universe B refund 20,000 → violation reproducible → assigned ticket.

## Slide 2: Technical implementation, adoption risk and evidence

**Architecture:** Mock booking app → deploy event → fixture inventory/route graph → planner → bounded in-process agent → isolated booking clones → invariant oracle → evidence + human review + retest.

**Round 2 build:** FastAPI + SQLAlchemy + SQLite/PostgreSQL + browser UI + seeded flows + tests. All 3 security invariants implemented; 17 backend tests passed in the authoring environment.

**Safety:** Only synthetic accounts and fixtures, no arbitrary external targets, max 40 calls/scan, pause switch, human review.

**Adoption risks:** Needs authorized staging inputs, policy approval, real API discovery, proper false-positive benchmark, distributed job workers and robust secrets/permissions before production.

**Ask:** Evaluate on controlled newly deployed planted bugs, not on manufactured dashboard numbers.
