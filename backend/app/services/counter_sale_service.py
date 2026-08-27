"""Transactional counter-sale domain service (DB-045).

Provider I/O is deliberately excluded from locked transactions.  Endpoints use
``prepare_checkout`` then commit, call a provider, and enter one of the shared
idempotent finalizers below.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
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
    CounterSale, CounterSaleLine, CounterSalePaymentAttempt,
    CounterSaleRefund, CounterSaleReservation, CounterSaleReturn,
    CounterSaleReturnLine,
)
from app.db.models.parts_operations import InventoryMovement
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.part_activity_backfill import latest_verified_backfill
from app.services.part_activity_service import append_part_activity
from app.services.parts_operations_service import actor_name, apply_inventory_movement, decimal_money
from app.services.quickbooks_payments_service import QuickBooksPaymentError, payments_base_url


READ_ROLES = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST})
MANAGER_ROLES = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN})
MANUAL_TENDERS = frozenset({"cash", "check", "ach", "zelle", "external_terminal", "fleet_reference", "other"})
PROVIDER_TENDERS = frozenset({"stripe", "quickbooks_payments"})
ALL_TENDERS = MANUAL_TENDERS | PROVIDER_TENDERS
MONEY = Decimal("0.01")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def require_counter_sale_role(user: User, *, manager: bool = False) -> None:
    allowed = MANAGER_ROLES if manager else READ_ROLES
    if user.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def require_counter_sales_enabled(db: AsyncSession, user: User) -> tuple[Tenant, list[str]]:
    """Resolve every rollout gate from server state or return generic 404."""
    if not settings.COUNTER_SALES_ENABLED or not settings.PARTS_OPERATIONS_V1_ENABLED or not user.tenant_id:
        raise _not_found()
    tenant = (await db.execute(select(Tenant).where(
        Tenant.id == user.tenant_id, Tenant.deleted_at.is_(None),
        Tenant.is_active.is_(True), Tenant.parts_operations_enabled.is_(True),
        Tenant.counter_sales_enabled.is_(True),
    ))).scalar_one_or_none()
    if tenant is None or await latest_verified_backfill(db, tenant.id) is None:
        raise _not_found()
    require_counter_sale_role(user)
    tenders = sorted(MANUAL_TENDERS)
    if tenant.stripe_account_id and tenant.stripe_onboarding_complete and settings.STRIPE_SECRET_KEY:
        tenders.append("stripe")
    connection = (await db.execute(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant.id,
        QuickBooksConnection.deleted_at.is_(None),
        QuickBooksConnection.status == "connected",
    ))).scalar_one_or_none()
    if connection and connection.encrypted_access_token and "payment" in (connection.scopes or "").lower():
        tenders.append("quickbooks_payments")
    return tenant, tenders


async def counter_sale_capabilities(db: AsyncSession, user: User) -> dict[str, Any]:
    disabled = {
        "counter_sales": False,
        "counter_sale_tenders": [],
        "counter_sale_providers": {
            "stripe": {"available": False, "stripe_account_id": None},
            "quickbooks_payments": {"available": False, "token_url": None},
        },
    }
    try:
        tenant, tenders = await require_counter_sales_enabled(db, user)
    except HTTPException:
        return disabled
    try:
        token_url = f"{payments_base_url()}/quickbooks/v4/payments/tokens" if "quickbooks_payments" in tenders else None
    except QuickBooksPaymentError:
        token_url = None
        tenders = [tender for tender in tenders if tender != "quickbooks_payments"]
    return {
        "counter_sales": True,
        "counter_sale_tenders": tenders,
        "counter_sale_providers": {
            "stripe": {
                "available": "stripe" in tenders,
                "stripe_account_id": tenant.stripe_account_id if "stripe" in tenders else None,
            },
            "quickbooks_payments": {
                "available": "quickbooks_payments" in tenders,
                "token_url": token_url,
            },
        },
    }


async def _tenant_customer(db: AsyncSession, tenant_id: UUID, customer_id: UUID | None) -> Customer | None:
    if customer_id is None:
        return None
    row = (await db.execute(select(Customer).where(
        Customer.id == customer_id, Customer.tenant_id == tenant_id,
        Customer.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if row is None:
        raise _not_found()
    return row


async def _tenant_parts(db: AsyncSession, tenant_id: UUID, ids: Iterable[UUID], *, lock: bool = False) -> dict[UUID, Inventory]:
    unique_ids = sorted(set(ids), key=str)
    stmt = select(Inventory).where(
        Inventory.tenant_id == tenant_id, Inventory.id.in_(unique_ids),
        Inventory.deleted_at.is_(None), Inventory.is_placeholder.is_(False),
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
    latest = max((int(value.rsplit("-", 1)[-1]) for value in numbers if value.startswith("CS-") and value.rsplit("-", 1)[-1].isdigit()), default=0)
    return f"CS-{latest + 1:06d}"


def _allocate_cents(total: Decimal, weights: list[Decimal], stable_ids: list[UUID]) -> list[Decimal]:
    cents = int((money(total) * 100).to_integral_value())
    if cents == 0 or not weights:
        return [Decimal("0.00") for _ in weights]
    weight_sum = sum(weights, Decimal("0"))
    if weight_sum <= 0:
        return [Decimal("0.00") for _ in weights]
    raw = [Decimal(cents) * weight / weight_sum for weight in weights]
    floors = [int(value.to_integral_value(rounding=ROUND_DOWN)) for value in raw]
    remainder = cents - sum(floors)
    order = sorted(range(len(raw)), key=lambda index: (-(raw[index] - Decimal(floors[index])), str(stable_ids[index])))
    for index in order[:remainder]:
        floors[index] += 1
    return [Decimal(value) / Decimal("100") for value in floors]


def _unit_cents(total: Decimal, quantity: int) -> list[Decimal]:
    cents = int((money(total) * 100).to_integral_value())
    quotient, remainder = divmod(cents, quantity)
    return [Decimal(quotient + (1 if index < remainder else 0)) / Decimal("100") for index in range(quantity)]


def price_sale(sale: CounterSale, lines: list[CounterSaleLine], *, fee_eligible: bool) -> None:
    list_values = [money(line.list_unit_price * line.quantity) for line in lines]
    charged_values = [money(line.charged_unit_price * line.quantity) for line in lines]
    sale.list_subtotal = money(sum(list_values, Decimal("0")))
    sale.charged_subtotal = money(sum(charged_values, Decimal("0")))
    sale.discount_total = money(sale.list_subtotal - sale.charged_subtotal)
    sale.tax_total = money(sale.charged_subtotal * Decimal(sale.tax_rate_snapshot) / Decimal("100"))
    sale.service_fee_total = money(
        (sale.charged_subtotal + sale.tax_total) * Decimal(sale.service_fee_rate_snapshot) / Decimal("100")
    ) if fee_eligible else Decimal("0.00")
    sale.total = money(sale.charged_subtotal + sale.tax_total + sale.service_fee_total)
    tax_allocations = _allocate_cents(sale.tax_total, charged_values, [line.id for line in lines])
    fee_allocations = _allocate_cents(sale.service_fee_total, charged_values, [line.id for line in lines])
    for line, list_value, charged_value, tax, fee in zip(lines, list_values, charged_values, tax_allocations, fee_allocations):
        line.discount_total = money(list_value - charged_value)
        line.item_subtotal = charged_value
        line.tax_allocation = tax
        line.fee_allocation = fee
        line.total = money(charged_value + tax + fee)
        line.cost_total = money(line.unit_cost * line.quantity)
        item_units = _unit_cents(charged_value, line.quantity)
        discount_units = _unit_cents(line.discount_total, line.quantity)
        tax_units = _unit_cents(tax, line.quantity)
        fee_units = _unit_cents(fee, line.quantity)
        cost_units = _unit_cents(line.cost_total, line.quantity)
        line.unit_allocations = [
            {"ordinal": index + 1, "item": str(item_units[index]), "discount": str(discount_units[index]),
             "tax": str(tax_units[index]), "fee": str(fee_units[index]), "cost": str(cost_units[index])}
            for index in range(line.quantity)
        ]


async def create_or_replace_draft(
    db: AsyncSession, *, tenant: Tenant, actor: User,
    sale: CounterSale | None, customer_id: UUID | None,
    buyer_name: str | None, buyer_email: str | None, buyer_phone: str | None,
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
    if sale is None:
        sale = CounterSale(
            id=uuid4(), tenant_id=tenant.id, sale_number=await _next_sale_number(db, tenant.id),
            status="draft", version=1, currency="USD", customer_id=customer_id,
            created_by_user_id=actor.id, updated_by_user_id=actor.id,
            tax_rate_snapshot=Decimal(tenant.sales_tax_rate or 0),
            service_fee_rate_snapshot=Decimal(tenant.service_fee_rate or 0),
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
        CounterSaleLine.tenant_id == tenant.id, CounterSaleLine.sale_id == sale.id,
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
        requested_price = request.get("charged_unit_price")
        reason = " ".join(str(request.get("price_override_reason") or "").split())
        charged = catalog if requested_price is None else money(requested_price)
        if charged <= 0:
            raise _unprocessable("Charged unit price must be positive")
        if charged != catalog:
            require_counter_sale_role(actor, manager=True)
            if not 3 <= len(reason) <= 500:
                raise _unprocessable("Manager price override reason is required")
        elif actor.role == UserRole.RECEPTIONIST and requested_price is not None and charged != catalog:
            raise HTTPException(status_code=403, detail="Price override is not permitted")
        row = CounterSaleLine(
            id=uuid4(), tenant_id=tenant.id, sale_id=sale.id, inventory_id=part.id,
            quantity=quantity, sku_snapshot=part.sku, name_snapshot=part.name,
            unit_snapshot=part.unit_type, category_snapshot=part.category,
            unit_cost=money(part.cost), list_unit_price=catalog,
            charged_unit_price=charged, price_override_reason=reason or None,
            price_override_actor_id=actor.id if charged != catalog else None,
            item_subtotal=Decimal("0"), total=Decimal("0"), cost_total=Decimal("0"),
        )
        db.add(row)
        lines.append(row)
    price_sale(sale, lines, fee_eligible=True)
    if existing:
        sale.version += 1
    await db.flush()
    for line in lines:
        await append_part_activity(
            db, tenant_id=tenant.id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.created" if not existing else "counter_sale.updated",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:draft:v{sale.version}", actor=actor,
            correlation_id=sale.id, source_type="counter_sale", source_id=sale.id,
            source_number=sale.sale_number,
            after={"quantity": line.quantity, "status": sale.status},
            money={"currency": "USD", "list_price": str(line.list_unit_price), "charged_price": str(line.charged_unit_price), "discount": str(line.discount_total), "item_subtotal": str(line.item_subtotal), "tax": str(line.tax_allocation), "service_fee": str(line.fee_allocation), "total": str(line.total), "cost_basis": str(line.cost_total)},
        )
    return sale, lines


async def tenant_sale(db: AsyncSession, tenant_id: UUID, sale_id: UUID, *, lock: bool = False) -> CounterSale:
    stmt = select(CounterSale).where(
        CounterSale.id == sale_id, CounterSale.tenant_id == tenant_id,
        CounterSale.deleted_at.is_(None),
    )
    if lock:
        stmt = stmt.with_for_update()
    sale = (await db.execute(stmt)).scalar_one_or_none()
    if sale is None:
        raise _not_found()
    return sale


async def sale_lines(db: AsyncSession, tenant_id: UUID, sale_id: UUID, *, lock: bool = False) -> list[CounterSaleLine]:
    stmt = select(CounterSaleLine).where(
        CounterSaleLine.tenant_id == tenant_id, CounterSaleLine.sale_id == sale_id,
        CounterSaleLine.deleted_at.is_(None),
    ).order_by(CounterSaleLine.id)
    if lock:
        stmt = stmt.with_for_update()
    return list((await db.execute(stmt)).scalars().all())


async def held_for_parts(db: AsyncSession, tenant_id: UUID, inventory_ids: Iterable[UUID]) -> dict[UUID, int]:
    rows = (await db.execute(select(
        CounterSaleReservation.inventory_id, func.coalesce(func.sum(CounterSaleReservation.quantity), 0)
    ).where(
        CounterSaleReservation.tenant_id == tenant_id,
        CounterSaleReservation.inventory_id.in_(list(inventory_ids)),
        CounterSaleReservation.state == "held",
        CounterSaleReservation.deleted_at.is_(None),
    ).group_by(CounterSaleReservation.inventory_id))).all()
    return {inventory_id: int(quantity) for inventory_id, quantity in rows}


async def prepare_checkout(
    db: AsyncSession, *, tenant: Tenant, sale_id: UUID, actor: User,
    expected_version: int, tender: str, idempotency_key: str,
    manual_reference: str | None = None, receipt_email: str | None = None,
) -> tuple[CounterSale, list[CounterSaleLine], CounterSalePaymentAttempt]:
    if tender not in ALL_TENDERS:
        raise _unprocessable("Unsupported tender")
    if tender in MANUAL_TENDERS and tender not in {"cash", "other"} and not (manual_reference or "").strip():
        raise _unprocessable("Tender reference is required")
    sale = await tenant_sale(db, tenant.id, sale_id, lock=True)
    if sale.status != "draft" or sale.version != expected_version:
        raise _conflict("Counter sale version or state conflict")
    lines = await sale_lines(db, tenant.id, sale.id, lock=True)
    if not lines:
        raise _unprocessable("Counter sale has no lines")
    parts = await _tenant_parts(db, tenant.id, [line.inventory_id for line in lines], lock=True)
    existing_reservations = list((await db.execute(select(CounterSaleReservation).where(
        CounterSaleReservation.tenant_id == tenant.id,
        CounterSaleReservation.inventory_id.in_(list(parts)),
        CounterSaleReservation.state == "held",
        CounterSaleReservation.deleted_at.is_(None),
    ).order_by(CounterSaleReservation.inventory_id).with_for_update())).scalars().all())
    held = {part_id: 0 for part_id in parts}
    for reservation in existing_reservations:
        held[reservation.inventory_id] += reservation.quantity
    for line in lines:
        if int(parts[line.inventory_id].stock_quantity or 0) - held[line.inventory_id] < line.quantity:
            raise _conflict("Insufficient available-to-sell stock")
    # Manual tenders exclude card-provider service fees.
    price_sale(sale, lines, fee_eligible=tender in PROVIDER_TENDERS)
    if sale.total <= 0:
        raise _unprocessable("Counter sale total must be positive")
    expiry = now_utc() + timedelta(minutes=15)
    own_reservations = {
        row.sale_line_id: row for row in (await db.execute(select(CounterSaleReservation).where(
            CounterSaleReservation.tenant_id == tenant.id,
            CounterSaleReservation.sale_id == sale.id,
            CounterSaleReservation.deleted_at.is_(None),
        ).order_by(CounterSaleReservation.sale_line_id).with_for_update())).scalars().all()
    }
    for line in lines:
        reservation = own_reservations.get(line.id)
        if reservation is None:
            db.add(CounterSaleReservation(
                tenant_id=tenant.id, sale_id=sale.id, sale_line_id=line.id,
                inventory_id=line.inventory_id, quantity=line.quantity, state="held",
                expires_at=expiry,
            ))
        elif reservation.state in {"released", "expired"}:
            # The schema deliberately keeps one durable reservation identity
            # per sale line.  A definitive failure releases it; a later retry
            # re-arms that same audited row instead of violating the unique
            # tenant/line contract or losing its version history.
            reservation.inventory_id = line.inventory_id
            reservation.quantity = line.quantity
            reservation.state = "held"
            reservation.expires_at = expiry
            reservation.held_at = now_utc()
            reservation.released_at = None
            reservation.consumed_at = None
            reservation.release_reason = None
            reservation.version += 1
        else:
            raise _conflict("Counter sale reservation state conflict")
    attempt_count = int(await db.scalar(select(func.count(CounterSalePaymentAttempt.id)).where(
        CounterSalePaymentAttempt.tenant_id == tenant.id,
        CounterSalePaymentAttempt.sale_id == sale.id,
    )) or 0) + 1
    fingerprint = hashlib.sha256(json.dumps({"sale": str(sale.id), "version": sale.version, "tender": tender, "total": str(sale.total), "manual_reference": manual_reference}, sort_keys=True).encode()).hexdigest()
    attempt = CounterSalePaymentAttempt(
        id=uuid4(), tenant_id=tenant.id, sale_id=sale.id, tender=tender,
        state="created" if tender in MANUAL_TENDERS else "pending", amount=sale.total,
        request_fingerprint=fingerprint, idempotency_key=idempotency_key,
        provider_reference=(manual_reference or "").strip() or None,
        provider_request_id=f"db045-{attempt_count}-{sale.id}",
        attempt_number=attempt_count, actor_user_id=actor.id,
    )
    db.add(attempt)
    sale.status = "awaiting_payment"
    sale.receipt_email_to = receipt_email
    sale.version += 1
    await db.flush()
    for line in lines:
        await append_part_activity(
            db, tenant_id=tenant.id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.awaiting_payment",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:attempt:{attempt.id}:awaiting:v1",
            actor=actor, correlation_id=attempt.id, source_type="counter_sale", source_id=sale.id,
            source_number=sale.sale_number, before={"status": "draft"}, after={"status": sale.status, "quantity": line.quantity},
            money={"currency": "USD", "list_price": str(line.list_unit_price), "charged_price": str(line.charged_unit_price), "tax": str(line.tax_allocation), "service_fee": str(line.fee_allocation), "total": str(line.total)},
            payment={"tender": tender, "state": attempt.state, "provider_object_id": None},
        )
    return sale, lines, attempt


def _outbox(
    *, tenant_id: UUID, event_type: str, aggregate_type: str,
    aggregate_id: UUID, payload: dict[str, Any], idempotency_key: str,
) -> ProviderOutboxEvent:
    return ProviderOutboxEvent(
        tenant_id=tenant_id, event_type=event_type, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, payload=payload, idempotency_key=idempotency_key,
        status=ProviderOutboxStatus.PENDING.value, available_at=now_utc(),
    )


def _validate_provider_identity(
    attempt: CounterSalePaymentAttempt, provider_object_id: str | None,
) -> None:
    """Bind provider finalization to the object created for this attempt."""
    if attempt.tender not in PROVIDER_TENDERS:
        return
    if not provider_object_id:
        raise _conflict("Provider object identity is required")
    recorded = (
        attempt.provider_intent_id
        if attempt.tender == "stripe"
        else attempt.provider_charge_id
    )
    if recorded and recorded != provider_object_id:
        raise _conflict("Provider object identity mismatch")
    if attempt.tender == "stripe":
        attempt.provider_intent_id = provider_object_id
    else:
        attempt.provider_charge_id = provider_object_id


async def _queue_late_success_compensation(
    db: AsyncSession, *, sale: CounterSale,
    attempt: CounterSalePaymentAttempt, provider_status: str,
) -> None:
    """Persist one provider refund request without changing stock."""
    if attempt.tender not in PROVIDER_TENDERS:
        raise _conflict("Late-success compensation requires a provider tender")
    attempt.state = "compensating_refund_pending"
    attempt.provider_status = provider_status[:80]
    key = f"counter-sale-late-success:{attempt.id}:v1"
    exists = await db.scalar(select(ProviderOutboxEvent.id).where(
        ProviderOutboxEvent.tenant_id == sale.tenant_id,
        ProviderOutboxEvent.event_type == "counter_sale.compensating_refund.v1",
        ProviderOutboxEvent.idempotency_key == key,
    ))
    if exists is None:
        db.add(_outbox(
            tenant_id=sale.tenant_id,
            event_type="counter_sale.compensating_refund.v1",
            aggregate_type="counter_sale_payment_attempt",
            aggregate_id=attempt.id,
            payload={
                "sale_id": str(sale.id), "attempt_id": str(attempt.id),
                "amount": str(attempt.amount), "tender": attempt.tender,
            },
            idempotency_key=key,
        ))


async def finalize_checkout_success(
    db: AsyncSession, *, tenant_id: UUID, sale_id: UUID, attempt_id: UUID,
    provider_amount: Decimal, currency: str, provider_status: str,
    provider_object_id: str | None, actor: User | None,
) -> CounterSale:
    sale = await tenant_sale(db, tenant_id, sale_id, lock=True)
    attempt = (await db.execute(select(CounterSalePaymentAttempt).where(
        CounterSalePaymentAttempt.id == attempt_id,
        CounterSalePaymentAttempt.tenant_id == tenant_id,
        CounterSalePaymentAttempt.sale_id == sale.id,
    ).with_for_update())).scalar_one_or_none()
    if attempt is None:
        raise _not_found()
    if money(provider_amount) != money(attempt.amount) or currency.upper() != "USD":
        raise _conflict("Provider amount, currency, or state mismatch")
    _validate_provider_identity(attempt, provider_object_id)
    if sale.status == "completed" and attempt.state == "succeeded":
        return sale
    lines = await sale_lines(db, tenant_id, sale.id, lock=True)
    all_reservations = list((await db.execute(select(CounterSaleReservation).where(
        CounterSaleReservation.tenant_id == tenant_id,
        CounterSaleReservation.sale_id == sale.id,
    ).order_by(CounterSaleReservation.inventory_id).with_for_update())).scalars().all())
    reservations = [row for row in all_reservations if row.state == "held"]

    if attempt.state in {"failed", "compensating_refund_pending", "compensated"}:
        # The failed attempt itself is the durable proof that its own hold was
        # released.  A later retry may already have re-armed the same reservation
        # row for a newer attempt; the old provider success still must be refunded
        # and must never consume that newer hold.
        if attempt.state == "compensated":
            return sale
        await _queue_late_success_compensation(
            db, sale=sale, attempt=attempt, provider_status=provider_status,
        )
        return sale

    # A provider can report success after its definitive failure response caused
    # this attempt's holds to be safely released and the sale to return to draft.
    # Compensate financially; never decrement stock or complete the sale.
    if sale.status == "draft":
        if not all_reservations or any(
            row.state not in {"released", "expired"} for row in all_reservations
        ):
            raise _conflict("Late provider success has unsafe reservation state")
        await _queue_late_success_compensation(
            db, sale=sale, attempt=attempt, provider_status=provider_status,
        )
        return sale
    if sale.status != "awaiting_payment":
        raise _conflict("Provider amount, currency, or state mismatch")
    latest_attempt_id = await db.scalar(select(CounterSalePaymentAttempt.id).where(
        CounterSalePaymentAttempt.tenant_id == tenant_id,
        CounterSalePaymentAttempt.sale_id == sale.id,
    ).order_by(
        CounterSalePaymentAttempt.attempt_number.desc(),
        CounterSalePaymentAttempt.created_at.desc(),
    ).limit(1))
    if latest_attempt_id != attempt.id:
        raise _conflict("Provider success does not match the active payment attempt")
    if len(reservations) != len(lines):
        if not all_reservations or any(
            row.state not in {"released", "expired"} for row in all_reservations
        ):
            raise _conflict("Provider success has unsafe reservation state")
        await _queue_late_success_compensation(
            db, sale=sale, attempt=attempt, provider_status=provider_status,
        )
        return sale
    parts = await _tenant_parts(db, tenant_id, [line.inventory_id for line in lines], lock=True)
    # Consumed reservations are no longer holds. Materialize that transition
    # before stock events calculate physical/held/available snapshots; the
    # finalizer still commits all stock, payment, Activity, and outbox writes
    # atomically.
    consumed_at = now_utc()
    for reservation in reservations:
        reservation.state = "consumed"
        reservation.consumed_at = consumed_at
    await db.flush()
    remaining_holds = await held_for_parts(db, tenant_id, [line.inventory_id for line in lines])
    for line in lines:
        part = parts[line.inventory_id]
        await apply_inventory_movement(
            db, item=part, quantity_delta=-line.quantity,
            movement_type="counter_sale", actor=actor,
            source_type="counter_sale", source_id=sale.id,
            reason_code="counter_sale_completed",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:movement:v1",
            held_for_checkout=remaining_holds.get(line.inventory_id, 0),
        )
        await append_part_activity(
            db, tenant_id=tenant_id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.payment_succeeded",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:attempt:{attempt.id}:payment-succeeded:v1",
            actor=actor, correlation_id=attempt.id, source_type="counter_sale", source_id=sale.id,
            source_number=sale.sale_number,
            before={"status": "awaiting_payment"}, after={"status": "payment_succeeded"},
            money={"currency": "USD", "total": str(line.total)},
            payment={"tender": attempt.tender, "state": "succeeded", "provider_object_id": provider_object_id},
        )
        await append_part_activity(
            db, tenant_id=tenant_id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.completed",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:completed:v1",
            actor=actor, correlation_id=attempt.id, source_type="counter_sale", source_id=sale.id,
            source_number=sale.sale_number,
            before={"status": "awaiting_payment"}, after={"status": "completed", "quantity": line.quantity},
            money={"currency": "USD", "list_price": str(line.list_unit_price), "charged_price": str(line.charged_unit_price), "discount": str(line.discount_total), "item_subtotal": str(line.item_subtotal), "tax": str(line.tax_allocation), "service_fee": str(line.fee_allocation), "total": str(line.total), "cost_basis": str(line.cost_total)},
            payment={"tender": attempt.tender, "state": "succeeded", "provider_object_id": provider_object_id},
        )
    attempt.state = "succeeded"
    attempt.provider_status = provider_status[:80]
    attempt.reconciled_at = now_utc()
    sale.status = "completed"
    sale.version += 1
    sale.completed_at = now_utc()
    sale.completed_by_user_id = actor.id if actor else attempt.actor_user_id
    sale.accounting_sync_status = "queued"
    sale.receipt_snapshot = build_receipt_snapshot(sale, lines, attempt)
    db.add(_outbox(
        tenant_id=tenant_id, event_type="quickbooks.counter_sale.sync.v1",
        aggregate_type="counter_sale", aggregate_id=sale.id,
        payload={"sale_id": str(sale.id), "payload_version": 1},
        idempotency_key=f"counter-sale:{sale.id}:qbo-sales-receipt:v1",
    ))
    if sale.receipt_email_to:
        db.add(_outbox(
            tenant_id=tenant_id, event_type="counter_sale.receipt.email.v1",
            aggregate_type="counter_sale", aggregate_id=sale.id,
            payload={"sale_id": str(sale.id), "payload_version": 1},
            idempotency_key=f"counter-sale:{sale.id}:receipt-email:v1",
        ))
    return sale


async def finalize_checkout_failure(
    db: AsyncSession, *, tenant_id: UUID, sale_id: UUID, attempt_id: UUID,
    failure_code: str, actor: User | None,
) -> CounterSale:
    sale = await tenant_sale(db, tenant_id, sale_id, lock=True)
    attempt = (await db.execute(select(CounterSalePaymentAttempt).where(
        CounterSalePaymentAttempt.id == attempt_id,
        CounterSalePaymentAttempt.tenant_id == tenant_id,
        CounterSalePaymentAttempt.sale_id == sale.id,
    ).with_for_update())).scalar_one_or_none()
    if attempt is None:
        raise _not_found()
    if attempt.state == "failed":
        return sale
    if sale.status != "awaiting_payment":
        raise _conflict("Counter sale is not awaiting payment")
    lines = await sale_lines(db, tenant_id, sale.id)
    reservations = list((await db.execute(select(CounterSaleReservation).where(
        CounterSaleReservation.tenant_id == tenant_id,
        CounterSaleReservation.sale_id == sale.id,
        CounterSaleReservation.state == "held",
    ).with_for_update())).scalars().all())
    for row in reservations:
        row.state = "released"
        row.released_at = now_utc()
        row.release_reason = "definitive_payment_failure"
    attempt.state = "failed"
    attempt.safe_failure_code = failure_code[:100]
    attempt.reconciled_at = now_utc()
    sale.status = "draft"
    sale.version += 1
    for line in lines:
        await append_part_activity(
            db, tenant_id=tenant_id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.payment_failed",
            idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:attempt:{attempt.id}:failed:v1",
            actor=actor, correlation_id=attempt.id, source_type="counter_sale", source_id=sale.id,
            source_number=sale.sale_number, before={"status": "awaiting_payment"}, after={"status": "draft"},
            payment={"tender": attempt.tender, "state": "failed", "failure_code": failure_code[:100]},
        )
    return sale


def build_receipt_snapshot(sale: CounterSale, lines: list[CounterSaleLine], attempt: CounterSalePaymentAttempt) -> dict[str, Any]:
    return {
        "sale_number": sale.sale_number, "completed_at": sale.completed_at.isoformat() if sale.completed_at else None,
        "buyer": {"name": sale.buyer_name_snapshot, "email": sale.buyer_email_snapshot, "phone": sale.buyer_phone_snapshot},
        "currency": "USD", "lines": [
            {"sku": line.sku_snapshot, "name": line.name_snapshot, "quantity": line.quantity,
             "unit_price": str(line.charged_unit_price), "item": str(line.item_subtotal),
             "tax": str(line.tax_allocation), "fee": str(line.fee_allocation), "total": str(line.total)}
            for line in lines
        ],
        "subtotal": str(sale.charged_subtotal), "tax": str(sale.tax_total),
        "service_fee": str(sale.service_fee_total), "total": str(sale.total),
        "tender": attempt.tender,
        "payment_reference": attempt.provider_reference or attempt.provider_charge_id or attempt.provider_intent_id,
    }


async def create_return_claim(
    db: AsyncSession, *, tenant: Tenant, sale_id: UUID, actor: User,
    expected_version: int, line_inputs: list[dict[str, Any]],
    idempotency_key: str, manual_reference: str | None,
) -> tuple[CounterSale, CounterSaleReturn, CounterSaleRefund, list[CounterSaleReturnLine]]:
    require_counter_sale_role(actor, manager=True)
    sale = await tenant_sale(db, tenant.id, sale_id, lock=True)
    if sale.status not in {"completed", "partially_returned"} or sale.version != expected_version:
        raise _conflict("Counter sale version or return state conflict")
    if not line_inputs:
        raise _unprocessable("Return requires at least one line")
    requested_line_ids = [request["sale_line_id"] for request in line_inputs]
    if len(set(requested_line_ids)) != len(requested_line_ids):
        raise _unprocessable("Each sale line may appear only once per return")
    lines = {line.id: line for line in await sale_lines(db, tenant.id, sale.id, lock=True)}
    previous = list((await db.execute(select(CounterSaleReturnLine).join(
        CounterSaleReturn, CounterSaleReturn.id == CounterSaleReturnLine.return_id
    ).where(
        CounterSaleReturnLine.tenant_id == tenant.id,
        CounterSaleReturn.sale_id == sale.id,
        CounterSaleReturn.state.in_(("pending_refund", "refund_failed", "completed")),
        CounterSaleReturnLine.deleted_at.is_(None),
    ).with_for_update())).scalars().all())
    claimed: dict[UUID, set[int]] = {}
    for row in previous:
        claimed.setdefault(row.sale_line_id, set()).update(int(value) for value in (row.unit_ordinals or []))
    return_row = CounterSaleReturn(
        id=uuid4(), tenant_id=tenant.id, sale_id=sale.id, version=1,
        state="pending_refund", item_amount=0, tax_amount=0, fee_amount=0,
        refund_amount=0, created_by_user_id=actor.id,
        reason="; ".join(" ".join(str(value.get("reason") or "").split()) for value in line_inputs),
        correlation_id=uuid4(),
    )
    db.add(return_row)
    created: list[CounterSaleReturnLine] = []
    for request in line_inputs:
        line_id = request["sale_line_id"]
        line = lines.get(line_id)
        if line is None:
            raise _not_found()
        quantity = int(request["quantity"])
        reason = " ".join(str(request.get("reason") or "").split())
        disposition = request.get("disposition")
        if quantity <= 0 or not 3 <= len(reason) <= 500 or disposition not in {"restock", "damaged"}:
            raise _unprocessable("Invalid return line")
        available_ordinals = [entry["ordinal"] for entry in (line.unit_allocations or []) if int(entry["ordinal"]) not in claimed.get(line.id, set())]
        if len(available_ordinals) < quantity:
            raise _conflict("Return quantity exceeds remaining units")
        ordinals = available_ordinals[:quantity]
        entries = [entry for entry in line.unit_allocations if int(entry["ordinal"]) in ordinals]
        item_amount = money(sum((Decimal(entry["item"]) for entry in entries), Decimal("0")))
        discount_amount = money(sum((Decimal(entry["discount"]) for entry in entries), Decimal("0")))
        tax_amount = money(sum((Decimal(entry["tax"]) for entry in entries), Decimal("0")))
        fee_amount = money(sum((Decimal(entry["fee"]) for entry in entries), Decimal("0")))
        cost_amount = money(sum((Decimal(entry["cost"]) for entry in entries), Decimal("0")))
        row = CounterSaleReturnLine(
            tenant_id=tenant.id, return_id=return_row.id, sale_line_id=line.id,
            quantity=quantity, reason=reason, disposition=disposition,
            item_amount=item_amount, discount_amount=discount_amount,
            tax_amount=tax_amount, fee_amount=fee_amount, cost_amount=cost_amount,
            unit_ordinals=ordinals,
        )
        db.add(row)
        created.append(row)
        return_row.item_amount += item_amount
        return_row.tax_amount += tax_amount
        return_row.fee_amount += fee_amount
    return_row.refund_amount = money(return_row.item_amount + return_row.tax_amount + return_row.fee_amount)
    attempt = (await db.execute(select(CounterSalePaymentAttempt).where(
        CounterSalePaymentAttempt.tenant_id == tenant.id,
        CounterSalePaymentAttempt.sale_id == sale.id,
        CounterSalePaymentAttempt.state == "succeeded",
    ).order_by(CounterSalePaymentAttempt.created_at.desc()).limit(1).with_for_update())).scalar_one_or_none()
    if attempt is None:
        raise _conflict("Original settled payment is unavailable")
    if attempt.tender in MANUAL_TENDERS and attempt.tender not in {"cash", "other"} and not (manual_reference or "").strip():
        raise _unprocessable("Manual refund reference is required")
    fingerprint = hashlib.sha256(f"{return_row.id}:{return_row.refund_amount}:{attempt.id}".encode()).hexdigest()
    refund = CounterSaleRefund(
        tenant_id=tenant.id, return_id=return_row.id, payment_attempt_id=attempt.id,
        tender=attempt.tender, state="pending", amount=return_row.refund_amount,
        provider_reference=(manual_reference or "").strip() or None,
        idempotency_key=idempotency_key, request_fingerprint=fingerprint,
    )
    db.add(refund)
    await db.flush()
    for row in created:
        line = lines[row.sale_line_id]
        await append_part_activity(
            db, tenant_id=tenant.id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.return_requested",
            idempotency_key=f"counter_sale_return:{return_row.id}:line:{row.id}:requested:v1",
            actor=actor, correlation_id=return_row.correlation_id,
            source_type="counter_sale", source_id=sale.id, source_number=sale.sale_number,
            after={"quantity": row.quantity, "status": return_row.state, "disposition": row.disposition},
            money={"currency": "USD", "refund_allocations": {"item": str(row.item_amount), "tax": str(row.tax_amount), "fee": str(row.fee_amount), "total": str(money(row.item_amount + row.tax_amount + row.fee_amount))}},
            payment={"tender": attempt.tender, "state": "pending"},
        )
    return sale, return_row, refund, created


async def finalize_refund_success(
    db: AsyncSession, *, tenant_id: UUID, return_id: UUID,
    provider_refund_id: str | None, actor: User | None,
) -> CounterSaleReturn:
    return_row = (await db.execute(select(CounterSaleReturn).where(
        CounterSaleReturn.id == return_id, CounterSaleReturn.tenant_id == tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if return_row is None:
        raise _not_found()
    refund = (await db.execute(select(CounterSaleRefund).where(
        CounterSaleRefund.return_id == return_id, CounterSaleRefund.tenant_id == tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if refund is None:
        raise _not_found()
    if return_row.state == "completed" and refund.state == "succeeded":
        return return_row
    sale = await tenant_sale(db, tenant_id, return_row.sale_id, lock=True)
    lines = {line.id: line for line in await sale_lines(db, tenant_id, sale.id, lock=True)}
    return_lines = list((await db.execute(select(CounterSaleReturnLine).where(
        CounterSaleReturnLine.tenant_id == tenant_id,
        CounterSaleReturnLine.return_id == return_id,
    ).with_for_update())).scalars().all())
    parts = await _tenant_parts(db, tenant_id, [lines[row.sale_line_id].inventory_id for row in return_lines], lock=True)
    for row in return_lines:
        line = lines[row.sale_line_id]
        if row.disposition == "restock":
            await apply_inventory_movement(
                db, item=parts[line.inventory_id], quantity_delta=row.quantity,
                movement_type="counter_sale_return", actor=actor,
                source_type="counter_sale", source_id=sale.id,
                reason_code="counter_sale_return_restock", note=row.reason,
                idempotency_key=f"counter_sale_return:{return_row.id}:line:{row.id}:movement:v1",
            )
        await append_part_activity(
            db, tenant_id=tenant_id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.return_completed",
            idempotency_key=f"counter_sale_return:{return_row.id}:line:{row.id}:completed:v1",
            actor=actor, correlation_id=return_row.correlation_id,
            source_type="counter_sale", source_id=sale.id, source_number=sale.sale_number,
            before={"status": "pending_refund"}, after={"status": "completed", "quantity": row.quantity, "disposition": row.disposition},
            money={"currency": "USD", "refund_allocations": {"item": str(row.item_amount), "tax": str(row.tax_amount), "fee": str(row.fee_amount)}},
            payment={"tender": refund.tender, "state": "succeeded", "provider_object_id": provider_refund_id},
        )
        await append_part_activity(
            db, tenant_id=tenant_id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.refund_succeeded",
            idempotency_key=f"counter_sale_return:{return_row.id}:line:{row.id}:refund-succeeded:v1",
            actor=actor, correlation_id=return_row.correlation_id,
            source_type="counter_sale", source_id=sale.id, source_number=sale.sale_number,
            after={"status": "succeeded", "quantity": row.quantity},
            money={"currency": "USD", "refund_allocations": {
                "item": str(row.item_amount), "tax": str(row.tax_amount),
                "fee": str(row.fee_amount),
            }},
            payment={"tender": refund.tender, "state": "succeeded", "provider_object_id": provider_refund_id},
        )
    refund.state = "succeeded"
    refund.provider_refund_id = provider_refund_id
    return_row.state = "completed"
    return_row.version += 1
    return_row.completed_at = now_utc()
    # Sessions use autoflush=False, so explicitly materialize this completed
    # return before deriving the aggregate sale state.
    await db.flush()
    total_returned = int(await db.scalar(select(func.coalesce(func.sum(CounterSaleReturnLine.quantity), 0)).join(
        CounterSaleReturn, CounterSaleReturn.id == CounterSaleReturnLine.return_id
    ).where(
        CounterSaleReturn.tenant_id == tenant_id, CounterSaleReturn.sale_id == sale.id,
        CounterSaleReturn.state == "completed",
    )) or 0)
    total_sold = sum(line.quantity for line in lines.values())
    sale.status = "returned" if total_returned >= total_sold else "partially_returned"
    sale.version += 1
    db.add(_outbox(
        tenant_id=tenant_id, event_type="quickbooks.counter_sale_return.sync.v1",
        aggregate_type="counter_sale_return", aggregate_id=return_row.id,
        payload={"sale_id": str(sale.id), "return_id": str(return_row.id), "payload_version": 1},
        idempotency_key=f"counter-sale-return:{return_row.id}:qbo-refund-receipt:v1",
    ))
    return return_row


async def finalize_refund_failure(
    db: AsyncSession, *, tenant_id: UUID, return_id: UUID,
    failure_code: str, actor: User | None,
) -> CounterSaleReturn:
    return_row = (await db.execute(select(CounterSaleReturn).where(
        CounterSaleReturn.id == return_id, CounterSaleReturn.tenant_id == tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if return_row is None:
        raise _not_found()
    refund = (await db.execute(select(CounterSaleRefund).where(
        CounterSaleRefund.return_id == return_id,
        CounterSaleRefund.tenant_id == tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if refund is None:
        raise _not_found()
    if return_row.state == "refund_failed" and refund.state == "failed":
        return return_row
    sale = await tenant_sale(db, tenant_id, return_row.sale_id)
    sale_line_rows = await sale_lines(db, tenant_id, sale.id)
    lines = {line.id: line for line in sale_line_rows}
    return_lines = list((await db.execute(select(CounterSaleReturnLine).where(
        CounterSaleReturnLine.tenant_id == tenant_id,
        CounterSaleReturnLine.return_id == return_id,
    ))).scalars().all())
    safe_code = (failure_code or "provider_failed")[:100]
    refund.state = "failed"
    refund.safe_failure_code = safe_code
    return_row.state = "refund_failed"
    return_row.version += 1
    for row in return_lines:
        line = lines[row.sale_line_id]
        await append_part_activity(
            db, tenant_id=tenant_id, inventory_id=line.inventory_id,
            category="sales", event_type="counter_sale.refund_failed",
            idempotency_key=f"counter_sale_return:{return_row.id}:line:{row.id}:refund-failed:{refund.attempt_count}:v1",
            actor=actor, correlation_id=return_row.correlation_id,
            source_type="counter_sale", source_id=sale.id, source_number=sale.sale_number,
            before={"status": "pending_refund"}, after={"status": "refund_failed"},
            money={"currency": "USD", "refund_allocations": {
                "item": str(row.item_amount), "tax": str(row.tax_amount),
                "fee": str(row.fee_amount),
            }},
            payment={"tender": refund.tender, "state": "failed", "failure_code": safe_code},
        )
    return return_row


def serialize_line(
    line: CounterSaleLine, *, returned_quantity: int = 0,
) -> dict[str, Any]:
    return {
        "id": str(line.id), "inventory_id": str(line.inventory_id), "quantity": line.quantity,
        "sku": line.sku_snapshot, "name": line.name_snapshot, "unit_type": line.unit_snapshot,
        "returned_quantity": returned_quantity,
        "remaining_returnable_quantity": max(line.quantity - returned_quantity, 0),
        "unit_cost": str(money(line.unit_cost)),
        "list_unit_price": str(money(line.list_unit_price)),
        "charged_unit_price": str(money(line.charged_unit_price)),
        "discount_amount": str(money(line.discount_total)),
        "item_subtotal": str(money(line.item_subtotal)),
        "tax_amount": str(money(line.tax_allocation)),
        "fee_amount": str(money(line.fee_allocation)),
        "total_amount": str(money(line.total)),
        "price_override_reason": line.price_override_reason,
    }


async def serialize_sale(db: AsyncSession, sale: CounterSale, actor: User) -> dict[str, Any]:
    lines = await sale_lines(db, sale.tenant_id, sale.id)
    held = await held_for_parts(db, sale.tenant_id, [line.inventory_id for line in lines])
    parts = await _tenant_parts(db, sale.tenant_id, [line.inventory_id for line in lines]) if lines else {}
    attempts = list((await db.execute(select(CounterSalePaymentAttempt).where(
        CounterSalePaymentAttempt.tenant_id == sale.tenant_id,
        CounterSalePaymentAttempt.sale_id == sale.id,
    ).order_by(CounterSalePaymentAttempt.created_at))).scalars().all())
    return_rows = list((await db.execute(select(CounterSaleReturn).where(
        CounterSaleReturn.tenant_id == sale.tenant_id,
        CounterSaleReturn.sale_id == sale.id,
        CounterSaleReturn.deleted_at.is_(None),
    ).order_by(CounterSaleReturn.created_at))).scalars().all())
    return_ids = [row.id for row in return_rows]
    return_lines = list((await db.execute(select(CounterSaleReturnLine).where(
        CounterSaleReturnLine.tenant_id == sale.tenant_id,
        CounterSaleReturnLine.return_id.in_(return_ids),
        CounterSaleReturnLine.deleted_at.is_(None),
    ))).scalars().all()) if return_ids else []
    refunds = list((await db.execute(select(CounterSaleRefund).where(
        CounterSaleRefund.tenant_id == sale.tenant_id,
        CounterSaleRefund.return_id.in_(return_ids),
        CounterSaleRefund.deleted_at.is_(None),
    ))).scalars().all()) if return_ids else []
    claimed_by_line: dict[UUID, int] = {}
    for row in return_lines:
        claimed_by_line[row.sale_line_id] = claimed_by_line.get(row.sale_line_id, 0) + row.quantity
    lines_by_return: dict[UUID, list[CounterSaleReturnLine]] = {}
    for row in return_lines:
        lines_by_return.setdefault(row.return_id, []).append(row)
    refund_by_return = {row.return_id: row for row in refunds}
    actions: list[str] = []
    if sale.status == "draft":
        actions.extend(("edit_draft", "checkout"))
        if actor.role in MANAGER_ROLES:
            actions.append("cancel")
    elif sale.status == "awaiting_payment":
        actions.append("reconcile_payment")
    elif sale.status in {"completed", "partially_returned", "returned"}:
        actions.extend(("download_receipt", "email_receipt"))
        if actor.role in MANAGER_ROLES:
            if sale.status != "returned" and any(claimed_by_line.get(line.id, 0) < line.quantity for line in lines):
                actions.append("create_return")
            if any(row.state == "refund_failed" for row in return_rows):
                actions.append("retry_refund")
    email_status = await db.scalar(select(ProviderOutboxEvent.status).where(
        ProviderOutboxEvent.tenant_id == sale.tenant_id,
        ProviderOutboxEvent.aggregate_type == "counter_sale",
        ProviderOutboxEvent.aggregate_id == sale.id,
        ProviderOutboxEvent.event_type == "counter_sale.receipt.email.v1",
    ).order_by(ProviderOutboxEvent.created_at.desc()).limit(1))
    return {
        "id": str(sale.id), "sale_number": sale.sale_number, "status": sale.status,
        "version": sale.version, "customer_id": str(sale.customer_id) if sale.customer_id else None,
        "buyer_name": sale.buyer_name_snapshot,
        "buyer_email": sale.buyer_email_snapshot,
        "buyer_phone": sale.buyer_phone_snapshot,
        "currency": "USD", "list_subtotal": str(money(sale.list_subtotal)),
        "charged_subtotal": str(money(sale.charged_subtotal)),
        "discount_amount": str(money(sale.discount_total)),
        "tax_amount": str(money(sale.tax_total)),
        "service_fee_amount": str(money(sale.service_fee_total)),
        "total_amount": str(money(sale.total)),
        "lines": [{**serialize_line(line, returned_quantity=claimed_by_line.get(line.id, 0)),
                   "physical_on_hand": int(parts[line.inventory_id].stock_quantity or 0),
                   "held_for_checkout": held.get(line.inventory_id, 0),
                   "available_to_sell": max(int(parts[line.inventory_id].stock_quantity or 0) - held.get(line.inventory_id, 0), 0)} for line in lines],
        "payment_attempts": [{
            "id": str(row.id), "tender": row.tender, "state": row.state,
            "amount": str(money(row.amount)), "failure_code": row.safe_failure_code,
            "safe_status": row.provider_status,
            "created_at": row.created_at.isoformat(),
        } for row in attempts],
        "returns": [{
            "id": str(row.id), "state": row.state,
            "refund_amount": str(money(row.refund_amount)),
            "created_at": row.created_at.isoformat(),
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "lines": [{
                "sale_line_id": str(line.sale_line_id), "quantity": line.quantity,
                "reason": line.reason, "disposition": line.disposition,
            } for line in lines_by_return.get(row.id, [])],
            "refund": None if row.id not in refund_by_return else {
                "id": str(refund_by_return[row.id].id),
                "state": refund_by_return[row.id].state,
                "failure_code": refund_by_return[row.id].safe_failure_code,
            },
        } for row in return_rows],
        "allowed_actions": actions,
        "created_at": sale.created_at.isoformat(),
        "updated_at": sale.updated_at.isoformat(),
        "completed_at": sale.completed_at.isoformat() if sale.completed_at else None,
        "cancelled_at": sale.cancelled_at.isoformat() if sale.cancelled_at else None,
        "accounting_sync_status": sale.accounting_sync_status,
        "receipt_email_status": email_status,
    }
