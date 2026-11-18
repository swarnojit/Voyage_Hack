# TripParadox — Detailed ML Engineering and Orchestration

The runnable code is in `backend/app/services/ml_planner.py`, `model_registry.py`, and `engine.py`. This is a **local, synthetic, reproducible ML laboratory** for the organizer's Agentic Real-Time DAST challenge. The models do **not** test arbitrary websites, generate exploits, or certify security; testing happens only through a fixed registry of three controlled synthetic business-rule checks.

## A. End-to-end architecture

```text
Browser: Model Laboratory                      Browser: Autonomous scanner
   | eight feature switches + description         | choose deployed synthetic change
   v                                              v
POST /api/ml/preview                         GET /api/agent/plan
   |                                              |
   |  Python / scikit-learn                       | registered test cases only
   +----------------------------------------------+
   |                 local inference               |
   |  MODEL 1 Random Forest risk priority         |
   |  MODEL 2 TF-IDF + Logistic Regression         |
   |          threat category                      |
   |  MODEL 3 Isolation Forest novelty flag        |
   |                                              v
   |                                        POST /api/agent/start
   |                                              |
   |                                    authorized bounded ASGI executor
   |                                    transaction clone A, clone B
   |                                    verify SQL booking invariant
   |                                    reproduce on fresh clone
   |                                              |
   v                                              v
PostgreSQL or SQLite: model_snapshots, model_predictions, scan_runs,
                    run_events, evidence, findings, tickets, audit
   |
   v
UI: score, important flags, SQL rows, timeline, proof cards, review tickets
```

**Trust separation:** AI predictions only determine the *order* and *category* of allowlisted tests. A deterministic oracle separately checks financial conservation or access boundaries, repeats findings, and records evidence. The user cannot configure an external URL or executable request from the ML interface.

## B. Model 1 — supervised risk prioritization

**Purpose:** Sort approved security tests so potentially important travel business flows run sooner.

**Algorithm:** `RandomForestClassifier(n_estimators=120, max_depth=7, min_samples_leaf=5, class_weight='balanced_subsample', random_state=42)`.

**Eight features**, each `0` or `1`, and their precise meanings:

| Feature | Interpretation |
|---|---|
| `authorization_boundary` | Cross-user or cross-agency ownership might matter |
| `financial_mutation` | Can change refund/payment records |
| `legacy_endpoint` | Deprecated or old-version API |
| `undocumented_endpoint` | Missing from approved API inventory |
| `privileged_operation` | Requires elevated permission |
| `cross_role_flow` | Involves several roles/agencies |
| `write_method` | Mutates state, rather than read-only |
| `recently_changed` | A deployment changed it |

**Training:** Generate 1,800 fictional binary endpoint feature vectors with NumPy seeded at `20261118`. Generate synthetic outcome labels from a documented weighted latent function with randomness; *these labels are invented, not from real breaches*. Stratified train/test: 1,350 train, 450 held-out test. The random forest sees only training rows, and held-out examples determine accuracy, precision, recall, F1, ROC-AUC and Brier loss.

**Measured synthetic holdout metrics (in the packaged evaluation run):** accuracy `0.8200`; precision `0.8642`; recall `0.8358`; F1 `0.8497`; ROC-AUC `0.8977`; Brier `0.1289`. Exact results are calculated dynamically by the running code. They **do not predict real-world security detection rates**.

**Inference:** `risk.predict_proba([features])[0, 1]` produces a **priority score**. It is NOT a probability that a real vulnerability exists. Active feature contributions are approximated by setting one flag to 0 and measuring the change in the model output. The UI calls these *risk drivers*; they are conditional model sensitivities, not causal proof.

## C. Model 2 — NLP threat-family classification

**Purpose:** Classify a synthetic endpoint change into `authorization`, `financial_logic`, or `legacy_api` to help explain why an approved test was selected.

**Algorithm:** `TfidfVectorizer(ngram_range=(1,2), stop_words='english', sublinear_tf=True)` followed by `LogisticRegression(max_iter=1500, random_state=42)` in an sklearn Pipeline.

**Training:** 10 independently authored source phrases per class, combined with four innocuous prefixes. Split by **phrase family first**: 8 phrases/class for training, 2 phrases/class held out. This avoids placing identical source phrases with different prefixes in both train and test (one source of misleading evaluation results). Synthetic dataset has 96 training and 24 held-out descriptions.

**Metrics:** held-out macro F1 `0.8166` and accuracy `0.8333` on the generated phrase set, with per-class precision and recall in `GET /api/ml/overview`. A novel real supplier API description may classify incorrectly; class predictions never independently trigger or authorize tests.

**Output:** category, class confidence, and a probability distribution for all three categories.

## D. Model 3 — novelty detection

**Purpose:** Flag feature combinations unlike *simulated normal* API changes.

**Algorithm:** `IsolationForest(n_estimators=100, contamination=.07, random_state=2026)` trained on synthetic feature rows labelled ordinary by the synthetic risk generator. Its `decision_function` gives an unsupervised signed margin. We use a bounded sigmoid of the negative margin to display a **novelty index** from 0–1. Negative margin is flagged as an outlier.

This model has no ground-truth precision/recall claim. Unusual is not equivalent to insecure. More genuine normal-operation histories would be needed for useful real-world deployment.

## E. Stable model identity and reproducibility

`MODEL_VERSION` is the first 16 hexadecimal characters of SHA-256 over the seed, feature schema, threat-source phrase families, and algorithm label. It is **a synthetic training configuration fingerprint, not a cryptographic checksum of fitted model weights**. Model outputs, evaluation metadata, and version are stored using SQLAlchemy. Predictions are recomputed from deterministic synthetic training during each process start; no unsafe external pickle/joblib model file is loaded.

The Python `@lru_cache` ensures the trained scikit-learn objects are reused in the process. On a new process start, training regenerates identical illustrative data and the model code rebuilds the estimators.

## F. Exactly what happens when Run is clicked

1. The browser requests `GET /api/agent/plan?scenario=...` and shows safety constraints and anticipated backend stages.
2. The user explicitly starts a selected **synthetic** change using `POST /api/agent/start`.
3. Python checks admin role, emergency stop flag, and whether another scan is running.
4. The system records the simulated deployment and queues a `scan_runs` row.
5. The approved invariant registry limits the scenarios to cross-agency read, duplicate refund, and legacy bypass.
6. All three ML models score the approved tests. Their scores, feature flags, model build, class and explanations are recorded in `model_predictions` under the `scan_id`.
7. The run records the ML plan to `run_events`, which the UI polls.
8. The inventory builder compares synthetic traffic, documented paths and archived JS fixtures.
9. The counterfactual engine clones a fake SQL booking. It uses real local FastAPI requests through HTTPX's **in-process ASGI transport**, not a network host.
10. A strict allowlist, per-run request cap, sequential execution and kill switch enforce scope.
11. Deterministic invariants compare the actual SQL outcome with the expected outcome; suspected violations are reproduced on another cloned booking.
12. The system saves `evidence`, `findings`, human-review `tickets`, `audit`, and the final run outcome. Fix/retest reads these records rather than trusting the model.

## G. Data, evaluation and deployment limitations

- All models train on synthetic features and phrases. Do not claim the held-out metrics establish real vulnerability detection performance.
- An ML score never changes tenant permissions, payment/refund logic, target hosts, or test payloads.
- Interactive preview accepts only eight explicit binary flags and a short synthetic description. It makes no scanner request.
- New test classes require an explicit human-reviewed validator in `services/engine.py` and registration in `fixtures/security_invariants.json`.
- There is no arbitrary external API scanning, zero-day generalization, LLM reasoning engine, or guarantee of being unbreakable.
- Test with synthetic accounts only. For any eventual approved staging integration, add a separate connector and obtain explicit scope, credentials, security review, and governance approval.

## H. Where to edit code

- `backend/app/services/ml_planner.py` — three models, feature schema, synthetic training, metrics, inference and explanations.
- `backend/app/services/model_registry.py` — save model versions and predictions into SQL.
- `backend/app/services/engine.py` — scanner orchestration and deterministic travel-security proofs.
- `backend/app/services/safety.py` — hard request allowlist, rate limit, kill switch.
- `backend/app/routers/api.py` — authenticated endpoints for the scanner and Model Lab.
- `backend/app/models.py` — SQLAlchemy models; `ModelSnapshot`, `ModelPrediction`.
- `backend/app/static/app.js` — frontend, real ML values, live scan trace and SQL ledger.
- `backend/tests/test_model_lab.py` — model/API/database integration regression tests.

### Library documentation

- [scikit-learn: common pitfalls and leakage](https://scikit-learn.org/stable/common_pitfalls.html)
- [scikit-learn: model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html)
- [scikit-learn: probability calibration](https://scikit-learn.org/stable/modules/calibration.html)
