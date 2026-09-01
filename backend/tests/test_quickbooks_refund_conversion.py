from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints import quickbooks
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


@pytest.mark.asyncio
async def test_quickbooks_refund_is_unavailable_while_external_approval_is_closed(db_session, monkeypatch):
    tenant = Tenant(
        name="Refund Garage", slug=f"refund-{uuid4().hex}", paid_invoice_webhook_enabled=True,
        paid_invoice_webhook_url="https://hooks.example.com/conversions",
        paid_invoice_webhook_secret_encrypted="encrypted",
    )
    owner = User(
        tenant=tenant, email=f"owner-{uuid4().hex}@example.com", hashed_password="x", first_name="Owner",
        last_name="One", role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    customer = Customer(tenant=tenant, first_name="Test", last_name="Customer", email="refund@example.com")
    order = RepairOrder(
        tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"RO-{uuid4().hex}",
        status=RepairOrderStatus.PAID,
    )
    invoice = Invoice(
        tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID,
        subtotal=Decimal("100"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("100"),
    )
    payment = Payment(
        tenant=tenant, invoice=invoice, payment_number=f"PAY-{uuid4().hex}", amount=Decimal("100"),
        method=PaymentMethod.QUICKBOOKS, status=PaymentStatus.COMPLETED,
        quickbooks_charge_id="charge-refund", quickbooks_charge_status="CAPTURED",
    )
    db_session.add_all([tenant, owner, customer, order, invoice, payment])
    await db_session.commit()

    provider_calls = 0

    async def provider_call_forbidden(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("QuickBooks Payments provider execution must remain gated")

    monkeypatch.setattr(
        quickbooks.settings,
        "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED",
        False,
    )
    monkeypatch.setattr(quickbooks, "_get_connection", provider_call_forbidden)
    monkeypatch.setattr(quickbooks, "refund_charge", provider_call_forbidden)

    with pytest.raises(HTTPException) as exc_info:
        await quickbooks.refund_quickbooks_payment(
            payment.id,
            quickbooks.QuickBooksRefundRequest(amount=Decimal("25"), reason="Customer adjustment"),
            db=db_session,
            current_user=owner,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "QuickBooks Payments is not approved for this environment"
    assert provider_calls == 0
    assert (await db_session.execute(select(ProviderOutboxEvent))).scalars().all() == []
    assert payment.quickbooks_refunded_amount in (None, Decimal("0"))
    assert invoice.status == InvoiceStatus.PAID
    assert order.status == RepairOrderStatus.PAID


@pytest.mark.asyncio
async def test_quickbooks_charge_is_blocked_before_provider_or_accounting_work(
    db_session, monkeypatch,
):
    customer_user = User(
        tenant_id=uuid4(), customer_id=uuid4(),
        email=f"qbp-customer-{uuid4().hex}@example.com",
        hashed_password="x", first_name="QBP", last_name="Customer",
        role=UserRole.CUSTOMER, is_active=True, is_verified=True,
    )
    provider_calls = 0

    async def forbidden(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("dormant QBP must not execute provider/accounting work")

    monkeypatch.setattr(
        quickbooks.settings,
        "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED",
        False,
    )
    monkeypatch.setattr(quickbooks, "_get_connection", forbidden)
    monkeypatch.setattr(quickbooks, "create_charge", forbidden)
    monkeypatch.setattr(quickbooks, "finalize_quickbooks_invoice_payment", forbidden)

    with pytest.raises(HTTPException) as exc_info:
        await quickbooks.charge_quickbooks_invoice(
            quickbooks.QuickBooksChargeRequest(
                invoice_id=uuid4(), token="opaque-token",
                idempotency_key="qbp_dormant_charge_01",
            ),
            db=db_session,
            current_user=customer_user,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "QuickBooks Payments is not approved for this environment"
    assert provider_calls == 0
    assert (await db_session.execute(select(Payment))).scalars().all() == []
    assert (await db_session.execute(select(ProviderOutboxEvent))).scalars().all() == []


@pytest.mark.asyncio
async def test_legacy_quickbooks_charge_hides_foreign_invoice_like_missing_invoice(
    db_session, monkeypatch,
):
    own_tenant = Tenant(name="Own QBP Garage", slug=f"own-qbp-{uuid4().hex}")
    foreign_tenant = Tenant(name="Foreign QBP Garage", slug=f"foreign-qbp-{uuid4().hex}")
    db_session.add_all([own_tenant, foreign_tenant])
    await db_session.flush()
    own_customer = Customer(
        tenant_id=own_tenant.id,
        first_name="Own",
        last_name="Customer",
        email=f"qbp-own-customer-{uuid4().hex}@example.com",
    )
    db_session.add(own_customer)
    await db_session.flush()
    current_user = User(
        tenant_id=own_tenant.id,
        customer_id=own_customer.id,
        email=f"qbp-own-{uuid4().hex}@example.com",
        hashed_password="x",
        first_name="Own",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    foreign_customer = Customer(
        tenant_id=foreign_tenant.id,
        first_name="Foreign",
        last_name="Customer",
        email=f"qbp-foreign-{uuid4().hex}@example.com",
    )
    db_session.add_all([current_user, foreign_customer])
    await db_session.flush()
    foreign_order = RepairOrder(
        tenant_id=foreign_tenant.id,
        customer_id=foreign_customer.id,
        vehicle_id=uuid4(),
        order_number=f"RO-{uuid4().hex}",
        status=RepairOrderStatus.INVOICED,
    )
    db_session.add(foreign_order)
    await db_session.flush()
    foreign_invoice = Invoice(
        tenant_id=foreign_tenant.id,
        repair_order_id=foreign_order.id,
        invoice_number=f"INV-{uuid4().hex}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("25.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("25.00"),
    )
    db_session.add(foreign_invoice)
    nonpayable_invoice_ids = []
    for invoice_status in (InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED):
        order = RepairOrder(
            tenant_id=own_tenant.id,
            customer_id=own_customer.id,
            vehicle_id=uuid4(),
            order_number=f"RO-{invoice_status.value}-{uuid4().hex}",
            status=RepairOrderStatus.INVOICED,
        )
        db_session.add(order)
        await db_session.flush()
        invoice = Invoice(
            tenant_id=own_tenant.id,
            repair_order_id=order.id,
            invoice_number=f"INV-{invoice_status.value}-{uuid4().hex}",
            status=invoice_status,
            subtotal=Decimal("25.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("25.00"),
        )
        db_session.add(invoice)
        await db_session.flush()
        nonpayable_invoice_ids.append(invoice.id)
    await db_session.commit()

    calls = 0

    async def forbidden(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("foreign or missing invoice must not reach payment services")

    monkeypatch.setattr(
        quickbooks.settings,
        "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED",
        True,
    )
    monkeypatch.setattr(quickbooks, "settlement_for_compatibility_route", forbidden)
    monkeypatch.setattr(quickbooks, "_get_connection", forbidden)
    monkeypatch.setattr(quickbooks, "create_charge", forbidden)

    errors = []
    for invoice_id in (foreign_invoice.id, uuid4(), *nonpayable_invoice_ids):
        with pytest.raises(HTTPException) as exc_info:
            await quickbooks.charge_quickbooks_invoice(
                quickbooks.QuickBooksChargeRequest(
                    invoice_id=invoice_id,
                    token="opaque-token",
                    idempotency_key=f"qbp-hidden-{invoice_id}",
                ),
                db=db_session,
                current_user=current_user,
            )
        errors.append((exc_info.value.status_code, exc_info.value.detail))

    assert errors == [(404, "Invoice not found")] * 4
    assert calls == 0
    assert (await db_session.execute(select(Payment))).scalars().all() == []
    assert (await db_session.execute(select(ProviderOutboxEvent))).scalars().all() == []
