"""Private PostgreSQL source of truth for driver worker recovery.

The held connection owns a session advisory lock, but no long transaction or
application row lock. Every checkpoint commits independently of import sessions.
"""

import hashlib
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from scripts.motive_drivers.import_records import source_hash, validate

metadata = sa.MetaData()
runs = sa.Table(
    "motive_driver_worker_runs",
    metadata,
    sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
    sa.Column("worker_key", sa.String(120), nullable=False),
    sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("fleet_customer_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("company_id", sa.String(120), nullable=False),
    sa.Column("company_label", sa.String(255), nullable=False),
    sa.Column("mode", sa.String(16), nullable=False),
    sa.Column("source_sha256", sa.String(64), nullable=False),
    sa.Column(
        "source_document", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False
    ),
    sa.Column("attempt_document", sa.JSON().with_variant(JSONB, "postgresql")),
    sa.Column("attempt_sha256", sa.String(64)),
    sa.Column("stage", sa.String(20), nullable=False),
    sa.Column("receipts", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    ),
)


@dataclass(frozen=True)
class Identity:
    tenant_id: UUID
    actor_id: UUID
    customer_id: UUID
    company_id: str
    company_label: str

    @classmethod
    def from_environment(cls):
        company_id = os.environ["MOTIVE_COMPANY_ID"]
        company_label = os.environ["MOTIVE_COMPANY_LABEL"]
        if (
            not company_id.strip()
            or len(company_id) > 120
            or not company_label.strip()
            or len(company_label) > 255
        ):
            raise ValueError("Explicit driver company configuration required")
        return cls(
            UUID(os.environ["MOTIVE_SYNC_TENANT_ID"]),
            UUID(os.environ["MOTIVE_SYNC_ACTOR_ID"]),
            UUID(os.environ["MOTIVE_DRIVER_FLEET_CUSTOMER_ID"]),
            company_id,
            company_label,
        )

    def values(self):
        return {
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "fleet_customer_id": self.customer_id,
            "company_id": self.company_id,
            "company_label": self.company_label,
        }

    def receipt_identity(self, source_sha256):
        return {
            "tenant_id": str(self.tenant_id),
            "actor_id": str(self.actor_id),
            "expected_customer_id": str(self.customer_id),
            "company_id": self.company_id,
            "company_label": self.company_label,
            "source_sha256": source_sha256,
        }


def lock_key(worker_key):
    return int.from_bytes(
        hashlib.sha256(f"dieselbridge:driver-journal:{worker_key}".encode()).digest()[
            :8
        ],
        "big",
        signed=True,
    )


async def authorize_configuration(factory, identity):
    from app.db.models.customer import Customer
    from app.services.fleet_diagnostics import authorize

    # Application authority is checked in its own short transaction. Never
    # hold its FOR UPDATE locks in the durable journal connection.
    async with factory() as db:
        await authorize(db, identity.tenant_id, identity.actor_id)
        customer = await db.scalar(
            sa.select(Customer.id).where(
                Customer.id == identity.customer_id,
                Customer.tenant_id == identity.tenant_id,
                Customer.deleted_at.is_(None),
            )
        )
        if customer is None:
            raise ValueError("Configured driver fleet customer unavailable")
        await db.rollback()


@asynccontextmanager
async def database_journal(engine, identity, worker_key="motive-driver"):
    if engine.dialect.name != "postgresql":
        raise ValueError("Driver database journal requires PostgreSQL")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", worker_key):
        raise ValueError("Invalid stable driver worker key")
    async with engine.connect() as connection:
        held = await connection.scalar(
            sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key(worker_key)}
        )
        pid = await connection.scalar(sa.text("SELECT pg_backend_pid()"))
        await connection.commit()
        if not held:
            raise RuntimeError("Motive driver worker already running")
        try:
            journal = Journal(connection, identity, worker_key, backend_pid=pid)
            await journal.check_binding()
            yield journal
        finally:
            # A connection failure releases its server session lock. Do not
            # reconnect to unlock a different session or mask the original error.
            if not connection.invalidated:
                await connection.rollback()
                await connection.execute(
                    sa.text("SELECT pg_advisory_unlock(:key)"),
                    {"key": lock_key(worker_key)},
                )
                await connection.commit()


class Journal:
    def __init__(self, connection, identity, worker_key, *, backend_pid=None):
        self.connection = connection
        self.identity = identity
        self.worker_key = worker_key
        self.backend_pid = backend_pid

    async def _check_lock(self):
        if self.backend_pid is not None:
            pid = await self.connection.scalar(sa.text("SELECT pg_backend_pid()"))
            key = lock_key(self.worker_key)
            held = await self.connection.scalar(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype='advisory' AND pid=pg_backend_pid() AND granted AND classid=:high AND objid=:low AND objsubid=1)"
                ),
                {"high": (key & ((1 << 64) - 1)) >> 32, "low": key & ((1 << 32) - 1)},
            )
            if pid != self.backend_pid or not held:
                raise RuntimeError("Driver journal lock was lost")

    def _check_identity(self, row):
        if row["worker_key"] != self.worker_key or any(
            row[key] != value for key, value in self.identity.values().items()
        ):
            raise ValueError("Driver journal immutable identity mismatch")

    async def check_binding(self):
        async with self.connection.begin():
            await self._check_lock()
            rows = (
                await self.connection.execute(
                    sa.select(
                        runs.c.worker_key,
                        *(runs.c[key] for key in self.identity.values()),
                    )
                    .where(runs.c.worker_key == self.worker_key)
                    .distinct()
                )
            ).mappings()
            for row in rows:
                self._check_identity(row)

    async def create(self, document, *, commit=False):
        # Bound the retained artifact and reject non-JSON values before persistence.
        if len(json.dumps(document, allow_nan=False).encode()) > 16 * 1024 * 1024:
            raise ValueError("Driver source exceeds journal limit")
        validate(document, self.identity.company_label, self.identity.company_id)
        source_digest = source_hash(document)
        identity = self.identity.receipt_identity(source_digest)
        mode = "commit" if commit else "dry_run"
        receipt = {
            **identity,
            "mode": mode,
            "stage": "source_saved",
            "committed": False,
        }
        run_id = uuid4()
        await self.check_binding()
        async with self.connection.begin():
            await self._check_lock()
            await self.connection.execute(
                runs.insert().values(
                    id=run_id,
                    worker_key=self.worker_key,
                    **self.identity.values(),
                    mode=mode,
                    source_sha256=source_digest,
                    source_document=document,
                    stage="source_saved",
                    receipts=[receipt],
                )
            )
        return DurableRun(self, run_id)

    async def pending(self):
        await self.check_binding()
        async with self.connection.begin():
            await self._check_lock()
            ids = (
                (
                    await self.connection.execute(
                        sa.select(runs.c.id)
                        .where(
                            runs.c.worker_key == self.worker_key,
                            runs.c.mode == "commit",
                            runs.c.stage != "verified",
                        )
                        .order_by(runs.c.created_at, runs.c.id)
                    )
                )
                .scalars()
                .all()
            )
        return [DurableRun(self, run_id) for run_id in ids]

    async def _load(self, run_id):
        row = (
            (
                await self.connection.execute(
                    sa.select(runs).where(
                        runs.c.id == run_id, runs.c.worker_key == self.worker_key
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ValueError("Driver journal run unavailable")
        self._check_identity(row)
        if source_hash(row["source_document"]) != row["source_sha256"]:
            raise ValueError("Saved driver journal source changed")
        identity = self.identity.receipt_identity(row["source_sha256"])
        attempt = row["attempt_document"]
        if attempt is not None and (
            source_hash(attempt) != row["attempt_sha256"]
            or any(attempt.get(key) != value for key, value in identity.items())
        ):
            raise ValueError("Saved driver journal attempt changed")
        receipts = row["receipts"]
        if not receipts or receipts[-1].get("stage") != row["stage"]:
            raise ValueError("Saved driver journal receipt changed")
        for receipt in receipts:
            if (
                any(receipt.get(key) != value for key, value in identity.items())
                or receipt.get("mode") != row["mode"]
            ):
                raise ValueError("Saved driver journal receipt identity changed")
            if (
                receipt["stage"] != "source_saved"
                and receipt.get("attempt_sha256") != row["attempt_sha256"]
            ):
                raise ValueError("Saved driver journal receipt attempt changed")
        return row


class DurableRun:
    def __init__(self, journal, run_id):
        self.journal = journal
        self.id = run_id

    async def load(self):
        async with self.journal.connection.begin():
            await self.journal._check_lock()
            row = await self.journal._load(self.id)
            return {
                "source": row["source_document"],
                "attempt": row["attempt_document"],
                "receipt": row["receipts"][-1],
            }

    async def checkpoint(self, receipt, *, attempt=None):
        async with self.journal.connection.begin():
            await self.journal._check_lock()
            row = await self.journal._load(self.id)
            identity = self.journal.identity.receipt_identity(row["source_sha256"])
            if receipt.get("mode") != row["mode"] or any(
                receipt.get(key) != value for key, value in identity.items()
            ):
                raise ValueError("Driver checkpoint immutable identity mismatch")
            if row["stage"] == "verified":
                raise ValueError("Verified driver journal run is terminal")
            saved_attempt = row["attempt_document"]
            if attempt is not None:
                if any(
                    attempt.get(key) != value for key, value in identity.items()
                ) or (saved_attempt is not None and saved_attempt != attempt):
                    raise ValueError("Immutable driver journal attempt changed")
                saved_attempt = attempt
            if saved_attempt is None or receipt.get("attempt_sha256") != source_hash(
                saved_attempt
            ):
                raise ValueError("Driver checkpoint requires immutable attempt")
            allowed = {
                "source_saved": {"validated"},
                "validated": {"validated", "commit_pending"},
                "commit_pending": {"validated", "committed"},
                "committed": {"validated", "verified"},
            }
            if receipt.get("stage") not in allowed.get(row["stage"], set()):
                raise ValueError("Invalid driver journal phase")
            await self.journal.connection.execute(
                runs.update()
                .where(runs.c.id == self.id)
                .values(
                    attempt_document=saved_attempt,
                    attempt_sha256=source_hash(saved_attempt),
                    receipts=[*row["receipts"], receipt],
                    stage=receipt["stage"],
                    updated_at=sa.func.now(),
                )
            )
