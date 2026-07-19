"""Fail a deploy when the live PostgreSQL schema does not match this release.

This command is intentionally independent from the application Settings object:
deployment checks only need ``DATABASE_URL`` and must not require or echo other
runtime secrets. Railway runs it immediately after ``alembic upgrade head``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterable

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Connection, Engine, URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool


ALEMBIC_CONFIG_PATH = Path(__file__).resolve().parents[2] / "alembic.ini"

# These objects back code paths already deployed in this release. Keep this
# list small and explicit: it is a release-safety probe, not a schema diff tool.
PARTS_USAGE_SOURCE_LINE_INDEX = "ix_parts_usage_source_line_id"
PARTS_USAGE_SOURCE_LINE_FOREIGN_KEY = "fk_parts_usage_source_line_id_labor"
REPAIR_ORDER_ACTIVE_LIST_INDEX = "ix_repair_orders_tenant_created_at"
PROVIDER_OUTBOX_DUE_INDEX = "ix_provider_outbox_due"


class SchemaPreflightError(RuntimeError):
    """Raised when the database is not safe to serve this application release."""

    def __init__(self, issues: Iterable[str]):
        self.issues = tuple(issues)
        super().__init__("; ".join(self.issues))


def _sync_postgres_url(database_url: str) -> URL:
    """Return a URL suitable for Alembic/SQLAlchemy's synchronous inspector."""
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise SchemaPreflightError(("DATABASE_URL must use PostgreSQL for schema preflight",))

    if url.drivername == "postgresql+asyncpg":
        return url.set(drivername="postgresql")
    return url


def _load_expected_heads(alembic_config_path: Path = ALEMBIC_CONFIG_PATH) -> set[str]:
    config = Config(str(alembic_config_path))
    script = ScriptDirectory.from_config(config)
    return set(script.get_heads())


def _normalise_action(value: Any) -> str:
    return " ".join(str(value or "").upper().split())


def _index_matches(
    indexes: Iterable[dict[str, Any]], *, name: str, columns: tuple[str, ...]
) -> bool:
    return any(
        index.get("name") == name and tuple(index.get("column_names") or ()) == columns
        for index in indexes
    )


def _foreign_key_matches(foreign_keys: Iterable[dict[str, Any]]) -> bool:
    for foreign_key in foreign_keys:
        if foreign_key.get("name") != PARTS_USAGE_SOURCE_LINE_FOREIGN_KEY:
            continue
        if foreign_key.get("constrained_columns") != ["source_line_id"]:
            continue
        if foreign_key.get("referred_table") != "labor":
            continue
        if foreign_key.get("referred_columns") != ["id"]:
            continue
        if _normalise_action((foreign_key.get("options") or {}).get("ondelete")) == "SET NULL":
            return True
    return False


def collect_schema_issues(inspector: Any) -> list[str]:
    """Return all required-object mismatches without exposing connection details."""
    issues: list[str] = []

    parts_usage_columns = {column["name"] for column in inspector.get_columns("parts_usage")}
    if "source_line_id" not in parts_usage_columns:
        issues.append("missing required column parts_usage.source_line_id")

    parts_usage_indexes = inspector.get_indexes("parts_usage")
    if not _index_matches(
        parts_usage_indexes,
        name=PARTS_USAGE_SOURCE_LINE_INDEX,
        columns=("source_line_id",),
    ):
        issues.append(
            "missing required index parts_usage.ix_parts_usage_source_line_id(source_line_id)"
        )

    if not _foreign_key_matches(inspector.get_foreign_keys("parts_usage")):
        issues.append(
            "missing required foreign key "
            "fk_parts_usage_source_line_id_labor "
            "(parts_usage.source_line_id -> labor.id ON DELETE SET NULL)"
        )

    if not _index_matches(
        inspector.get_indexes("repair_orders"),
        name=REPAIR_ORDER_ACTIVE_LIST_INDEX,
        columns=("tenant_id", "created_at"),
    ):
        issues.append(
            "missing required active repair-order list index "
            "repair_orders.ix_repair_orders_tenant_created_at(tenant_id, created_at)"
        )

    provider_outbox_columns = {column["name"] for column in inspector.get_columns("provider_outbox")}
    required_provider_outbox_columns = {
        "tenant_id",
        "event_type",
        "aggregate_type",
        "aggregate_id",
        "payload",
        "idempotency_key",
        "status",
        "attempt_count",
        "available_at",
        "locked_until",
    }
    missing_provider_outbox_columns = required_provider_outbox_columns - provider_outbox_columns
    if missing_provider_outbox_columns:
        issues.append(
            "missing required provider_outbox columns "
            + ", ".join(sorted(missing_provider_outbox_columns))
        )

    if not _index_matches(
        inspector.get_indexes("provider_outbox"),
        name=PROVIDER_OUTBOX_DUE_INDEX,
        columns=("status", "available_at"),
    ):
        issues.append(
            "missing required provider outbox due index "
            "provider_outbox.ix_provider_outbox_due(status, available_at)"
        )

    return issues


def verify_database(connection: Connection, expected_heads: set[str]) -> None:
    """Validate the migration revision and the critical physical schema objects."""
    current_heads = set(MigrationContext.configure(connection).get_current_heads())
    issues: list[str] = []
    if current_heads != expected_heads:
        expected = ", ".join(sorted(expected_heads)) or "<none>"
        current = ", ".join(sorted(current_heads)) or "<none>"
        issues.append(f"Alembic revision mismatch (expected {expected}; found {current})")

    issues.extend(collect_schema_issues(inspect(connection)))
    if issues:
        raise SchemaPreflightError(issues)


def build_engine(database_url: str) -> Engine:
    """Build a one-shot, non-pooled inspection engine with a bounded connect time."""
    return create_engine(
        _sync_postgres_url(database_url),
        connect_args={"connect_timeout": 10},
        hide_parameters=True,
        poolclass=NullPool,
        pool_pre_ping=True,
    )


def run_preflight(database_url: str, alembic_config_path: Path = ALEMBIC_CONFIG_PATH) -> None:
    """Connect once, inspect the live database, then release the connection."""
    expected_heads = _load_expected_heads(alembic_config_path)
    engine = build_engine(database_url)
    try:
        with engine.connect() as connection:
            verify_database(connection, expected_heads)
    finally:
        engine.dispose()


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Schema preflight failed: DATABASE_URL is not configured.", file=sys.stderr)
        return 1

    try:
        run_preflight(database_url)
    except SchemaPreflightError as error:
        print("Schema preflight failed:", file=sys.stderr)
        for issue in error.issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    except (OSError, SQLAlchemyError):
        # SQLAlchemy errors can include database hostnames, users, or URLs. Keep
        # the deploy output actionable without leaking deployment credentials.
        print(
            "Schema preflight failed: unable to inspect the deployment database.",
            file=sys.stderr,
        )
        return 1

    print("Schema preflight passed: Alembic revision and required schema objects are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
