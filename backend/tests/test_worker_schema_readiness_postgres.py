"""Worker startup probes on an exclusively owned disposable PostgreSQL database."""
import os
import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.commands import schema_preflight, worker_schema_readiness as gate


@pytest.fixture
def pg():
    raw = os.environ.get("WORKER_SCHEMA_POSTGRES_TEST_URL")
    if not raw:
        pytest.skip("Disposable worker-readiness PostgreSQL database not configured")
    url = make_url(raw)
    if url.host not in {"localhost", "127.0.0.1"} or not (url.database or "").startswith("db133_test_merge_worker_gate_"):
        raise RuntimeError("Only the dedicated local worker-gate disposable database is permitted")
    engine = create_engine(schema_preflight._sync_postgres_url(raw), poolclass=NullPool)
    with engine.connect() as connection:
        assert set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars()) == gate._expected_heads()
    try:
        yield raw, engine
    finally:
        engine.dispose()


def test_actual_probe_is_readonly_with_effective_connection_timeouts(pg, monkeypatch):
    raw, _ = pg
    original = schema_preflight.verify_database
    evidence = {}

    def inspect_transaction(connection, heads):
        for setting in ("transaction_read_only", "statement_timeout", "lock_timeout"):
            evidence[setting] = connection.execute(text("SELECT current_setting(:name)"), {"name": setting}).scalar_one()
        with pytest.raises(DBAPIError) as exc:
            with connection.begin_nested():
                connection.execute(text("CREATE TABLE worker_gate_write_must_fail (id integer)"))
        assert exc.value.orig.pgcode == "25006"
        original(connection, heads)

    monkeypatch.setattr(schema_preflight, "verify_database", inspect_transaction)
    assert gate._probe_database(raw, gate._expected_heads()) == "ready"
    assert evidence == {"transaction_read_only": "on", "statement_timeout": "2s", "lock_timeout": "1s"}


def test_current_head_with_missing_physical_c1_column_cannot_unlock_worker(pg):
    raw, engine = pg
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE customers RENAME COLUMN pricing_labor_rate TO gate_test_missing_rate"))
        assert gate._probe_process(raw, gate._expected_heads(), 5) == "schema_not_ready"
    finally:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE customers RENAME COLUMN gate_test_missing_rate TO pricing_labor_rate"))
    assert gate._probe_process(raw, gate._expected_heads(), 5) == "ready"


def test_ddl_lock_does_not_hold_probe_past_actual_lock_timeout(pg):
    raw, engine = pg
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE"))
        try:
            started = time.monotonic()
            assert gate._probe_process(raw, gate._expected_heads(), 5) == "unavailable"
            assert time.monotonic() - started < 4
        finally:
            transaction.rollback()
    assert gate._probe_process(raw, gate._expected_heads(), 5) == "ready"


def test_actual_statement_timeout_bounds_slow_inspection(pg, monkeypatch):
    raw, _ = pg

    def slow(connection, heads):
        connection.execute(text("SELECT pg_sleep(10)"))

    monkeypatch.setattr(schema_preflight, "verify_database", slow)
    started = time.monotonic()
    assert gate._probe_database(raw, gate._expected_heads()) == "unavailable"
    assert time.monotonic() - started < 4
