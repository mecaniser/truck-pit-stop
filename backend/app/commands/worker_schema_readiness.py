"""Wait for the Web-owned migration before a Celery worker starts bootsteps.

Importing this module does not connect or wait. Each read-only probe runs in a
bounded child process so DNS/driver stalls cannot outlive the startup deadline.
Database credentials travel only over its private stdin pipe, never argv/logs.
"""
from __future__ import annotations

import json
import logging
import math
import subprocess
import sys
import time
from pathlib import Path


logger = logging.getLogger(__name__)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
TOTAL_WAIT_SECONDS = 120.0
PROBE_TIMEOUT_SECONDS = 10.0
RETRY_SECONDS = 2.0
CONNECT_TIMEOUT_SECONDS = 3
STATEMENT_TIMEOUT_MS = 2000
LOCK_TIMEOUT_MS = 1000
EXIT_UNAVAILABLE = 78
REQUIRED_COLUMNS = {
    "customers": {
        "ets_contact_phone_snapshot", "pricing_labor_rate", "parts_price_matrix_id",
        "pricing_version", "pricing_updated_at", "pricing_updated_by",
    },
    "repair_orders": {"pricing_policy_snapshot", "pricing_matrix_revision_id"},
    "counter_sales": {"pricing_policy_snapshot", "pricing_matrix_revision_id"},
    "labor": {"pricing_snapshot", "pricing_source"},
    "account_pricing_events": {"id", "tenant_id", "entity_type", "entity_id", "created_at"},
}
PROBE_STATES = frozenset({"ready", "schema_not_ready", "unavailable", "fatal"})


def _expected_heads() -> set[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    heads = set(ScriptDirectory.from_config(config).get_heads())
    if len(heads) != 1:
        raise ValueError("Worker requires one installed migration head")
    return heads


def _probe_database(database_url: str, expected_heads: set[str]) -> str:
    """One bounded, read-only connection; no ORM, DDL, migration or task calls."""
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.exc import ArgumentError, DBAPIError, NoSuchTableError, SQLAlchemyError
    from sqlalchemy.pool import NullPool
    from app.commands import schema_preflight

    engine = None
    try:
        engine = create_engine(
            schema_preflight._sync_postgres_url(database_url),
            connect_args={
                "connect_timeout": CONNECT_TIMEOUT_SECONDS,
                "options": (
                    "-c default_transaction_read_only=on "
                    f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
                    f"-c lock_timeout={LOCK_TIMEOUT_MS}"
                ),
            },
            hide_parameters=True,
            poolclass=NullPool,
        )
        with engine.connect() as connection:
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                schema_preflight.verify_database(connection, expected_heads)
                inspector = inspect(connection)
                for table, required in REQUIRED_COLUMNS.items():
                    present = {column["name"] for column in inspector.get_columns(table)}
                    if not required <= present:
                        return "schema_not_ready"
                return "ready"
            finally:
                connection.rollback()
    except (schema_preflight.SchemaPreflightError, NoSuchTableError):
        return "schema_not_ready"
    except ArgumentError:
        return "fatal"
    except DBAPIError as exc:
        # Authentication, missing database and denied inspection cannot be
        # repaired by the Web's pending migration. Never expose server messages.
        if getattr(exc.orig, "pgcode", None) in {"28P01", "28000", "3D000", "42501"}:
            return "fatal"
        return "unavailable"
    except SQLAlchemyError:
        return "unavailable"
    except Exception:
        return "fatal"
    finally:
        if engine is not None:
            engine.dispose()


def _probe_process(database_url: str, expected_heads: set[str], timeout: float) -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.commands.worker_schema_readiness", "--probe"],
            cwd=BACKEND_ROOT,
            input=json.dumps({"database_url": database_url, "expected_heads": sorted(expected_heads)}),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        # subprocess.run kills and reaps the child on timeout. Its server-side
        # statement timeout also bounds any query left during disconnection.
        return "unavailable"
    except Exception:
        return "fatal"
    try:
        body = json.loads(result.stdout)
        state = body["state"]
        if result.returncode == 0 and set(body) == {"state"} and state in PROBE_STATES:
            return state
    except (ValueError, KeyError, TypeError):
        pass
    return "fatal"


def _abort(reason: str) -> None:
    logger.error("Worker schema readiness aborted: %s; no worker bootsteps started", reason)
    # Celery signal dispatch swallows Exception; SystemExit must propagate.
    raise SystemExit(EXIT_UNAVAILABLE)


def wait_for_worker_schema(
    database_url: str,
    *,
    total_wait: float = TOTAL_WAIT_SECONDS,
    retry_seconds: float = RETRY_SECONDS,
    probe_timeout: float = PROBE_TIMEOUT_SECONDS,
) -> None:
    started = time.monotonic()
    if not all(math.isfinite(v) and v > 0 for v in (total_wait, retry_seconds, probe_timeout)):
        _abort("invalid wait configuration")
    deadline = started + total_wait
    try:
        from app.commands.schema_preflight import _sync_postgres_url

        _sync_postgres_url(database_url)
        heads = _expected_heads()
    except Exception:
        _abort("invalid database or migration configuration")
    logger.info("Worker schema readiness waiting for installed migration head")
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _abort("deadline exhausted")
        state = _probe_process(database_url, heads, min(probe_timeout, remaining))
        # A result arriving outside the deadline cannot unlock startup.
        if time.monotonic() >= deadline:
            _abort("deadline exhausted")
        if state == "ready":
            logger.info("Worker schema readiness passed; startup may continue")
            return
        if state == "fatal":
            _abort("unrecoverable readiness failure")
        time.sleep(min(retry_seconds, max(0.0, deadline - time.monotonic())))


def _probe_main() -> None:
    logging.disable(logging.CRITICAL)
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("oversized probe request")
        request = json.loads(raw)
        if set(request) != {"database_url", "expected_heads"}:
            raise ValueError("invalid probe request")
        heads = request["expected_heads"]
        if not isinstance(heads, list) or len(heads) != 1 or not isinstance(heads[0], str):
            raise ValueError("invalid expected heads")
        state = _probe_database(request["database_url"], set(heads))
    except Exception:
        state = "fatal"
    print(json.dumps({"state": state}))


if __name__ == "__main__":
    if sys.argv[1:] != ["--probe"]:
        raise SystemExit(EXIT_UNAVAILABLE)
    _probe_main()
