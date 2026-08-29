"""Transactional primitives shared by DB-038 APIs and legacy inventory paths."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.inventory import Inventory
from app.db.models.parts_operations import InventoryMovement, PartsOperationIdempotency
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole

PARTS_READ_ROLES = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST})
PARTS_MUTATE_ROLES = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN})
IDEMPOTENCY_KEY = re.compile(r"^[ -~]{16,128}$")
MONEY = Decimal("0.01")


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def decimal_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def require_parts_role(user: User, *, mutate: bool) -> None:
    allowed = PARTS_MUTATE_ROLES if mutate else PARTS_READ_ROLES
    if user.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def require_parts_operations_enabled(db: AsyncSession, user: User) -> UUID:
    """Return only an active server-derived tenant or generic 404."""
    if not settings.PARTS_OPERATIONS_V1_ENABLED or not user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    tenant = (await db.execute(select(Tenant).where(
        Tenant.id == user.tenant_id,
        Tenant.is_active.is_(True),
        Tenant.deleted_at.is_(None),
        Tenant.parts_operations_enabled.is_(True),
    ))).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return tenant.id


def actor_name(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or user.email


async def apply_inventory_movement(
    db: AsyncSession,
    *,
    item: Inventory,
    quantity_delta: int,
    movement_type: str,
    actor: User | None,
    source_type: str | None = None,
    source_id: UUID | None = None,
    destination_type: str | None = None,
    destination_id: UUID | None = None,
    reason_code: str | None = None,
    note: str | None = None,
    idempotency_key: str | None = None,
    wac_after: Decimal | None = None,
    held_for_checkout: int | None = None,
) -> InventoryMovement:
    """Append the immutable on-hand ledger row and materialize the balance."""
    if quantity_delta == 0:
        raise ValueError("Inventory movement must be non-zero")
    before = int(item.stock_quantity or 0)
    after = before + quantity_delta
    if after < 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient stock")
    old_wac = decimal_money(item.cost or Decimal("0"))
    new_wac = decimal_money(wac_after if wac_after is not None else old_wac)
    movement = InventoryMovement(
        id=uuid4(),
        tenant_id=item.tenant_id,
        inventory_id=item.id,
        bucket="on_hand",
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        balance_before=before,
        balance_after=after,
        unit_cost_snapshot=old_wac,
        wac_before=old_wac,
        wac_after=new_wac,
        source_type=source_type,
        source_id=source_id,
        destination_type=destination_type,
        destination_id=destination_id,
        actor_user_id=actor.id if actor else None,
        actor_display_name_snapshot=actor_name(actor) if actor else None,
        reason_code=reason_code,
        note=note,
        idempotency_key=idempotency_key,
    )
    item.stock_quantity = after
    item.cost = new_wac
    item.stock_version = int(item.stock_version or 0) + 1
    db.add(movement)
    if held_for_checkout is None:
        held_for_checkout = 0
    available_to_sell = max(after - held_for_checkout, 0)
    # Activity is an immutable searchable index written atomically with the
    # authoritative movement and materialized balance.
    from app.services.part_activity_service import append_part_activity
    event_type = {
        "po_receipt": "stock.received",
        "repair_reservation": "stock.repair_reserved",
        "repair_release": "stock.repair_released",
        "counter_sale": "stock.counter_sale_completed",
        "counter_sale_return": "stock.counter_sale_returned",
    }.get(movement_type, "stock.adjusted")
    await append_part_activity(
        db, tenant_id=item.tenant_id, inventory_id=item.id,
        category="stock", event_type=event_type,
        idempotency_key=f"inventory_movement:{movement.id}:v1", actor=actor,
        source_type=source_type or "inventory_movement", source_id=source_id or movement.id,
        reason_code=reason_code, note=note,
        before={"stock_quantity": before}, after={"stock_quantity": after},
        stock={
            "physical_on_hand": after, "held_for_checkout": held_for_checkout,
            "available_to_sell": available_to_sell, "delta": quantity_delta,
            "bucket": "on_hand", "stock_version": int(item.stock_version),
        },
        money={
            "currency": "USD", "wac_before": str(old_wac), "wac_after": str(new_wac),
            "cost_before": str(old_wac), "cost_after": str(new_wac),
        },
    )
    return movement


def receipt_wac(*, old_balance: int, old_wac: Decimal, quantity: int, unit_cost: Decimal) -> Decimal:
    if old_balance < 0 or quantity <= 0 or unit_cost <= 0:
        raise ValueError("Invalid receipt WAC inputs")
    if old_balance == 0:
        return decimal_money(unit_cost)
    value = ((Decimal(old_balance) * Decimal(old_wac)) + (Decimal(quantity) * Decimal(unit_cost))) / Decimal(old_balance + quantity)
    return decimal_money(value)


def canonical_fingerprint(*, route: str, principal_id: UUID, payload: Any) -> str:
    encoded = json.dumps({"route": route, "principal": str(principal_id), "payload": payload}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def validate_idempotency_key(key: str | None) -> str:
    if not key or not IDEMPOTENCY_KEY.fullmatch(key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Idempotency-Key")
    return key


async def find_idempotent_response(
    db: AsyncSession, *, tenant_id: UUID, family: str, key: str, fingerprint: str,
    allow_incomplete_resume: bool = False,
) -> PartsOperationIdempotency | None:
    # There is no row to lock for a first request. PostgreSQL's transaction-
    # scoped advisory lock serializes the durable key's initial insert; after
    # the winner commits, a contender observes and replays that row.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        scope = f"db038:{tenant_id}:{family}:{key}"
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(scope))))
    record = (await db.execute(select(PartsOperationIdempotency).where(
        PartsOperationIdempotency.tenant_id == tenant_id,
        PartsOperationIdempotency.operation_family == family,
        PartsOperationIdempotency.idempotency_key == key,
    ).with_for_update())).scalar_one_or_none()
    if record and record.request_fingerprint != fingerprint:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency key conflict")
    if record and record.completed_at is None and not allow_incomplete_resume:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request in progress")
    return record


def begin_idempotency(*, tenant_id: UUID, family: str, key: str, fingerprint: str) -> PartsOperationIdempotency:
    return PartsOperationIdempotency(
        tenant_id=tenant_id, operation_family=family, idempotency_key=key, request_fingerprint=fingerprint,
    )


def complete_idempotency(record: PartsOperationIdempotency, *, status_code: int, body: dict[str, Any]) -> None:
    from datetime import datetime, timezone
    record.status_code = status_code
    record.response_body = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    record.completed_at = datetime.now(timezone.utc)
