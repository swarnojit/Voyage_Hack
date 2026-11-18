"""Narrow, idempotent demo-schema upgrade for pre-existing SQLite/Postgres lab DBs.

This is NOT a replacement for reviewed Alembic migrations in production.
Never mutates customer data (the app only supports fictional seed data).
"""
from sqlalchemy import inspect, text


def migrate_demo_schema(engine):
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        if 'refunds' in tables:
            columns = {c['name'] for c in inspector.get_columns('refunds')}
            if 'safe_idempotency_key' not in columns:
                conn.execute(text('ALTER TABLE refunds ADD COLUMN safe_idempotency_key VARCHAR(140)'))
            # New refunds use this unique key; historic intentionally vulnerable
            # rows are NULL. Both PostgreSQL and SQLite support this index.
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS '
                              'uq_secure_refund_booking_key ON refunds '
                              '(booking_id, safe_idempotency_key)'))
        if 'tickets' in tables and engine.dialect.name == 'postgresql':
            columns = {c['name']: c for c in inspector.get_columns('tickets')}
            state = columns.get('state')
            if state is not None and getattr(state['type'], 'length', 999) is not None \
                    and state['type'].length < 48:
                conn.execute(text('ALTER TABLE tickets ALTER COLUMN state TYPE VARCHAR(48)'))
