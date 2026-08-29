"""Bounded manual counter-sale domain service for DB-045.

This module intentionally has no card provider, reservation worker, accounting
outbox, email receipt, or provider reconciliation seam. A checkout is a single
tenant-scoped database transaction: lock stock, record the manual tender,
decrement on-hand, append Activity, and complete the occasional walk-in sale.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Iterable
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory
from app.db.models.inventory_lifecycle import (
    CounterSale,
    CounterSaleLine,
    CounterSalePaymentAttempt,
    CounterSaleReturn,
    CounterSaleReturnLine,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.part_activity_backfill import latest_verified_backfill
from app.services.part_activity_service import append_part_activity
from app.services.parts_operations_service import apply_inventory_movement


READ_ROLES = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST})
MANAGER_ROLES = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN})
MANUAL_TENDERS = frozenset({"cash", "check", "ach", "zelle", "external_terminal", "fleet_reference", "other"})
MONEY = Decimal("0.01")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Decimal | str | int | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def require_counter_sale_role(user: User, *, manager: bool = False) -> None:
    if user.role not in (MANAGER_ROLES if manager else READ_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def require_counter_sales_enabled(db: AsyncSession, user: User) -> tuple[Tenant, list[str]]:
    """Resolve rollout gates from server state; disabled and foreign paths stay generic."""
    if not settings.COUNTER_SALES_ENABLED or not settings.PARTS_OPERATIONS_V1_ENABLED or not user.tenant_id:
        raise _not_found()
    tenant = (await db.execute(select(Tenant).where(
        Tenant.id == user.tenant_id,
        Tenant.deleted_at.is_(None),
        Tenant.is_active.is_(True),
        Tenant.parts_operations_enabled.is_(True),
        Tenant.counter_sales_enabled.is_(True),
    ))).scalar_one_or_none()
    if tenant is None or await latest_verified_backfill(db, tenant.id) is None:
        raise _not_found()
    require_counter_sale_role(user)
    return tenant, sorted(MANUAL_TENDERS)


async def counter_sale_capabilities(db: AsyncSession, user: User) -> dict[str, Any]:
    try:
        _tenant, tenders = await require_counter_sales_enabled(db, user)
    except HTTPException:
        return {"counter_sales": False, "counter_sale_tenders": []}
    return {"counter_sales": True, "counter_sale_tenders": tenders}


async def _tenant_customer(db: AsyncSession, tenant_id: UUID, customer_id: UUID | None) -> Customer | None:
    if customer_id is None:
        return None
    row = (await db.execute(select(Customer).where(
        Customer.id == customer_id,
        Customer.tenant_id == tenant_id,
        Customer.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if row is None:
        raise _not_found()
    return row


async def _tenant_parts(
    db: AsyncSession,
    tenant_id: UUID,
    ids: Iterable[UUID],
    *,
    lock: bool = False,
) -> dict[UUID, Inventory]:
    unique_ids = sorted(set(ids), key=str)
    if not unique_ids:
        return {}
    stmt = select(Inventory).where(
        Inventory.tenant_id == tenant_id,
        Inventory.id.in_(unique_ids),
        Inventory.deleted_at.is_(None),
        Inventory.is_placeholder.is_(False),
    ).order_by(Inventory.id)
    if lock:
        stmt = stmt.with_for_update()
    rows = list((await db.execute(stmt)).scalars().all())
    if len(rows) != len(unique_ids):
        raise _not_found()
    return {row.id: row for row in rows}


async def _next_sale_number(db: AsyncSession, tenant_id: UUID) -> str:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"db045:sale-number:{tenant_id}"))))
    numbers = list((await db.execute(select(CounterSale.sale_number).where(
        CounterSale.tenant_id == tenant_id,
    ))).scalars().all())
    latest = max((
        int(value.rsplit("-", 1)[-1])
        for value in numbers
        if value.startswith("CS-") and value.rsplit("-", 1)[-1].isdigit()
    ), default=0)
    return f"CS-{latest + 1:06d}"


def _allocate_cents(total: Decimal, weights: list[Decimal], stable_ids: list[UUID]) -> list[Decimal]:
    cents = int((money(total) * 100).to_integral_value())
    if cents == 0 or not weights or sum(weights, Decimal("0")) <= 0:
        return [Decimal("0.00") for _ in weights]
    weight_sum = sum(weights, Decimal("0"))
    raw = [Decimal(cents) * weight / weight_sum for weight in weights]
    floors = [int(value.to_integral_value(rounding=ROUND_DOWN)) for value in raw]
    remainder = cents - sum(floors)
    order = sorted(
        range(len(raw)),
        key=lambda index: (-(raw[index] - Decimal(floors[index])), str(stable_ids[index])),
    )
    for index in order[:remainder]:
        floors[index] += 1
    return [Decimal(value) / Decimal("100") for value in floors]


def _unit_cents(total: Decimal, quantity: int) -> list[Decimal]:
    cents = int((money(total) * 100).to_integral_value())
    quotient, remainder = divmod(cents, quantity)
    return [Decimal(quotient + (1 if index < remainder else 0)) / Decimal("100") for index in range(quantity)]


def price_sale(sale: CounterSale, lines: list[CounterSaleLine]) -> None:
    list_values = [money(line.list_unit_price * line.quantity) for line in lines]
    charged_values = [money(line.charged_unit_price * line.quantity) for line in lines]
    sale.list_subtotal = money(sum(list_values, Decimal("0")))
    sale.charged_subtotal = money(sum(charged_values, Decimal("0")))
    sale.discount_total = money(sale.list_subtotal - sale.charged_subtotal)
    sale.tax_total = money(sale.charged_subtotal * Decimal(sale.tax_rate_snapshot) / Decimal("100"))
    sale.total = money(sale.charged_subtotal + sale.tax_total)
    tax_allocations = _allocate_cents(sale.tax_total, charged_values, [line.id for line in lines])
    for line, list_value, charged_value, tax in zip(lines, list_values, charged_values, tax_allocations):
        line.discount_total = money(list_value - charged_value)
        line.item_subtotal = charged_value
        line.tax_allocation = tax
        line.total = money(charged_value + tax)
        line.cost_total = money(line.unit_cost * line.quantity)
        item_units = _unit_cents(charged_value, line.quantity)
        discount_units = _unit_cents(line.discount_total, line.quantity)
        tax_units = _unit_cents(tax, line.quantity)
        cost_units = _unit_cents(line.cost_total, line.quantity)
        line.unit_allocations = [
            {
                "ordinal": index + 1,
                "item": str(item_units[index]),
                "discount": str(discount_units[index]),
                "tax": str(tax_units[index]),
                "cost": str(cost_units[index]),
            }
            for index in range(line.quantity)
        ]


async def create_or_replace_draft(
    db: AsyncSession,
    *,
    tenant: Tenant,
    actor: User,
    sale: CounterSale | None,
    customer_id: UUID | None,
    buyer_name: str | None,
    buyer_email: str | None,
    buyer_phone: str | None,
    line_inputs: list[dict[str, Any]],
) -> tuple[CounterSale, list[CounterSaleLine]]:
    if not line_inputs or len(line_inputs) > 100:
        raise _unprocessable("A counter sale requires 1-100 lines")
    customer = await _tenant_customer(db, tenant.id, customer_id)
    if customer:
        buyer_name = (customer.company_name or f"{customer.first_name} {customer.last_name}").strip()
        buyer_email = customer.email
        buyer_phone = customer.phone
    parts = await _tenant_parts(db, tenant.id, [line["inventory_id"] for line in line_inputs])
    is_new = sale is None
    if sale is None:
        sale = CounterSale(
            id=uuid4(),
            tenant_id=tenant.id,
            sale_number=await _next_sale_number(db, tenant.id),
            status="draft",
            version=1,
            currency="USD",
            customer_id=customer_id,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
            tax_rate_snapshot=Decimal(tenant.sales_tax_rate or 0),
        )
        db.add(sale)
    elif sale.status != "draft":
        raise _conflict("Only draft sales can be edited")
    sale.customer_id = customer_id
    sale.buyer_name_snapshot = (buyer_name or "").strip() or None
    sale.buyer_email_snapshot = (buyer_email or "").strip() or None
    sale.buyer_phone_snapshot = (buyer_phone or "").strip() or None
    sale.updated_by_user_id = actor.id
    existing = list((await db.execute(select(CounterSaleLine).where(
        CounterSaleLine.tenant_id == tenant.id,
        CounterSaleLine.sale_id == sale.id,
        CounterSaleLine.deleted_at.is_(None),
    ))).scalars().all())
    for row in existing:
        row.deleted_at = now_utc()
    lines: list[CounterSaleLine] = []
    seen: set[UUID] = set()
    for request in line_inputs:
        part = parts[request["inventory_id"]]
        if part.id in seen:
            raise _unprocessable("Each part may appear only once")
        seen.add(part.id)
        quantity = int(request["quantity"])
        if quantity <= 0:
            raise _unprocessable("Quantity must be a positive whole package")
        catalog = money(part.selling_price)
        if catalog <= 0:
            raise _unprocessable("A catalog selling price is required")
        requested_price = request.get("charged_unit_price")
        charged = catalog if requested_price is None else money(requested_price)
        reason = " ".join(str(request.get("price_override_reason") or "").split())
        if charged <= 0:
            raise _unprocessable("Charged unit price must be positive")
        if charged != catalog:
            require_counter_sale_role(actor, manager=True)
            if not 3 <= len(reason) <= 500:
                raise _unprocessable("Manager price override reason is required")
        row = CounterSaleLine(
            id=uuid4(),
            tenant_id=tenant.id,
            sale_id=sale.id,
            inventory_id=part.id,
            quantity=quantity,
            sku_snapshot=part.sku,
            name_snapshot=part.name,
            unit_snapshot=part.unit_type,
            category_snapshot=part.category,
            unit_cost=money(part.cost),
            list_unit_price=catalog,
            charged_unit_price=charged,
            price_override_reason=reason or None,
            price_override_actor_id=actor.id if charged != catalog else None,
            item_subtotal=Decimal("0"),
            total=Decimal("0"),
            cost_total=Decimal("0"),
        )
        db.add(row)
        lines.append(row)
    price_sale(sale, lines)
    if not is_new:
        sale.version += 1
    await db.flush()
    for line in lines:
        await append_part_activity(
            db,
            tenant_id=tenant.id,
            inventory_id=line.inventory_id,
            category="sales",
            event_type="counter_sale.created" if is_new else "counter_sale.updated",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:draft:v{sale.version}",
            actor=actor,
            correlation_id=sale.id,
            source_type="counter_sale",
            source_id=sale.id,
            source_number=sale.sale_number,
            after={"quantity": line.quantity, "status": sale.status},
            money={
                "currency": "USD",
                "list_price": str(line.list_unit_price),
                "charged_price": str(line.charged_unit_price),
                "discount": str(line.discount_total),
                "item_subtotal": str(line.item_subtotal),
                "tax": str(line.tax_allocation),
                "total": str(line.total),
                "cost_basis": str(line.cost_total),
            },
        )
    return sale, lines


async def tenant_sale(db: AsyncSession, tenant_id: UUID, sale_id: UUID, *, lock: bool = False) -> CounterSale:
    stmt = select(CounterSale).where(
        CounterSale.id == sale_id,
        CounterSale.tenant_id == tenant_id,
        CounterSale.deleted_at.is_(None),
    )
    if lock:
        stmt = stmt.with_for_update()
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _not_found()
    return row


async def sale_lines(db: AsyncSession, tenant_id: UUID, sale_id: UUID, *, lock: bool = False) -> list[CounterSaleLine]:
    stmt = select(CounterSaleLine).where(
        CounterSaleLine.tenant_id == tenant_id,
        CounterSaleLine.sale_id == sale_id,
        CounterSaleLine.deleted_at.is_(None),
    ).order_by(CounterSaleLine.id)
    if lock:
        stmt = stmt.with_for_update()
    return list((await db.execute(stmt)).scalars().all())


def build_receipt_snapshot(
    sale: CounterSale,
    lines: list[CounterSaleLine],
    payment: CounterSalePaymentAttempt,
) -> dict[str, Any]:
    return {
        "sale_number": sale.sale_number,
        "completed_at": sale.completed_at.isoformat() if sale.completed_at else None,
        "buyer": {
            "name": sale.buyer_name_snapshot,
            "email": sale.buyer_email_snapshot,
            "phone": sale.buyer_phone_snapshot,
        },
        "currency": "USD",
        "lines": [
            {
                "sku": line.sku_snapshot,
                "name": line.name_snapshot,
                "quantity": line.quantity,
                "unit_price": str(line.charged_unit_price),
                "item": str(line.item_subtotal),
                "tax": str(line.tax_allocation),
                "total": str(line.total),
            }
            for line in lines
        ],
        "subtotal": str(sale.charged_subtotal),
        "tax": str(sale.tax_total),
        "total": str(sale.total),
        "tender": payment.tender,
        "payment_reference": payment.external_reference,
    }


async def complete_manual_checkout(
    db: AsyncSession,
    *,
    tenant: Tenant,
    sale_id: UUID,
    actor: User,
    expected_version: int,
    tender: str,
    idempotency_key: str,
    manual_reference: str | None,
) -> CounterSale:
    if tender not in MANUAL_TENDERS:
        raise _unprocessable("Only manual tenders are supported")
    reference = (manual_reference or "").strip() or None
    sale = await tenant_sale(db, tenant.id, sale_id, lock=True)
    if sale.status != "draft" or sale.version != expected_version:
        raise _conflict("Counter sale version or state conflict")
    lines = await sale_lines(db, tenant.id, sale.id, lock=True)
    if not lines:
        raise _unprocessable("Counter sale has no lines")
    parts = await _tenant_parts(db, tenant.id, [line.inventory_id for line in lines], lock=True)
    for line in lines:
        if int(parts[line.inventory_id].stock_quantity or 0) < line.quantity:
            raise _conflict("Insufficient stock")
    price_sale(sale, lines)
    if sale.total <= 0:
        raise _unprocessable("Counter sale total must be positive")
    fingerprint = hashlib.sha256(json.dumps({
        "sale": str(sale.id),
        "version": sale.version,
        "tender": tender,
        "total": str(sale.total),
        "reference": reference,
    }, sort_keys=True).encode()).hexdigest()
    payment = CounterSalePaymentAttempt(
        id=uuid4(),
        tenant_id=tenant.id,
        sale_id=sale.id,
        tender=tender,
        state="succeeded",
        amount=sale.total,
        request_fingerprint=fingerprint,
        idempotency_key=idempotency_key,
        external_reference=reference,
        actor_user_id=actor.id,
    )
    db.add(payment)
    for line in lines:
        part = parts[line.inventory_id]
        await apply_inventory_movement(
            db,
            item=part,
            quantity_delta=-line.quantity,
            movement_type="counter_sale",
            actor=actor,
            source_type="counter_sale",
            source_id=sale.id,
            reason_code="manual_counter_sale",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:movement:v1",
            held_for_checkout=0,
        )
        await append_part_activity(
            db,
            tenant_id=tenant.id,
            inventory_id=line.inventory_id,
            category="sales",
            event_type="counter_sale.completed",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:completed:v1",
            actor=actor,
            correlation_id=payment.id,
            source_type="counter_sale",
            source_id=sale.id,
            source_number=sale.sale_number,
            before={"status": "draft"},
            after={"status": "completed", "quantity": line.quantity},
            money={
                "currency": "USD",
                "list_price": str(line.list_unit_price),
                "charged_price": str(line.charged_unit_price),
                "discount": str(line.discount_total),
                "item_subtotal": str(line.item_subtotal),
                "tax": str(line.tax_allocation),
                "total": str(line.total),
                "cost_basis": str(line.cost_total),
            },
            payment={"tender": tender, "state": "succeeded", "external_reference": reference},
        )
    sale.status = "completed"
    sale.version += 1
    sale.completed_at = now_utc()
    sale.completed_by_user_id = actor.id
    sale.receipt_snapshot = build_receipt_snapshot(sale, lines, payment)
    return sale


async def cancel_draft(
    db: AsyncSession,
    *,
    tenant: Tenant,
    sale_id: UUID,
    actor: User,
    expected_version: int,
    reason: str,
) -> CounterSale:
    require_counter_sale_role(actor, manager=True)
    sale = await tenant_sale(db, tenant.id, sale_id, lock=True)
    if sale.status != "draft" or sale.version != expected_version:
        raise _conflict("Counter sale version or state conflict")
    sale.status = "cancelled"
    sale.version += 1
    sale.cancelled_at = now_utc()
    sale.cancelled_by_user_id = actor.id
    for line in await sale_lines(db, tenant.id, sale.id):
        await append_part_activity(
            db,
            tenant_id=tenant.id,
            inventory_id=line.inventory_id,
            category="sales",
            event_type="counter_sale.cancelled",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:cancelled:v1",
            actor=actor,
            correlation_id=sale.id,
            source_type="counter_sale",
            source_id=sale.id,
            source_number=sale.sale_number,
            before={"status": "draft"},
            after={"status": "cancelled"},
            reason_code="manager_cancel",
            note=reason,
        )
    return sale


async def complete_manual_return(
    db: AsyncSession,
    *,
    tenant: Tenant,
    sale_id: UUID,
    actor: User,
    expected_version: int,
    line_inputs: list[dict[str, Any]],
    manual_reference: str | None,
) -> tuple[CounterSale, CounterSaleReturn]:
    require_counter_sale_role(actor, manager=True)
    sale = await tenant_sale(db, tenant.id, sale_id, lock=True)
    if sale.status not in {"completed", "partially_returned"} or sale.version != expected_version:
        raise _conflict("Counter sale version or return state conflict")
    if not line_inputs:
        raise _unprocessable("Return requires at least one line")
    requested_ids = [row["sale_line_id"] for row in line_inputs]
    if len(set(requested_ids)) != len(requested_ids):
        raise _unprocessable("Each sale line may appear only once per return")
    lines = {line.id: line for line in await sale_lines(db, tenant.id, sale.id, lock=True)}
    previous = list((await db.execute(select(CounterSaleReturnLine).join(
        CounterSaleReturn,
        CounterSaleReturn.id == CounterSaleReturnLine.return_id,
    ).where(
        CounterSaleReturnLine.tenant_id == tenant.id,
        CounterSaleReturn.sale_id == sale.id,
        CounterSaleReturn.state == "completed",
        CounterSaleReturnLine.deleted_at.is_(None),
    ).with_for_update())).scalars().all())
    claimed: dict[UUID, set[int]] = {}
    for row in previous:
        claimed.setdefault(row.sale_line_id, set()).update(int(value) for value in (row.unit_ordinals or []))
    return_row = CounterSaleReturn(
        id=uuid4(),
        tenant_id=tenant.id,
        sale_id=sale.id,
        version=1,
        state="completed",
        item_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        refund_amount=Decimal("0"),
        created_by_user_id=actor.id,
        reason="; ".join(" ".join(str(row.get("reason") or "").split()) for row in line_inputs),
        refund_reference=(manual_reference or "").strip() or None,
        correlation_id=uuid4(),
        completed_at=now_utc(),
    )
    db.add(return_row)
    created: list[CounterSaleReturnLine] = []
    parts = await _tenant_parts(
        db,
        tenant.id,
        [lines[row["sale_line_id"]].inventory_id for row in line_inputs if row["sale_line_id"] in lines],
        lock=True,
    )
    for request in line_inputs:
        line = lines.get(request["sale_line_id"])
        if line is None:
            raise _not_found()
        quantity = int(request["quantity"])
        reason = " ".join(str(request.get("reason") or "").split())
        disposition = request.get("disposition")
        if quantity <= 0 or not 3 <= len(reason) <= 500 or disposition not in {"restock", "damaged"}:
            raise _unprocessable("Invalid return line")
        available = [
            int(entry["ordinal"])
            for entry in (line.unit_allocations or [])
            if int(entry["ordinal"]) not in claimed.get(line.id, set())
        ]
        if len(available) < quantity:
            raise _conflict("Return quantity exceeds remaining units")
        ordinals = available[:quantity]
        entries = [entry for entry in (line.unit_allocations or []) if int(entry["ordinal"]) in ordinals]
        item_amount = money(sum((Decimal(entry["item"]) for entry in entries), Decimal("0")))
        discount_amount = money(sum((Decimal(entry["discount"]) for entry in entries), Decimal("0")))
        tax_amount = money(sum((Decimal(entry["tax"]) for entry in entries), Decimal("0")))
        cost_amount = money(sum((Decimal(entry["cost"]) for entry in entries), Decimal("0")))
        row = CounterSaleReturnLine(
            tenant_id=tenant.id,
            return_id=return_row.id,
            sale_line_id=line.id,
            quantity=quantity,
            reason=reason,
            disposition=disposition,
            item_amount=item_amount,
            discount_amount=discount_amount,
            tax_amount=tax_amount,
            cost_amount=cost_amount,
            unit_ordinals=ordinals,
        )
        db.add(row)
        created.append(row)
        return_row.item_amount += item_amount
        return_row.tax_amount += tax_amount
        if disposition == "restock":
            await apply_inventory_movement(
                db,
                item=parts[line.inventory_id],
                quantity_delta=quantity,
                movement_type="counter_sale_return",
                actor=actor,
                source_type="counter_sale",
                source_id=sale.id,
                reason_code="manual_counter_sale_return",
                note=reason,
                idempotency_key=f"counter_sale_return:{return_row.id}:line:{line.id}:movement:v1",
                held_for_checkout=0,
            )
        await append_part_activity(
            db,
            tenant_id=tenant.id,
            inventory_id=line.inventory_id,
            category="sales",
            event_type="counter_sale.return_completed",
            idempotency_key=f"counter_sale_return:{return_row.id}:line:{line.id}:completed:v1",
            actor=actor,
            correlation_id=return_row.correlation_id,
            source_type="counter_sale",
            source_id=sale.id,
            source_number=sale.sale_number,
            before={"status": sale.status},
            after={"status": "completed", "quantity": quantity, "disposition": disposition},
            money={
                "currency": "USD",
                "refund_allocations": {
                    "item": str(item_amount),
                    "tax": str(tax_amount),
                    "total": str(money(item_amount + tax_amount)),
                },
            },
            payment={
                "state": "manual_refund_recorded",
                "external_reference": return_row.refund_reference,
            },
            reason_code="manual_return",
            note=reason,
        )
    return_row.refund_amount = money(return_row.item_amount + return_row.tax_amount)
    total_returned = sum(row.quantity for row in previous) + sum(row.quantity for row in created)
    total_sold = sum(line.quantity for line in lines.values())
    sale.status = "returned" if total_returned >= total_sold else "partially_returned"
    sale.version += 1
    return sale, return_row


def serialize_line(line: CounterSaleLine, *, returned_quantity: int = 0) -> dict[str, Any]:
    return {
        "id": str(line.id),
        "inventory_id": str(line.inventory_id),
        "quantity": line.quantity,
        "sku": line.sku_snapshot,
        "name": line.name_snapshot,
        "unit_type": line.unit_snapshot,
        "returned_quantity": returned_quantity,
        "remaining_returnable_quantity": max(line.quantity - returned_quantity, 0),
        "unit_cost": str(money(line.unit_cost)),
        "list_unit_price": str(money(line.list_unit_price)),
        "charged_unit_price": str(money(line.charged_unit_price)),
        "discount_amount": str(money(line.discount_total)),
        "item_subtotal": str(money(line.item_subtotal)),
        "tax_amount": str(money(line.tax_allocation)),
        "total_amount": str(money(line.total)),
        "price_override_reason": line.price_override_reason,
    }


async def serialize_return(db: AsyncSession, row: CounterSaleReturn) -> dict[str, Any]:
    lines = list((await db.execute(select(CounterSaleReturnLine).where(
        CounterSaleReturnLine.tenant_id == row.tenant_id,
        CounterSaleReturnLine.return_id == row.id,
        CounterSaleReturnLine.deleted_at.is_(None),
    ))).scalars().all())
    return {
        "id": str(row.id),
        "sale_id": str(row.sale_id),
        "version": row.version,
        "state": row.state,
        "item_amount": str(money(row.item_amount)),
        "tax_amount": str(money(row.tax_amount)),
        "refund_amount": str(money(row.refund_amount)),
        "reason": row.reason,
        "refund_reference": row.refund_reference,
        "lines": [{
            "id": str(line.id),
            "sale_line_id": str(line.sale_line_id),
            "quantity": line.quantity,
            "reason": line.reason,
            "disposition": line.disposition,
            "item_amount": str(money(line.item_amount)),
            "tax_amount": str(money(line.tax_amount)),
        } for line in lines],
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


async def serialize_sale(db: AsyncSession, sale: CounterSale, actor: User) -> dict[str, Any]:
    lines = await sale_lines(db, sale.tenant_id, sale.id)
    parts = await _tenant_parts(db, sale.tenant_id, [line.inventory_id for line in lines]) if lines else {}
    payments = list((await db.execute(select(CounterSalePaymentAttempt).where(
        CounterSalePaymentAttempt.tenant_id == sale.tenant_id,
        CounterSalePaymentAttempt.sale_id == sale.id,
    ).order_by(CounterSalePaymentAttempt.created_at))).scalars().all())
    return_rows = list((await db.execute(select(CounterSaleReturn).where(
        CounterSaleReturn.tenant_id == sale.tenant_id,
        CounterSaleReturn.sale_id == sale.id,
        CounterSaleReturn.deleted_at.is_(None),
    ).order_by(CounterSaleReturn.created_at))).scalars().all())
    return_lines = list((await db.execute(select(CounterSaleReturnLine).join(
        CounterSaleReturn,
        CounterSaleReturn.id == CounterSaleReturnLine.return_id,
    ).where(
        CounterSaleReturn.tenant_id == sale.tenant_id,
        CounterSaleReturn.sale_id == sale.id,
        CounterSaleReturnLine.deleted_at.is_(None),
    ))).scalars().all())
    returned_by_line: dict[UUID, int] = {}
    for row in return_lines:
        returned_by_line[row.sale_line_id] = returned_by_line.get(row.sale_line_id, 0) + row.quantity
    actions: list[str] = []
    if sale.status == "draft":
        actions.extend(("edit_draft", "checkout"))
        if actor.role in MANAGER_ROLES:
            actions.append("cancel")
    elif sale.status in {"completed", "partially_returned", "returned"}:
        actions.append("download_receipt")
        if actor.role in MANAGER_ROLES and sale.status != "returned" and any(
            returned_by_line.get(line.id, 0) < line.quantity for line in lines
        ):
            actions.append("create_return")
    return {
        "id": str(sale.id),
        "sale_number": sale.sale_number,
        "status": sale.status,
        "version": sale.version,
        "customer_id": str(sale.customer_id) if sale.customer_id else None,
        "buyer_name": sale.buyer_name_snapshot,
        "buyer_email": sale.buyer_email_snapshot,
        "buyer_phone": sale.buyer_phone_snapshot,
        "currency": "USD",
        "list_subtotal": str(money(sale.list_subtotal)),
        "charged_subtotal": str(money(sale.charged_subtotal)),
        "discount_amount": str(money(sale.discount_total)),
        "tax_amount": str(money(sale.tax_total)),
        "total_amount": str(money(sale.total)),
        "lines": [{
            **serialize_line(line, returned_quantity=returned_by_line.get(line.id, 0)),
            "physical_on_hand": int(parts[line.inventory_id].stock_quantity or 0),
            "held_for_checkout": 0,
            "available_to_sell": int(parts[line.inventory_id].stock_quantity or 0),
        } for line in lines],
        "payment_attempts": [{
            "id": str(row.id),
            "tender": row.tender,
            "state": row.state,
            "amount": str(money(row.amount)),
            "reference": row.external_reference,
            "created_at": row.created_at.isoformat(),
        } for row in payments],
        "returns": [await serialize_return(db, row) for row in return_rows],
        "allowed_actions": actions,
        "created_at": sale.created_at.isoformat(),
        "updated_at": sale.updated_at.isoformat(),
        "completed_at": sale.completed_at.isoformat() if sale.completed_at else None,
        "cancelled_at": sale.cancelled_at.isoformat() if sale.cancelled_at else None,
    }
