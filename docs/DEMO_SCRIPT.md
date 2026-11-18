# Five-minute live demonstration — TripParadox AI PRO

**All amounts, accounts and vulnerabilities are fictional. Only a local simulator is tested.**

### 0:00–0:40 — Why TBO needs it

"Ordinary scanners test individual endpoints. The real financial and privacy failures in B2B travel can happen across a journey: one agency sees another agency's booking, or one payment is refunded twice. TripParadox tests whether those impossible business outcomes can happen after a software update."

Open the **Overview**. Highlight the three invariants and the in-process target lock.

### 0:40–1:25 — Actual AI model + plan preview

Open **Autonomous scanner** → scenario `Combined regression` → **Preview & run scan**. Show 8 planned stages. Point to **two actual scikit-learn models** and their feature-based priority scores. Say clearly: "These models choose and rank approved tests; SQL-backed deterministic checks decide whether a bug is real. Synthetic validation accuracy is not production accuracy."

### 1:25–2:45 — Automatic scan, transparent backend

Click **Run the automated scan**. The UI shows a timeline of the actual SQL-inserted events: safety check, model training, prioritization, route inventory, booking forks, HTTP request execution, invariant validation, reproduction, ticket creation, and summary. Expand **View backend operation & data** to show concrete functions and evidence. Expected synthetic demonstration: three planted security violations and ten bounded requests.

### 2:45–3:30 — Explain the proof

Open **Verified findings**. Select the duplicate-refund result. Baseline refunds a fictional booking once; counterfactual retries the same refund; observed SQL ledger exceeds paid amount. It is confirmed on another freshly cloned booking. Highlight expected state, observed state, owner and recommended fix.

### 3:30–4:10 — The actual travel app and SQL

Open **Travel platform clone**. Display fictional Dubai, Singapore and Bangkok hotels. Click **Hold this room**, then **Confirm simulated payment**, then **Cancel booking**. Show the booking row status changing; these actions persist via SQLAlchemy rather than being UI mock data. There is no real payment gateway.

### 4:10–4:40 — Deploy secure patch and retest

In scanner select **Secure release**; preview and run. Return to an earlier finding and click **Retest after secure deployment**. A pass marks the issue `fixed` and its internal ticket resolved. Original evidence remains.

### 4:40–5:00 — Safe governance

Show **Controls & audit**: token roles, Argon2, restricted host, SQL health, scanner exact-route gate, emergency stop and no external scanning. Explain the needed authorized-staging work before a real TBO pilot.

**Closing sentence:** "TripParadox automatically tries alternate synthetic travel journeys, and does not call something a vulnerability until it has proved that the system broke a business law."
