# PostgreSQL database — full setup and security boundaries

PostgreSQL is the **primary database when running this package with Docker Compose**. SQLite remains the development fallback for `python scripts/run_backend.py` and isolated unit tests. This separation is intentional: no Docker runtime exists in the generation environment, so we executed the full backend tests against local SQLite and statically validated the actual PostgreSQL Compose configuration, but **we cannot claim a successful PostgreSQL container connection here**.

## One-command Docker deployment

```bash
# From project root, Windows/macOS/Linux with Docker Engine + Compose installed
python scripts/bootstrap.py
# Creates an ignored .env with JWT, demo accounts, PostgreSQL administrator
# and PostgreSQL application passwords. NEVER commit this file.
docker compose up --build -d
# Open http://127.0.0.1:8000/lab
# Observe:
docker compose ps
docker compose logs app --tail 60
curl http://127.0.0.1:8000/health/db
```

A good health response is `{"status":"ok", "database":"postgresql", ...}`. The in-app **Model Laboratory** and **Security & audit** pages also show the connected SQL dialect dynamically. If the health endpoint says `sqlite`, you are running the local Python mode, not the Docker PostgreSQL configuration.

**Network:** The application HTTP port is published **only to `127.0.0.1:8000`**. PostgreSQL itself has no published host port; the app and DB communicate through the private Docker Compose bridge network. The backend and scanner are not safe to expose to a public network due to deliberately planted demo vulnerabilities.

## PostgreSQL account separation

- PostgreSQL container initializes its private volume with bootstrap administrator `tp_admin` using `TP_PG_ADMIN_PASSWORD`.
- `docker/postgres/01-create-app-role.sh` runs only during **first database initialization** and creates the non-superuser SQL role `tp_app` using `TP_DB_PASSWORD`.
- The application logs in as `tp_app`, not `tp_admin`, via the `postgresql+psycopg://...` SQLAlchemy connection.
- `tp_app` receives `CONNECT` to the named database and `USAGE, CREATE` on the `public` schema. This is suitable for **demo schema bootstrap**, not a completed production least-privilege policy. After migrations, remove `CREATE` and grant explicit table-level rights for production.
- The app uses SQLAlchemy parameterized queries and exposes no connection strings or passwords in `/api/db/status` and `/health/db`.

**Important:** Editing passwords after the Postgres volume has already been initialized does **not** automatically rotate existing database credentials. Rotate SQL role passwords explicitly and update the application environment, or carefully recreate the demo volume if it holds only disposable synthetic data.

## SQL data model

| Table | Purpose | Key relationships |
|---|---|---|
| `agencies` | Fictional agency identities | `id` |
| `users` | Argon2 authentication and role | `agency_id` → `agencies` |
| `bookings` | Baseline and counterfactual booking clones | `agency_id` → `agencies` |
| `refunds` | Synthetic payment conservation proof | `booking_id` → `bookings` |
| `deploys` | Controlled faulty/secure versions | `id` |
| `scan_runs` | Queued/running/completed scanners | `deploy_id` → `deploys` |
| `model_snapshots` | Model build fingerprint and holdout metrics | unique `model_version` |
| `model_predictions` | All scored ML decisions and previews | nullable `scan_id` → `scan_runs` |
| `run_events` | Live backend execution timeline | `run_id` → `scan_runs` |
| `evidence` | Deterministic expected/observed invariant state | `scan_id` → `scan_runs` |
| `findings` | Verified business-rule violations | `scan_id` → `scan_runs` |
| `tickets` | Human review workflow | `finding_id` → `findings` |
| `api_inventory` | Active/zombie/shadow route labels | unique `path_template` |
| `traffic` | Synthetic route observations | `id` |
| `audit` | Who did what and when | `id` |
| `simulator_config` | Synthetic flaw toggles and safety kill switch | `id` |

These tables are defined in `backend/app/models.py`; SQLAlchemy creates them automatically on first startup. **Schema migrations are not included**; for production lifecycle management, use Alembic and reviewed revisions.

## Inspect live PostgreSQL records

```bash
# Admin shell inside the PostgreSQL container; never paste passwords into chat.
docker compose exec postgres psql -U tp_admin -d tripparadox
```

```sql
SELECT id, model_version, created_at FROM model_snapshots ORDER BY id DESC;
SELECT id, scan_id, case, round(risk_score::numeric, 3) AS risk,
       round(novelty_score::numeric, 3) AS novelty, predicted_class
FROM model_predictions ORDER BY id DESC LIMIT 20;
SELECT id, status, confirmed, requests_sent FROM scan_runs ORDER BY id DESC LIMIT 10;
SELECT id, phase, title FROM run_events ORDER BY id DESC LIMIT 20;
SELECT id, kind, severity, status FROM findings ORDER BY id DESC LIMIT 20;
SELECT id, action, actor, result FROM audit ORDER BY id DESC LIMIT 20;
```

## Backup and shutdown

```bash
docker compose exec -T postgres pg_dump -U tp_admin -d tripparadox -Fc > tripparadox-synthetic.backup
docker compose down                 # preserves the named database volume
# WARNING — `docker compose down -v` deletes your lab's database volume.
```

Place backups outside the Git repository. Database records are **fictional and reproducible**, but passwords and authentication tokens are not data to be committed or shared.

## Verification and limits

- Validated: Compose YAML structure, service dependency on PostgreSQL health, private network, local host binding, SQLAlchemy PostgreSQL DSN selection, role initialization script presence, and separate credential variables.
- Validated live: API tests, real ML inference, SQL persistence and browser integration with SQLite in this workspace.
- **Not validated live here:** PostgreSQL container creation or actual database queries against a running PostgreSQL server, because Docker/Postgres executable is unavailable in the environment.
- Still required for production: formal migrations, TLS and managed secrets, structured rotation, strict SQL permissions, backups and disaster recovery, external penetration test, shared process rate limit, and real auth provider.
