#!/bin/sh
set -eu
# Runs only when the PostgreSQL data volume is initialized for the first time.
# App runs as a non-superuser, separate from PostgreSQL's bootstrap administrator.
: "${TP_DB_PASSWORD:?Missing TP_DB_PASSWORD}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$TP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE tp_app LOGIN PASSWORD %L', :'app_password') \gexec
GRANT CONNECT ON DATABASE tripparadox TO tp_app;
GRANT USAGE, CREATE ON SCHEMA public TO tp_app;
SQL
