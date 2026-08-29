"""Bounded, restartable DB-045 Activity backfill and reconciliation."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.inventory_lifecycle import PartActivityBackfillRun, PartActivityEvent
from app.db.models.parts_operations import (
    CoreObligation, InventoryMovement, PurchaseReceiptLine, VendorReturn,
    VendorReturnLine,
)
from app.db.models.tenant import Tenant
from app.db.session import AsyncSessionLocal
from app.services.part_activity_service import append_part_activity


PAYLOAD_VERSION = 1


@dataclass(frozen=True)
class BackfillResult:
    tenant_id: UUID
    run_id: UUID
    state: str
    source_counts: dict[str, int]
    inserted_counts: dict[str, int]
    duplicate_count: int
    checksum: str


async def latest_verified_backfill(db: AsyncSession, tenant_id: UUID) -> PartActivityBackfillRun | None:
    return (await db.execute(select(PartActivityBackfillRun).where(
        PartActivityBackfillRun.tenant_id == tenant_id,
        PartActivityBackfillRun.payload_version == PAYLOAD_VERSION,
        PartActivityBackfillRun.state == "verified",
    ).order_by(PartActivityBackfillRun.verified_at.desc(), PartActivityBackfillRun.id.desc()).limit(1))).scalar_one_or_none()


async def _lock_tenant(db: AsyncSession, tenant_id: UUID) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        scope = f"db045:activity-backfill:{tenant_id}:v{PAYLOAD_VERSION}"
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(scope))))


SOURCE_KINDS = ("baseline", "movement", "repair_usage", "receipt", "vendor_return", "core")
KEY_PREFIX = {
    "baseline": "part", "movement": "inventory_movement",
    "repair_usage": "repair_usage", "receipt": "purchase_receipt_line",
    "vendor_return": "vendor_return_line", "core": "core_obligation",
}
KEY_SUFFIX = {
    "baseline": "baseline:v1", "movement": "v1",
    "repair_usage": "current:v1", "receipt": "current:v1",
    "vendor_return": "current:v1", "core": "current:v1",
}


def _source_key(kind: str, row_id: UUID) -> str:
    return f"{KEY_PREFIX[kind]}:{row_id}:{KEY_SUFFIX[kind]}"


SourceIdentity = tuple[str, UUID, UUID, str, UUID, str]


def _canonical_origin(kind: str, origin: str) -> str:
    """Canonicalize only the truthful origins allowed for a source kind.

    A live writer can win the deterministic-key race before the backfill sees
    the same authoritative row.  That event and a backfill-created snapshot
    represent the same non-baseline source identity.  Baselines are different:
    they are explicit point-in-time captures and must never reconcile against
    a live or historical-source event.
    """
    if kind == "baseline":
        return "baseline" if origin == "baseline" else f"invalid:{origin}"
    if origin in {"live", "backfill_snapshot"}:
        return "live_or_backfill_snapshot"
    return f"invalid:{origin}"


def _source_identity(kind: str, row: Any) -> SourceIdentity:
    """Identity fields that prove an event represents its authoritative row."""
    key = _source_key(kind, row.id)
    if kind == "baseline":
        return (
            key, row.tenant_id, row.id, "inventory", row.id,
            _canonical_origin(kind, "baseline"),
        )
    if kind == "movement":
        return (
            key, row.tenant_id, row.inventory_id,
            row.source_type or "inventory_movement", row.source_id or row.id,
            _canonical_origin(kind, "backfill_snapshot"),
        )
    if kind == "repair_usage":
        return (
            key, row.tenant_id, row.inventory_id, "repair_order",
            row.repair_order_id, _canonical_origin(kind, "backfill_snapshot"),
        )
    if kind == "receipt":
        return (
            key, row.tenant_id, row.inventory_id, "purchase_receipt",
            row.purchase_receipt_id, _canonical_origin(kind, "backfill_snapshot"),
        )
    if kind == "vendor_return":
        return (
            key, row.tenant_id, row.inventory_id, "vendor_return",
            row.vendor_return_id, _canonical_origin(kind, "backfill_snapshot"),
        )
    return (
        key, row.tenant_id, row.inventory_id, "core_obligation", row.id,
        _canonical_origin(kind, "backfill_snapshot"),
    )


def _identity_bytes(identity: SourceIdentity) -> bytes:
    return "|".join(str(value) for value in identity).encode() + b"\n"


def _source_statement(kind: str, tenant_id: UUID, cutoff: datetime):
    if kind == "baseline":
        return select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.deleted_at.is_(None),
            Inventory.created_at <= cutoff,
        )
    if kind == "movement":
        return select(InventoryMovement).where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.occurred_at <= cutoff,
        )
    if kind == "repair_usage":
        return select(PartsUsage).where(
            PartsUsage.tenant_id == tenant_id,
            PartsUsage.deleted_at.is_(None),
            PartsUsage.created_at <= cutoff,
        )
    if kind == "receipt":
        return select(PurchaseReceiptLine).where(
            PurchaseReceiptLine.tenant_id == tenant_id,
            PurchaseReceiptLine.created_at <= cutoff,
        )
    if kind == "vendor_return":
        return select(VendorReturnLine).join(
            VendorReturn, VendorReturn.id == VendorReturnLine.vendor_return_id,
        ).where(
            VendorReturnLine.tenant_id == tenant_id,
            VendorReturnLine.deleted_at.is_(None),
            VendorReturnLine.created_at <= cutoff,
            VendorReturn.status.in_(("submitted", "shipped", "credited", "cancelled")),
        )
    if kind == "core":
        return select(CoreObligation).where(
            CoreObligation.tenant_id == tenant_id,
            CoreObligation.deleted_at.is_(None),
            CoreObligation.created_at <= cutoff,
        )
    raise ValueError(f"Unknown Activity source: {kind}")


async def _source_batch(
    db: AsyncSession, kind: str, tenant_id: UUID, cutoff: datetime,
    *, after_id: UUID | None, limit: int,
) -> list[Any]:
    statement = _source_statement(kind, tenant_id, cutoff)
    model = {
        "baseline": Inventory, "movement": InventoryMovement,
        "repair_usage": PartsUsage, "receipt": PurchaseReceiptLine,
        "vendor_return": VendorReturnLine, "core": CoreObligation,
    }[kind]
    if after_id is not None:
        statement = statement.where(model.id > after_id)
    return list((await db.execute(statement.order_by(model.id).limit(limit))).scalars().all())


async def _reconcile_source(
    db: AsyncSession, kind: str, tenant_id: UUID, cutoff: datetime,
    *, batch_size: int,
) -> tuple[int, str, int, str]:
    """Return bounded expected/present counts and deterministic checksums."""
    expected_hash = hashlib.sha256()
    present_hash = hashlib.sha256()
    expected_count = 0
    present_count = 0
    after_id: UUID | None = None
    while True:
        rows = await _source_batch(
            db, kind, tenant_id, cutoff, after_id=after_id, limit=batch_size,
        )
        if not rows:
            break
        identities = [_source_identity(kind, row) for row in rows]
        keys = [identity[0] for identity in identities]
        for identity in identities:
            expected_hash.update(_identity_bytes(identity))
        expected_count += len(identities)
        # ``scalars`` would discard the identity fields; keep complete rows and
        # hash them in the exact source-key order for a deterministic rerun.
        present_rows = list((await db.execute(select(
            PartActivityEvent.idempotency_key,
            PartActivityEvent.tenant_id,
            PartActivityEvent.inventory_id,
            PartActivityEvent.source_type,
            PartActivityEvent.source_id,
            PartActivityEvent.origin,
        ).where(
            PartActivityEvent.tenant_id == tenant_id,
            PartActivityEvent.idempotency_key.in_(keys),
        ))).all())
        present_by_key = {row.idempotency_key: row for row in present_rows}
        for key in keys:
            event = present_by_key.get(key)
            if event is not None:
                present_hash.update(_identity_bytes((
                    event.idempotency_key, event.tenant_id, event.inventory_id,
                    event.source_type, event.source_id,
                    _canonical_origin(kind, event.origin),
                )))
                present_count += 1
        after_id = rows[-1].id
    return expected_count, expected_hash.hexdigest(), present_count, present_hash.hexdigest()


async def _append_source(
    db: AsyncSession, kind: str, row: Any, *, baseline_captured_at: datetime,
) -> PartActivityEvent:
    if kind == "baseline":
        return await append_part_activity(
            db, tenant_id=row.tenant_id, inventory_id=row.id,
            category="catalog", event_type="part.baseline",
            idempotency_key=f"part:{row.id}:baseline:v1", origin="baseline",
            # This is the current catalog snapshot captured by this run, not a
            # reconstruction of state at the part's original creation date.
            occurred_at=baseline_captured_at,
            after={
                "sku": row.sku, "name": row.name, "description": row.description,
                "category": row.category, "category_id": row.category_id,
                "location": row.location, "unit_type": row.unit_type,
                "image_url": row.image_url, "reorder_level": row.reorder_level,
                "cost": Decimal(row.cost), "selling_price": Decimal(row.selling_price),
                "stock_quantity": int(row.stock_quantity or 0),
            },
            stock={"physical_on_hand": int(row.stock_quantity or 0), "held_for_checkout": 0, "available_to_sell": int(row.stock_quantity or 0), "delta": 0, "bucket": "on_hand", "stock_version": int(row.stock_version or 0)},
            money={"currency": "USD", "cost_after": str(row.cost), "list_price": str(row.selling_price)},
            source_type="inventory", source_id=row.id, source_number=row.sku,
        )
    if kind == "movement":
        return await append_part_activity(
            db, tenant_id=row.tenant_id, inventory_id=row.inventory_id,
            category="stock", event_type={
                "po_receipt": "stock.received", "repair_reservation": "stock.repair_reserved",
                "repair_release": "stock.repair_released", "counter_sale": "stock.counter_sale_completed",
                "counter_sale_return": "stock.counter_sale_returned",
            }.get(row.movement_type, "stock.adjusted"),
            idempotency_key=f"inventory_movement:{row.id}:v1", origin="backfill_snapshot",
            occurred_at=row.occurred_at, source_type=row.source_type or "inventory_movement",
            source_id=row.source_id or row.id, reason_code=row.reason_code, note=row.note,
            before={"stock_quantity": int(row.balance_before)}, after={"stock_quantity": int(row.balance_after)},
            stock={"physical_on_hand": int(row.balance_after), "held_for_checkout": 0, "available_to_sell": int(row.balance_after), "delta": int(row.quantity_delta), "bucket": row.bucket, "stock_version": None},
            money={"currency": "USD", "wac_before": str(row.wac_before) if row.wac_before is not None else None, "wac_after": str(row.wac_after) if row.wac_after is not None else None},
        )
    if kind == "repair_usage":
        return await append_part_activity(
            db, tenant_id=row.tenant_id, inventory_id=row.inventory_id,
            category="repairs", event_type="repair_usage.current_snapshot",
            idempotency_key=f"repair_usage:{row.id}:current:v1", origin="backfill_snapshot",
            occurred_at=row.updated_at, source_type="repair_order", source_id=row.repair_order_id,
            after={"quantity": str(row.quantity)},
            money={"currency": "USD", "charged_price": str(row.unit_price), "cost_after": str(row.unit_cost) if row.unit_cost is not None else None},
        )
    if kind == "receipt":
        return await append_part_activity(
            db, tenant_id=row.tenant_id, inventory_id=row.inventory_id,
            category="purchasing", event_type="receipt.current_snapshot",
            idempotency_key=f"purchase_receipt_line:{row.id}:current:v1", origin="backfill_snapshot",
            occurred_at=row.created_at, source_type="purchase_receipt", source_id=row.purchase_receipt_id,
            after={"quantity": int(row.quantity)},
            money={"currency": "USD", "cost_after": str(row.unit_cost), "wac_before": str(row.wac_before), "wac_after": str(row.wac_after)},
        )
    if kind == "vendor_return":
        return await append_part_activity(
            db, tenant_id=row.tenant_id, inventory_id=row.inventory_id,
            category="returns", event_type="vendor_return.current_snapshot",
            idempotency_key=f"vendor_return_line:{row.id}:current:v1", origin="backfill_snapshot",
            occurred_at=row.updated_at, source_type="vendor_return", source_id=row.vendor_return_id,
            after={"quantity": int(row.quantity)},
            money={"currency": "USD", "refund_allocations": str(row.actual_credit if row.actual_credit is not None else row.expected_credit)},
        )
    return await append_part_activity(
        db, tenant_id=row.tenant_id, inventory_id=row.inventory_id,
        category="purchasing", event_type="core.current_snapshot",
        idempotency_key=f"core_obligation:{row.id}:current:v1", origin="backfill_snapshot",
        occurred_at=row.updated_at, source_type="core_obligation", source_id=row.id,
        after={"quantity": int(row.quantity), "status": row.status},
        money={"currency": "USD", "cost_after": str(row.unit_core_value_snapshot)},
    )


async def backfill_tenant_activity(
    db: AsyncSession, tenant_id: UUID, *, batch_size: int = 500,
    dry_run: bool = False, verify_only: bool = False,
) -> BackfillResult:
    if not 1 <= batch_size <= 5000:
        raise ValueError("batch_size must be between 1 and 5000")
    await _lock_tenant(db, tenant_id)
    tenant = (await db.execute(select(Tenant).where(
        Tenant.id == tenant_id, Tenant.deleted_at.is_(None), Tenant.is_active.is_(True),
    ))).scalar_one_or_none()
    if tenant is None:
        raise ValueError("Tenant not found")
    cutoff = datetime.now(timezone.utc)
    latest = (await db.execute(select(PartActivityBackfillRun).where(
        PartActivityBackfillRun.tenant_id == tenant_id,
        PartActivityBackfillRun.payload_version == PAYLOAD_VERSION,
    ).order_by(PartActivityBackfillRun.created_at.desc()).limit(1))).scalar_one_or_none()
    if verify_only:
        if latest is None:
            raise ValueError("No Activity backfill run exists")
        cutoff = latest.cutoff_at
        run = latest
    elif not dry_run and latest is not None and latest.state in {"running", "failed", "reconciled"}:
        # Resume an interrupted payload-version run at its original cutoff.
        # Failed reconciliation replays from the beginning; deterministic
        # idempotency keys make that safe and allow a missing row to heal.
        run = latest
        cutoff = run.cutoff_at
        if run.state == "failed":
            run.batch_cursor = None
            run.error_summary = None
        if run.state == "reconciled":
            verify_only = True
        else:
            run.state = "running"
        await db.commit()
        await _lock_tenant(db, tenant_id)
    else:
        run = PartActivityBackfillRun(
            tenant_id=tenant_id, payload_version=PAYLOAD_VERSION, cutoff_at=cutoff,
            state="running", source_counts={}, inserted_counts={}, replayed_counts={},
            source_checksums={}, duplicate_count=0,
        )
        db.add(run)
        await db.flush()
        # Persist the run identity and cutoff before the first data batch so a
        # process interruption has a durable resume target.
        if not dry_run:
            await db.commit()
            await _lock_tenant(db, tenant_id)
    source_counts: dict[str, int] = {}
    source_checksums: dict[str, str] = {}
    for kind in SOURCE_KINDS:
        count, checksum, _present, _present_checksum = await _reconcile_source(
            db, kind, tenant_id, cutoff, batch_size=batch_size,
        )
        source_counts[kind] = count
        source_checksums[kind] = checksum
    checksum = hashlib.sha256("\n".join(
        f"{kind}:{source_checksums[kind]}" for kind in SOURCE_KINDS
    ).encode()).hexdigest()
    if dry_run:
        await db.rollback()
        return BackfillResult(tenant_id, run.id, "reconciled", source_counts, {}, 0, checksum)
    inserted_counts: dict[str, int] = {
        key: int(value) for key, value in (run.inserted_counts or {}).items()
    }
    replayed_counts: dict[str, int] = {
        key: int(value) for key, value in (run.replayed_counts or {}).items()
        if key in SOURCE_KINDS
    }
    duplicate_count = int(run.duplicate_count or 0)
    if not verify_only:
        resume_kind: str | None = None
        resume_id: UUID | None = None
        if run.batch_cursor:
            try:
                resume_kind, raw_id = run.batch_cursor.split(":", 1)
                if resume_kind not in SOURCE_KINDS:
                    raise ValueError
                resume_id = UUID(raw_id)
            except (TypeError, ValueError):
                raise RuntimeError("Invalid Activity backfill batch cursor")
        reached_resume = resume_kind is None
        for kind in SOURCE_KINDS:
            if not reached_resume:
                if kind != resume_kind:
                    continue
                reached_resume = True
            after_id = resume_id if kind == resume_kind else None
            inserted = int(inserted_counts.get(kind, 0))
            replayed = int(replayed_counts.get(kind, 0))
            while True:
                rows = await _source_batch(
                    db, kind, tenant_id, cutoff,
                    after_id=after_id, limit=batch_size,
                )
                if not rows:
                    break
                keys = [_source_key(kind, row.id) for row in rows]
                existing_keys = set((await db.execute(select(PartActivityEvent.idempotency_key).where(
                    PartActivityEvent.tenant_id == tenant_id,
                    PartActivityEvent.idempotency_key.in_(keys),
                ))).scalars().all())
                for row, key in zip(rows, keys):
                    await _append_source(
                        db, kind, row, baseline_captured_at=cutoff,
                    )
                    if key in existing_keys:
                        replayed += 1
                    else:
                        inserted += 1
                after_id = rows[-1].id
                run.batch_cursor = f"{kind}:{after_id}"
                inserted_counts[kind] = inserted
                replayed_counts[kind] = replayed
                run.inserted_counts = dict(inserted_counts)
                run.replayed_counts = dict(replayed_counts)
                run.duplicate_count = duplicate_count
                # Each bounded batch is an atomic checkpoint. A crash loses at
                # most the active batch and the next invocation resumes it.
                await db.commit()
                await _lock_tenant(db, tenant_id)
            inserted_counts[kind] = inserted
            replayed_counts[kind] = replayed
            resume_id = None
    present_counts: dict[str, int] = {}
    present_checksums: dict[str, str] = {}
    for kind in SOURCE_KINDS:
        expected, expected_checksum, present, present_checksum = await _reconcile_source(
            db, kind, tenant_id, cutoff, batch_size=batch_size,
        )
        source_counts[kind] = expected
        source_checksums[kind] = expected_checksum
        present_counts[kind] = present
        present_checksums[kind] = present_checksum
    failed_sources = [
        kind for kind in SOURCE_KINDS
        if source_counts[kind] != present_counts[kind]
        or source_checksums[kind] != present_checksums[kind]
    ]
    if failed_sources:
        run.state = "failed"
        run.error_summary = (
            "Activity source/event reconciliation failed: "
            + ", ".join(failed_sources)
        )
        await db.commit()
        raise RuntimeError(run.error_summary)
    checksum = hashlib.sha256("\n".join(
        f"{kind}:{source_checksums[kind]}" for kind in SOURCE_KINDS
    ).encode()).hexdigest()
    now = datetime.now(timezone.utc)
    run.source_counts = source_counts
    run.inserted_counts = inserted_counts
    run.replayed_counts = {**replayed_counts, "present": sum(present_counts.values())}
    run.source_checksums = {**source_checksums, "all": checksum}
    run.duplicate_count = duplicate_count
    run.state = "reconciled"
    run.reconciled_at = now
    await db.commit()
    # Verification is intentionally a distinct durable transition. A process
    # interruption here resumes this exact run without replaying source rows.
    run.state = "verified"
    run.verified_at = now
    run.error_summary = None
    await db.commit()
    return BackfillResult(tenant_id, run.id, run.state, source_counts, inserted_counts, duplicate_count, checksum)


async def run_activity_backfill(
    *, tenant_id: UUID | None = None, batch_size: int = 500,
    dry_run: bool = False, verify_only: bool = False,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> list[BackfillResult]:
    async with session_factory() as db:
        ids = [tenant_id] if tenant_id else list((await db.execute(select(Tenant.id).where(
            Tenant.deleted_at.is_(None), Tenant.is_active.is_(True),
        ).order_by(Tenant.id))).scalars().all())
    results: list[BackfillResult] = []
    for current_id in ids:
        async with session_factory() as db:
            results.append(await backfill_tenant_activity(
                db, current_id, batch_size=batch_size, dry_run=dry_run,
                verify_only=verify_only,
            ))
    return results
