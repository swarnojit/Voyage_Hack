# Model card: local security-planning ML

## Why ML and why these choices?

The challenge allows hybrid approaches, and reliable security findings require reproducible verification. **TripParadox uses ML to order and categorize candidate checks**, never to decide whether a vulnerability has been proven or to authorize an HTTP request. This avoids the hallucinated-vulnerability problem of having an LLM write and approve its own tests.

### Model 1 — RandomForestClassifier (75 estimators)

- Purpose: prioritize pre-registered security checks after a change.
- Features: authorization boundary, financial mutation, legacy endpoint, undocumented endpoint, privileged operation, cross-role flow, write method, recently changed.
- Training: 1,200 entirely synthetic feature/label pairs generated with a reproducible NumPy random seed and a noisy, *invented* risk process.
- Validation: held-out 25% of synthetic data with stratified split; the displayed metric measures only model agreement with the invented training distribution. It is **NOT** precision, recall or accuracy on real vulnerabilities.
- Output: bounded `0..1` scheduling score for each **already approved** test case.

### Model 2 — TfidfVectorizer + LogisticRegression

- Purpose: classify brief fictional endpoint descriptions as `authorization`, `financial_logic`, `legacy_api`.
- Training: small, handcrafted synthetic phrase variations. Demonstrates actual model inference but not generalization to unknown production attack classes.
- Output: predicted class plus class confidence (not a vulnerability probability).

### Safety and reproducibility

- Model creation happens in Python at process startup or first use (`lru_cache`), with **no `pickle` / `joblib` loading**, preventing untrusted model deserialization.
- Neither model can create endpoints, custom payloads or arbitrary tools; the registry of allowed tests is static JSON and the executor enforces exact routes.
- No customer data, external model services, remote LLM calls or GPU required.
- The models are not evaluated on real adversarial traffic. A meaningful benchmark would require a formally labelled corpus from approved staging and metrics for valid finding rate, false positives, detection delay, and coverage.
- Future optional extension: self-hosted LLM provides **candidate** scenario hypotheses under a strict schema and a human-reviewed rule registry, never direct unrestricted execution.

### Execution example

`GET /api/agent/plan?scenario=all` returns each `case`, `risk_priority_score`, `predicted_class`, `class_confidence`, `feature_vector`, and run phase descriptions. `POST /api/agent/start` executes those registered tests in scored order and records the plan plus subsequent proof evidence in SQL.

### Source code

- `backend/app/services/ml_planner.py`: real model definitions, synthetic training generation, inference, scoring.
- `backend/app/services/engine.py`: enforced ML-assisted scheduling, bounded execution, deterministic proof.
- `backend/app/services/safety.py`: exact method/path allowlist, budget, kill switch.

**Research references:** scikit-learn classifiers and model-persistence safety documentation; official docs are linked in the README research notes.
