from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.api.v1.endpoints import invoice_access, payments
from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    InvoicePaymentAttempt,
    InvoicePaymentLedgerEvent,
    InvoiceSettlement,
)
from app.db.models.payment import Payment
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.vehicle import Vehicle
from app.services.invoice_settlement_service import SettlementDomainError, create_attempt


async def _seed_adapter_context(db) -> SimpleNamespace:
    tenant = Tenant(
        name="DB048 Adapter Garage",
        slug=f"db048-adapter-{uuid4().hex}",
        invoice_split_payments_enabled=True,
        stripe_account_id=f"acct_{uuid4().hex}",
        stripe_onboarding_complete=True,
    )
    db.add(tenant)
    await db.flush()

    owner = User(
        email=f"owner-{uuid4().hex}@example.com",
        hashed_password="hash",
        first_name="Adapter",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Bounded",
        last_name="Customer",
        email=f"customer-{uuid4().hex}@example.com",
    )
    foreign_customer = Customer(
        tenant_id=tenant.id,
        first_name="Foreign",
        last_name="Customer",
        email=f"foreign-{uuid4().hex}@example.com",
    )
    db.add_all([owner, customer, foreign_customer])
    await db.flush()

    customer_user = User(
        email=customer.email,
        hashed_password="hash",
        first_name=customer.first_name,
        last_name=customer.last_name,
        role=UserRole.CUSTOMER,
        tenant_id=tenant.id,
        customer_id=customer.id,
        is_active=True,
        is_verified=True,
    )
    db.add(customer_user)
    await db.flush()
    db.add(UserCustomerLink(
        user_id=customer_user.id,
        customer_id=customer.id,
        tenant_id=tenant.id,
    ))

    async def make_invoice(linked_customer: Customer, prefix: str) -> tuple[RepairOrder, Invoice]:
        vehicle = Vehicle(
            tenant_id=tenant.id,
            customer_id=linked_customer.id,
            make="Volvo",
            model="VNL",
        )
        db.add(vehicle)
        await db.flush()
        order = RepairOrder(
            tenant_id=tenant.id,
            customer_id=linked_customer.id,
            vehicle_id=vehicle.id,
            order_number=f"{prefix}-RO-{uuid4().hex[:8]}",
            status=RepairOrderStatus.INVOICED,
            total_parts_cost=Decimal("0.00"),
            total_labor_cost=Decimal("100.00"),
            total_cost=Decimal("100.00"),
        )
        db.add(order)
        await db.flush()
        invoice = Invoice(
            tenant_id=tenant.id,
            repair_order_id=order.id,
            invoice_number=f"{prefix}-INV-{uuid4().hex[:8]}",
            status=InvoiceStatus.SENT,
            subtotal=Decimal("100.00"),
            shop_supplies_amount=Decimal("0.00"),
            service_fee_amount=Decimal("3.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("103.00"),
        )
        db.add(invoice)
        await db.flush()
        return order, invoice

    order, invoice = await make_invoice(customer, "OWN")
    foreign_order, foreign_invoice = await make_invoice(foreign_customer, "FOREIGN")
    await db.commit()
    customer_headers = {
        "Authorization": "Bearer " + create_access_token(
            {"sub": str(customer_user.id)}, tenant_id=str(tenant.id),
        )
    }
    owner_headers = {
        "Authorization": "Bearer " + create_access_token(
            {"sub": str(owner.id)}, tenant_id=str(tenant.id),
        )
    }
    return SimpleNamespace(
        tenant=tenant,
        owner=owner,
        customer=customer,
        customer_user=customer_user,
        order=order,
        invoice=invoice,
        foreign_order=foreign_order,
        foreign_invoice=foreign_invoice,
        customer_headers=customer_headers,
        owner_headers=owner_headers,
    )


async def _mutation_snapshot(db, invoice_id: UUID) -> tuple:
    db.expire_all()
    invoice = await db.get(Invoice, invoice_id)
    model_counts = []
    for model in (InvoiceSettlement, InvoicePaymentAttempt, InvoicePaymentLedgerEvent, Payment):
        model_counts.append(await db.scalar(select(func.count()).select_from(model)))
    return (
        *model_counts,
        invoice.status,
        invoice.zelle_pending_submitted_at,
        invoice.zelle_pending_sender_email,
        invoice.zelle_pending_sender_phone,
        invoice.notes,
    )


def _forbid_adapter_side_effects(monkeypatch) -> list[str]:
    calls: list[str] = []

    def forbidden_sync(*_args, **_kwargs):
        calls.append("provider")
        raise AssertionError("provider or side effect called before invoice authorization")

    async def forbidden_async(*_args, **_kwargs):
        calls.append("mutation")
        raise AssertionError("mutation or side effect called before invoice authorization")

    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", forbidden_sync)
    monkeypatch.setattr(payments.stripe.PaymentIntent, "retrieve", forbidden_sync)
    monkeypatch.setattr(payments, "ensure_connected_stripe_customer", forbidden_async)
    monkeypatch.setattr(invoice_access, "ensure_connected_stripe_customer", forbidden_async)
    monkeypatch.setattr(payments, "settlement_for_compatibility_route", forbidden_async)
    monkeypatch.setattr(invoice_access, "settlement_for_compatibility_route", forbidden_async)
    monkeypatch.setattr(payments, "finalize_stripe_invoice_payment", forbidden_async)
    monkeypatch.setattr(invoice_access, "finalize_stripe_invoice_payment", forbidden_async)
    monkeypatch.setattr(payments, "send_pending_zelle_submission_alert", forbidden_async)
    monkeypatch.setattr(invoice_access, "send_pending_zelle_submission_alert", forbidden_async)
    monkeypatch.setattr(payments, "broadcast_repair_order_update", forbidden_async)
    monkeypatch.setattr(invoice_access, "broadcast_repair_order_update", forbidden_async)
    return calls


ADAPTER_CASES = (
    (
        "/api/v1/payments/create-payment-intent",
        lambda ctx: {"invoice_id": str(ctx.invoice.id), "amount": "10.00"},
        "customer",
    ),
    (
        "/api/v1/payments/confirm-payment",
        lambda ctx: {"invoice_id": str(ctx.invoice.id), "payment_intent_id": "pi_never"},
        "customer",
    ),
    (
        "/api/v1/payments/record-manual",
        lambda ctx: {
            "invoice_id": str(ctx.invoice.id),
            "method": "check",
            "reference_number": "check-never",
            "amount": "10.00",
        },
        "owner",
    ),
    (
        "/api/v1/payments/submit-zelle",
        lambda ctx: {"invoice_id": str(ctx.invoice.id), "amount": "10.00"},
        "customer",
    ),
    (
        "/api/v1/invoice-access/create-payment-intent",
        lambda _ctx: {"token": "guest-token", "amount": "10.00"},
        "guest",
    ),
    (
        "/api/v1/invoice-access/confirm-payment",
        lambda _ctx: {"token": "guest-token", "payment_intent_id": "pi_never"},
        "guest",
    ),
    (
        "/api/v1/invoice-access/submit-zelle",
        lambda _ctx: {"token": "guest-token", "amount": "10.00"},
        "guest",
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("path,body_factory,audience", ADAPTER_CASES)
async def test_all_compatibility_adapters_reject_soft_deleted_invoice_before_effects(
    client,
    db_session,
    monkeypatch,
    path,
    body_factory,
    audience,
):
    monkeypatch.setattr(settings, "INVOICE_SPLIT_PAYMENTS_ENABLED", True)
    context = await _seed_adapter_context(db_session)
    context.invoice.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    payload = {
        "invoice_id": str(context.invoice.id),
        "customer_id": str(context.customer.id),
        "tenant_id": str(context.tenant.id),
    }

    async def guest_payload(_token: str):
        return payload

    monkeypatch.setattr(invoice_access, "_get_active_invoice_payload_or_400", guest_payload)
    monkeypatch.setattr(invoice_access, "_get_invoice_payload_for_confirm_or_400", guest_payload)
    calls = _forbid_adapter_side_effects(monkeypatch)
    before = await _mutation_snapshot(db_session, context.invoice.id)

    headers = {}
    if audience == "customer":
        headers = context.customer_headers
    elif audience == "owner":
        headers = context.owner_headers
    response = await client.post(path, json=body_factory(context), headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "invoice_not_found"
    assert calls == []
    assert await _mutation_snapshot(db_session, context.invoice.id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_state",
    ("voided_invoice", "cancelled_invoice", "deleted_order", "cancelled_order"),
)
@pytest.mark.parametrize("audience", ("customer", "guest"))
async def test_adapter_boundaries_hide_all_inactive_invoice_states(
    client,
    db_session,
    monkeypatch,
    invalid_state,
    audience,
):
    monkeypatch.setattr(settings, "INVOICE_SPLIT_PAYMENTS_ENABLED", True)
    context = await _seed_adapter_context(db_session)
    if invalid_state == "voided_invoice":
        context.invoice.voided_at = datetime.now(timezone.utc)
    elif invalid_state == "cancelled_invoice":
        context.invoice.status = InvoiceStatus.CANCELLED
    elif invalid_state == "deleted_order":
        context.order.deleted_at = datetime.now(timezone.utc)
    else:
        context.order.status = RepairOrderStatus.CANCELLED
    await db_session.commit()

    payload = {
        "invoice_id": str(context.invoice.id),
        "customer_id": str(context.customer.id),
        "tenant_id": str(context.tenant.id),
    }

    async def guest_payload(_token: str):
        return payload

    monkeypatch.setattr(invoice_access, "_get_active_invoice_payload_or_400", guest_payload)
    calls = _forbid_adapter_side_effects(monkeypatch)
    before = await _mutation_snapshot(db_session, context.invoice.id)

    if audience == "customer":
        response = await client.post(
            "/api/v1/payments/submit-zelle",
            json={"invoice_id": str(context.invoice.id), "amount": "10.00"},
            headers=context.customer_headers,
        )
    else:
        response = await client.post(
            "/api/v1/invoice-access/submit-zelle",
            json={"token": "guest-token", "amount": "10.00"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "invoice_not_found"
    assert calls == []
    assert await _mutation_snapshot(db_session, context.invoice.id) == before


@pytest.mark.asyncio
async def test_customer_foreign_and_missing_invoice_ids_share_generic_404(
    client,
    db_session,
    monkeypatch,
):
    context = await _seed_adapter_context(db_session)
    calls = _forbid_adapter_side_effects(monkeypatch)
    headers = context.customer_headers

    foreign = await client.post(
        "/api/v1/payments/submit-zelle",
        json={"invoice_id": str(context.foreign_invoice.id), "amount": "10.00"},
        headers=headers,
    )
    missing = await client.post(
        "/api/v1/payments/submit-zelle",
        json={"invoice_id": str(uuid4()), "amount": "10.00"},
        headers=headers,
    )

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["error"]["code"] == "invoice_not_found"
    assert calls == []


@pytest.mark.asyncio
async def test_guest_foreign_and_missing_token_subjects_share_generic_404(
    client,
    db_session,
    monkeypatch,
):
    context = await _seed_adapter_context(db_session)

    async def guest_payload(token: str):
        return {
            "invoice_id": (
                str(context.foreign_invoice.id) if token == "foreign-token" else str(uuid4())
            ),
            "customer_id": str(context.customer.id),
            "tenant_id": str(context.tenant.id),
        }

    monkeypatch.setattr(invoice_access, "_get_active_invoice_payload_or_400", guest_payload)
    calls = _forbid_adapter_side_effects(monkeypatch)

    foreign = await client.post(
        "/api/v1/invoice-access/submit-zelle",
        json={"token": "foreign-token", "amount": "10.00"},
    )
    missing = await client.post(
        "/api/v1/invoice-access/submit-zelle",
        json={"token": "missing-token", "amount": "10.00"},
    )

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["error"]["code"] == "invoice_not_found"
    assert calls == []


@pytest.mark.asyncio
async def test_create_attempt_rejects_deleted_order_before_readiness_or_mutation(
    db_session,
    monkeypatch,
):
    context = await _seed_adapter_context(db_session)
    context.order.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    async def forbidden_readiness(*_args, **_kwargs):
        raise AssertionError("feature/provider readiness evaluated before invoice authorization")

    monkeypatch.setattr(
        "app.services.invoice_settlement_service.require_feature_ready",
        forbidden_readiness,
    )
    with pytest.raises(SettlementDomainError) as error:
        await create_attempt(
            db_session,
            invoice=context.invoice,
            tenant=context.tenant,
            customer_id=context.customer.id,
            actor=context.owner,
            amount=Decimal("10.00"),
            rail="check",
            expected_settlement_version=1,
            idempotency_key="deleted-order-attempt",
            source="staff",
            subject_type="staff",
            subject_id=context.owner.id,
        )

    assert error.value.code == "invoice_not_found"
    assert error.value.status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(InvoiceSettlement)) == 0
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt)) == 0
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent)) == 0
