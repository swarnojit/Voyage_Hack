# Integration and validation walkthrough

## The complete frontend-to-model-to-database chain

```text
Open Model laboratory in the left sidebar
  ↓ GET /api/ml/overview
SQLAlchemy checks/creates a model snapshot → returns real holdout results,
features, global feature importance, database dialect and registry counts
  ↓ Tick eight flags + describe synthetic endpoint
POST /api/ml/preview, admin JWT, strict Pydantic validation
  ↓ in-process sklearn pipeline
RF risk, TF-IDF threat class, Isolation Forest novelty
  ↓ SQL transaction
model_predictions + audit, cross-reference model_snapshots
  ↓ JSON response
Browser shows scores, class distribution explanation and saved prediction ID
  ↓ Autonomous scanner
Choose synthetic deploy, preview phases, Run → model plans persist under scan_id
  ↓ safe replay, fixed policy oracle
SQL booking forks, evidence, findings, review tickets and run_events
  ↓ GET /api/agent/runs/{id} and GET /api/ml/predictions?scan_id=...
UI shows ML planning + exact backend stages and independent proof results
```

## Reproducible validation

```bash
# Without Docker: SQLite-only local demonstration
python scripts/bootstrap.py
python -m pip install -r backend/requirements-dev.txt
python scripts/run_backend.py
# Visit http://127.0.0.1:8000/lab

# Test suite
cd backend
python -m pytest tests -q
# 39 passing automated tests in the generation environment.

# JavaScript syntax validation
node --check app/static/app.js    # when cwd is backend

# PostgreSQL primary deployment (requires Docker installed)
cd ..
docker compose up --build -d
curl http://127.0.0.1:8000/health/db
```

## Running a real demo

1. Log in using the generated admin credentials in your local ignored `.env`.
2. Open **Model Laboratory**. Explain the three models, eight feature flags, holdout metrics, and separate proof oracle.
3. Select **Refund replay**, choose Run local model preview; the new inference appears in the SQL history table.
4. Open **Autonomous scanner**, inspect the preflight phase list, and start Combined regression.
5. Show the scanner trace: `ml` → `plan` → `inventory` → `fork` → `oracle` → `evidence` → `final`.
6. Show **Model-to-scan evidence** beneath the scanner: each recorded `scan_id`, class, risk and novelty score is SQL-backed.
7. Open **Verified findings** to display independently reproduced synthetic vulnerabilities.
8. Deploy a secure scenario, then retest the finding and show closure.
9. Open **Security & audit** and show the actual connected SQL dialect and kill switch.

## Screenshot artifacts from actual browser integration

- `docs/model-laboratory.png` — model architecture, metrics, features and SQL registry.
- `docs/model-inference.png` — live synthetic refund feature inference persisted in SQL.
- `docs/scan-with-model-evidence.png` — scanner execution after a synthetic run.

**Accuracy disclosure:** the risk and classifier metrics belong to synthetic holdout samples, not a real-world security dataset. The runtime verification is a controlled demonstration. If asked whether the system is unbreakable, the answer is **no**.
