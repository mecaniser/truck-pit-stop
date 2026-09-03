from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import stripe
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    CustomerCreditEntry,
    InvoicePaymentAttempt,
    InvoicePaymentLedgerEvent,
    InvoiceSettlement,
    InvoiceSettlementBackfillRun,
    PaymentAccountingLink,
    PaymentOverpayment,
    PaymentProviderDispute,
    PaymentRefund,
    TenantPaymentProviderConfiguration,
)
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.api.v1.endpoints import invoice_settlements as settlement_endpoints
from app.api.v1.endpoints import invoice_access as invoice_access_endpoints
from app.api.v1.endpoints import quickbooks as quickbooks_endpoints
from app.api.v1.endpoints.invoice_settlements import (
    allocation_page,
    customer_credit_aging,
    export_customer_credit_aging,
    read_invoice_settlement,
    record_customer_credit_due_diligence,
    settlement_summary,
    update_card_provider_configuration,
)
from app.schemas.invoice_settlement import (
    CardProviderConfigurationUpdate,
    CreditApplicationCreate,
    CreditDueDiligenceCreate,
)
from app.main import settlement_domain_exception_handler
from app.services.invoice_settlement_service import (
    SettlementDomainError,
    allocatable_balance,
    authorize_early_release,
    available_credit,
    apply_customer_credit,
    confirm_attempt,
    create_attempt,
    fail_attempt,
    get_or_create_settlement,
    load_active_configuration,
    money,
    provider_readiness,
    record_credit_consent,
    settlement_for_compatibility_route,
)
from app.services.db048_accounting_reconciliation import (
    _submit_stripe_refund,
    close_stripe_dispute,
    reconcile_due_card_attempts,
    record_stripe_dispute,
    reverse_confirmed_attempt,
)
from app.services import db048_accounting_reconciliation as reconciliation_service
from app.services.quickbooks_payments_service import QuickBooksPaymentError
from app.api.v1.endpoints.quickbooks import QuickBooksChargeRequest


def test_guest_invoice_token_has_no_customer_wallet_routes():
    paths = {route.path for route in invoice_access_endpoints.router.routes}
    assert "/eligible-credits" not in paths
    assert "/customer-credits/{credit_id}/applications" not in paths
    assert "/overpayments/{overpayment_id}/credit-consent" in paths


async def _financial_context(db, monkeypatch, *, principal=Decimal("100.00"), fee=Decimal("3.00")):
    monkeypatch.setattr(settings, "INVOICE_SPLIT_PAYMENTS_ENABLED", True)
    monkeypatch.setattr(settings, "STRIPE_CONNECT_INVOICE_PAYMENTS_APPROVED", True)
    tenant = Tenant(
        name="DB048 Garage",
        slug=f"db048-{uuid4().hex}",
        invoice_split_payments_enabled=True,
        stripe_account_id=f"acct_{uuid4().hex}",
        stripe_onboarding_complete=True,
    )
    db.add(tenant)
    await db.flush()
    owner = User(
        email=f"owner-{uuid4().hex}@example.com",
        hashed_password="hash",
        first_name="Garage",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Split",
        last_name="Customer",
        email=f"customer-{uuid4().hex}@example.com",
    )
    db.add_all([owner, customer])
    await db.flush()
    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Volvo",
        model="VNL",
    )
    db.add(vehicle)
    await db.flush()
    order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:10]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0"),
        total_labor_cost=principal,
        total_cost=principal,
    )
    db.add(order)
    await db.flush()
    invoice = Invoice(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        invoice_number=f"INV-{uuid4().hex[:10]}",
        status=InvoiceStatus.SENT,
        subtotal=principal,
        shop_supplies_amount=Decimal("0"),
        service_fee_amount=fee,
        tax_amount=Decimal("0"),
        discount_amount=Decimal("0"),
        total_amount=principal + fee,
    )
    db.add(invoice)
    await db.flush()
    qbo_realm = f"realm-{uuid4().hex}"
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=1,
        selected_provider="stripe_connect",
        readiness_state="ready",
        is_active=True,
        actor_user_id=owner.id,
        actor_name_snapshot="Garage Owner",
        provider_account_snapshot=tenant.stripe_account_id,
        qbo_realm_snapshot=qbo_realm,
        writer_strategy="dieselbridge",
        idempotency_key="initial-provider-config",
        request_hash="0" * 64,
        stripe_clearing_account="Stripe Clearing",
        qbp_clearing_account="QBP Clearing",
        check_deposit_account="Undeposited Funds",
        zelle_ach_account="Zelle Clearing",
        card_fee_income_account="Card Fee Income",
        processor_fee_expense_account="Processor Fees",
        sales_tax_liability_account="Sales Tax Payable",
        checking_account="Checking",
    )
    connection = QuickBooksConnection(
        tenant_id=tenant.id,
        realm_id=qbo_realm,
        status="connected",
        scopes="com.intuit.quickbooks.accounting",
        encrypted_access_token="test",
    )
    db.add_all([config, connection])
    db.add(InvoiceSettlementBackfillRun(
        tenant_id=tenant.id,
        cutoff_at=datetime.now(timezone.utc),
        state="verified",
        source_counts={"eligible_invoices": 0, "payments": 0, "pending_zelle": 0},
        inserted_counts={"settlements": 0, "attempts": 0, "events": 0},
        source_checksums={"eligible_invoices": "0" * 64, "payments": "0" * 64, "pending_zelle": "0" * 64},
        reconciled_at=datetime.now(timezone.utc),
        verified_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    invoice.repair_order = order
    order.customer = customer
    return tenant, owner, customer, invoice


async def _add_eligible_invoice(
    db,
    *,
    tenant: Tenant,
    customer: Customer,
    reference_invoice: Invoice,
    with_shadow_settlement: bool,
) -> Invoice:
    order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=reference_invoice.repair_order.vehicle_id,
        order_number=f"RO-READINESS-{uuid4().hex[:10]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0"),
        total_labor_cost=Decimal("50"),
        total_cost=Decimal("50"),
    )
    db.add(order)
    await db.flush()
    invoice = Invoice(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        invoice_number=f"INV-READINESS-{uuid4().hex[:10]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("50"),
        shop_supplies_amount=Decimal("0"),
        service_fee_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        discount_amount=Decimal("0"),
        total_amount=Decimal("50"),
    )
    db.add(invoice)
    await db.flush()
    invoice.repair_order = order
    order.customer = customer
    if with_shadow_settlement:
        await get_or_create_settlement(
            db,
            invoice=invoice,
            customer_id=customer.id,
            tenant=tenant,
        )
    await db.commit()
    return invoice


@pytest.mark.asyncio
async def test_mixed_tenders_keep_legacy_payment_principal_only(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db_session, monkeypatch)
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    card = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("40.00"),
        rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key="card-40",
        source="customer_portal",
        subject_type="customer",
        subject_id=customer.id,
    )
    card.attempt.provider_intent_id = "pi_card_40"
    card_confirmation = await confirm_attempt(
        db_session,
        attempt_id=card.attempt.id,
        tenant=tenant,
        actor=owner,
        expected_attempt_version=card.attempt.version,
        idempotency_key="confirm-card-40",
        received_principal=Decimal("40.00"),
        reference="pi_card_40",
        provider_charge_id="ch_card_40",
        provider_event_id="evt_card_40",
    )
    assert card_confirmation.paid_transition is False
    assert money(card_confirmation.payment.amount) == Decimal("40.00")
    assert money(card_confirmation.attempt.provider_charge_amount) == Decimal("41.20")
    assert invoice.status == InvoiceStatus.SENT

    zelle = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("60.00"),
        rail="zelle",
        expected_settlement_version=card_confirmation.settlement.version,
        idempotency_key="zelle-60",
        source="staff",
        subject_type="staff",
        subject_id=owner.id,
        sender_evidence={"reference_number": "zelle-ref-60"},
    )
    final = await confirm_attempt(
        db_session,
        attempt_id=zelle.attempt.id,
        tenant=tenant,
        actor=owner,
        expected_attempt_version=zelle.attempt.version,
        idempotency_key="confirm-zelle-60",
        received_principal=Decimal("60.00"),
        reference="zelle-ref-60",
    )
    await db_session.commit()
    payment_total = await db_session.scalar(select(func.sum(Payment.amount)).where(Payment.invoice_id == invoice.id))
    assert money(payment_total) == Decimal("100.00")
    assert final.paid_transition is True
    assert invoice.status == InvoiceStatus.PAID
    assert money(final.settlement.confirmed_principal) == Decimal("100.00")
    assert money(final.settlement.active_pending_principal) == Decimal("0.00")


@pytest.mark.asyncio
async def test_pending_zelle_reserves_only_declared_principal_and_replay_is_idempotent(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db_session, monkeypatch, principal=Decimal("834"), fee=Decimal("0"))
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    first = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("500"), rail="zelle",
        expected_settlement_version=settlement.version,
        idempotency_key="zelle-500", source="customer_portal",
        subject_type="customer", subject_id=customer.id,
        sender_evidence={"sender_email": "customer@example.com"},
    )
    replay = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("500"), rail="zelle",
        expected_settlement_version=1,
        idempotency_key="zelle-500", source="customer_portal",
        subject_type="customer", subject_id=customer.id,
        sender_evidence={"sender_email": "customer@example.com"},
    )
    assert replay.replayed is True
    assert replay.attempt.id == first.attempt.id
    assert allocatable_balance(first.settlement) == Decimal("334.00")
    summary = await settlement_summary(
        db_session, first.settlement, tenant, audience="customer", current_user=owner,
    )
    assert summary.outstanding_balance == Decimal("834.00")
    assert summary.active_pending_principal == Decimal("500.00")
    assert summary.allocatable_balance == Decimal("334.00")
    with pytest.raises(SettlementDomainError) as error:
        await create_attempt(
            db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
            actor=owner, amount=Decimal("335"), rail="card",
            expected_settlement_version=first.settlement.version,
            idempotency_key="card-too-large", source="customer_portal",
            subject_type="customer", subject_id=customer.id,
        )
    assert error.value.code == "payment_amount_exceeds_allocatable_balance"


@pytest.mark.asyncio
async def test_confirm_replay_does_not_duplicate_payment_or_accounting(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db_session, monkeypatch, fee=Decimal("0"))
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    attempt = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("100"), rail="check",
        expected_settlement_version=settlement.version,
        idempotency_key="check-create", source="staff", subject_type="staff",
        subject_id=owner.id, sender_evidence={"reference_number": "check-101"},
    )
    first = await confirm_attempt(
        db_session, attempt_id=attempt.attempt.id, tenant=tenant, actor=owner,
        expected_attempt_version=attempt.attempt.version,
        idempotency_key="check-confirm", reference="check-101",
    )
    second = await confirm_attempt(
        db_session, attempt_id=attempt.attempt.id, tenant=tenant, actor=owner,
        expected_attempt_version=1,
        idempotency_key="check-confirm", reference="check-101",
    )
    assert second.replayed is True
    assert second.payment.id == first.payment.id
    assert await db_session.scalar(select(func.count()).select_from(Payment).where(Payment.invoice_id == invoice.id)) == 1


@pytest.mark.asyncio
async def test_append_only_payment_ledger_rejects_orm_update(db_session, monkeypatch):
    tenant, _owner, customer, invoice = await _financial_context(db_session, monkeypatch)
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    await db_session.flush()
    event = InvoicePaymentLedgerEvent(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        settlement_id=settlement.id,
        customer_id=customer.id,
        actor_name_snapshot="System",
        sequence=1,
        idempotency_key="append-only-test",
        event_type="test",
        principal_delta=Decimal("0"),
        pending_delta=Decimal("0"),
        unapplied_delta=Decimal("0"),
        refund_pending_delta=Decimal("0"),
        money_snapshot={},
        evidence_snapshot={},
    )
    db_session.add(event)
    await db_session.flush()
    event.event_type = "tampered"
    with pytest.raises(ValueError, match="append-only"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_payment_attempt_rejects_orm_soft_and_hard_delete(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db_session, monkeypatch)
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant
    )
    result = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("25"),
        rail="check",
        expected_settlement_version=settlement.version,
        idempotency_key="attempt-delete-guard",
        source="staff",
        subject_type="staff",
        subject_id=owner.id,
        sender_evidence={"reference_number": "guard-25"},
    )
    await db_session.commit()
    attempt_id = result.attempt.id

    result.attempt.deleted_at = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="attempts cannot be deleted"):
        await db_session.flush()
    await db_session.rollback()

    attempt = await db_session.get(InvoicePaymentAttempt, attempt_id)
    await db_session.delete(attempt)
    with pytest.raises(ValueError, match="attempts cannot be deleted"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_domain_error_handler_preserves_safe_contract():
    response = await settlement_domain_exception_handler(
        SimpleNamespace(),
        SettlementDomainError(
            "invoice_not_found", "Invoice not found.", status_code=404,
            retryable=False, current_version=7,
        ),
    )
    assert response.status_code == 404
    assert json.loads(response.body) == {
        "error": {
            "code": "invoice_not_found",
            "message": "Invoice not found.",
            "retryable": False,
            "current_version": 7,
        }
    }


@pytest.mark.asyncio
async def test_accidental_card_overpayment_is_unapplied_and_refund_first(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db_session, monkeypatch, fee=Decimal("0"))
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    creation = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("100"), rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key="overpay-create", source="customer_portal",
        subject_type="customer", subject_id=customer.id,
    )
    creation.attempt.provider_intent_id = "pi_overpay"
    # Model an already-verified provider receipt whose immutable gross exceeds
    # the invoice principal. Public Stripe finalizers separately enforce this
    # snapshot against the signed provider amount.
    creation.attempt.provider_charge_amount = Decimal("110.00")
    result = await confirm_attempt(
        db_session, attempt_id=creation.attempt.id, tenant=tenant, actor=None,
        expected_attempt_version=creation.attempt.version,
        idempotency_key="overpay-confirm", received_principal=Decimal("110"),
        reference="pi_overpay", provider_charge_id="ch_overpay",
        provider_event_id="evt_overpay",
    )
    await db_session.flush()
    assert money(result.payment.amount) == Decimal("100.00")
    assert money(result.attempt.unapplied_amount) == Decimal("10.00")
    assert result.overpayment.state == "refund_required"
    assert result.refund.mode == "automatic"
    assert result.refund.state == "pending"
    assert money(result.settlement.unapplied_credit) == Decimal("10.00")
    assert money(result.settlement.refund_pending) == Decimal("10.00")
    refund_event = await db_session.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.aggregate_id == result.refund.id,
        ProviderOutboxEvent.event_type == "payment_refund.provider_submit",
    ))
    assert refund_event is not None


@pytest.mark.asyncio
async def test_credit_consent_channel_is_server_bound_to_principal(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    creation = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("100"), rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key="consent-channel-create", source="customer_portal",
        subject_type="customer", subject_id=customer.id,
    )
    creation.attempt.provider_intent_id = "pi_consent_channel"
    creation.attempt.provider_charge_amount = Decimal("110.00")
    confirmed = await confirm_attempt(
        db_session, attempt_id=creation.attempt.id, tenant=tenant, actor=None,
        expected_attempt_version=creation.attempt.version,
        idempotency_key="consent-channel-confirm",
        received_principal=Decimal("110"), reference="pi_consent_channel",
        provider_charge_id="ch_consent_channel",
        provider_event_id="evt_consent_channel",
    )
    customer_user = User(
        email=f"credit-customer-{uuid4().hex}@example.com",
        hashed_password="hash", first_name="Credit", last_name="Customer",
        role=UserRole.CUSTOMER, tenant_id=tenant.id, customer_id=customer.id,
        is_active=True, is_verified=True,
    )
    db_session.add(customer_user)
    await db_session.flush()

    invalid_cases = [
        (owner, "customer_portal", "owner-cannot-forge-customer"),
        (customer_user, "in_person", "customer-cannot-forge-staff"),
        (None, "customer_portal", "guest-cannot-forge-portal"),
    ]
    for actor, channel, key in invalid_cases:
        with pytest.raises(SettlementDomainError) as error:
            await record_credit_consent(
                db_session, overpayment_id=confirmed.overpayment.id,
                tenant_id=tenant.id, actor=actor,
                subject_customer_id=customer.id, channel=channel,
                note="Keep the excess", idempotency_key=key,
            )
        assert error.value.code == "consent_channel_invalid"
        assert error.value.status_code == 422

    assert await db_session.scalar(select(func.count(CustomerCreditEntry.id)).where(
        CustomerCreditEntry.origin_overpayment_id == confirmed.overpayment.id,
    )) == 0
    credit = await record_credit_consent(
        db_session, overpayment_id=confirmed.overpayment.id,
        tenant_id=tenant.id, actor=owner,
        subject_customer_id=customer.id, channel="phone",
        note="Customer approved by phone", idempotency_key="staff-phone-consent",
    )
    assert credit.consent_channel == "phone"


@pytest.mark.asyncio
async def test_credit_aging_due_diligence_csv_safety_and_tenant_isolation(
    db_session, monkeypatch,
):
    tenant, owner, customer, _invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    customer.company_name = "=FORMULA-CUSTOMER"
    local_credit = CustomerCreditEntry(
        tenant_id=tenant.id, customer_id=customer.id, entry_type="issued",
        amount=Decimal("25.00"), actor_name_snapshot="Customer",
        consent_channel="phone", consent_note="+FORMULA-NOTE",
        idempotency_key="aging-local-credit", request_hash="a" * 64,
        occurred_at=datetime.now(timezone.utc) - timedelta(days=45),
    )
    foreign_tenant = Tenant(
        name="Foreign credit tenant", slug=f"foreign-credit-{uuid4().hex}",
    )
    db_session.add_all([local_credit, foreign_tenant])
    await db_session.flush()
    foreign_customer = Customer(
        tenant_id=foreign_tenant.id, first_name="Foreign", last_name="Holder",
        email=f"foreign-credit-{uuid4().hex}@example.com",
    )
    db_session.add(foreign_customer)
    await db_session.flush()
    foreign_credit = CustomerCreditEntry(
        tenant_id=foreign_tenant.id, customer_id=foreign_customer.id,
        entry_type="issued", amount=Decimal("99.00"),
        actor_name_snapshot="Foreign", consent_channel="phone",
        consent_note="not visible", idempotency_key="aging-foreign-credit",
        request_hash="b" * 64,
    )
    db_session.add(foreign_credit)
    await db_session.commit()

    body = CreditDueDiligenceCreate(
        channel="phone", note="Left a voicemail",
        next_review_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    first = await record_customer_credit_due_diligence(
        credit_id=local_credit.id, body=body,
        idempotency_header="due-diligence-local",
        db=db_session, current_user=owner,
    )
    replay = await record_customer_credit_due_diligence(
        credit_id=local_credit.id, body=body,
        idempotency_header="due-diligence-local",
        db=db_session, current_user=owner,
    )
    assert first["event_id"] == replay["event_id"]

    rows = await customer_credit_aging(db=db_session, current_user=owner)
    assert [row.credit_id for row in rows] == [local_credit.id]
    assert rows[0].remaining_amount == Decimal("25.00")
    assert rows[0].age_days >= 45
    assert rows[0].last_contact_channel == "phone"
    assert rows[0].last_contact_note == "Left a voicemail"

    response = await export_customer_credit_aging(
        db=db_session, current_user=owner,
    )
    csv_body = response.body.decode()
    assert str(local_credit.id) in csv_body
    assert str(foreign_credit.id) not in csv_body
    assert "'=FORMULA-CUSTOMER" in csv_body
    assert "'+FORMULA-NOTE" in csv_body

    with pytest.raises(SettlementDomainError) as error:
        await record_customer_credit_due_diligence(
            credit_id=foreign_credit.id, body=body,
            idempotency_header="due-diligence-foreign",
            db=db_session, current_user=owner,
        )
    assert error.value.code == "invoice_not_found"
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_late_card_success_refunds_full_unearned_gross_and_preserves_charge_snapshot(
    db_session,
    monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("3.00"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    # Explicit frozen fee-tax snapshot keeps this regression independent of
    # the simplified invoice fixture's tax-line construction.
    settlement.max_card_fee_tax = Decimal("0.15")
    card = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("100.00"), rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key="late-card-create", source="customer_portal",
        subject_type="customer", subject_id=customer.id,
    )
    card.attempt.provider_intent_id = "pi_late_card"
    assert money(card.attempt.card_fee_amount) == Decimal("3.00")
    assert money(card.attempt.card_fee_tax_amount) == Decimal("0.15")
    assert money(card.attempt.provider_charge_amount) == Decimal("103.15")

    await fail_attempt(
        db_session, attempt_id=card.attempt.id, tenant_id=tenant.id,
        actor=None, expected_attempt_version=card.attempt.version,
        failure_code="provider_status_requires_review",
        idempotency_key="late-card-release", expired=True,
    )
    manual = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("100.00"), rail="zelle",
        expected_settlement_version=card.settlement.version,
        idempotency_key="late-card-competing-zelle", source="staff",
        subject_type="staff", subject_id=owner.id,
        sender_evidence={"reference_number": "zelle-filled-balance"},
    )
    await confirm_attempt(
        db_session, attempt_id=manual.attempt.id, tenant=tenant, actor=owner,
        expected_attempt_version=manual.attempt.version,
        idempotency_key="late-card-confirm-zelle",
        received_principal=Decimal("100.00"), reference="zelle-filled-balance",
    )

    late = await confirm_attempt(
        db_session, attempt_id=card.attempt.id, tenant=tenant, actor=None,
        expected_attempt_version=card.attempt.version,
        idempotency_key="late-card-provider-success",
        received_principal=Decimal("100.00"), reference="pi_late_card",
        provider_charge_id="ch_late_card", provider_event_id="evt_late_card",
    )
    await db_session.flush()

    assert money(late.payment.amount) == Decimal("0.00")
    assert money(late.attempt.applied_principal_amount) == Decimal("0.00")
    # Creation-time charge evidence remains frozen.
    assert money(late.attempt.card_fee_amount) == Decimal("3.00")
    assert money(late.attempt.card_fee_tax_amount) == Decimal("0.15")
    assert money(late.attempt.provider_charge_amount) == Decimal("103.15")
    # Only earned components are visible to accounting; none were earned.
    assert money(late.attempt.applied_card_fee_amount) == Decimal("0.00")
    assert money(late.attempt.applied_card_fee_tax_amount) == Decimal("0.00")
    assert money(late.attempt.unapplied_amount) == Decimal("103.15")
    assert money(late.overpayment.amount) == Decimal("103.15")
    assert money(late.refund.amount) == Decimal("103.15")
    assert money(late.settlement.unapplied_credit) == Decimal("103.15")
    assert money(late.settlement.refund_pending) == Decimal("103.15")

    with pytest.raises(SettlementDomainError) as credit_error:
        await record_credit_consent(
            db_session, overpayment_id=late.overpayment.id,
            tenant_id=tenant.id, actor=owner, subject_customer_id=customer.id,
            channel="in_person", note="Customer asked for credit",
            idempotency_key="late-card-credit-blocked",
        )
    assert credit_error.value.code == "refund_required"

    refund_event = await db_session.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.aggregate_id == late.refund.id,
        ProviderOutboxEvent.event_type == "payment_refund.provider_submit",
    ))
    provider_calls: list[dict] = []

    def fake_refund_create(**kwargs):
        provider_calls.append(kwargs)
        return SimpleNamespace(id="re_late_card", status="pending")

    monkeypatch.setattr(stripe.Refund, "create", fake_refund_create)
    await _submit_stripe_refund(db_session, refund_event)
    assert provider_calls[0]["amount"] == 10315
    assert provider_calls[0]["refund_application_fee"] is True
    assert "reverse_transfer" not in provider_calls[0]


@pytest.mark.asyncio
async def test_card_fee_allocation_after_noncard_payment_is_proportional(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("3.00"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    settlement.max_card_fee_tax = Decimal("0.15")
    zelle = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("60.00"), rail="zelle",
        expected_settlement_version=settlement.version,
        idempotency_key="zelle-before-card", source="staff",
        subject_type="staff", subject_id=owner.id,
        sender_evidence={"reference_number": "zelle-before-card"},
    )
    await confirm_attempt(
        db_session, attempt_id=zelle.attempt.id, tenant=tenant, actor=owner,
        expected_attempt_version=zelle.attempt.version,
        idempotency_key="confirm-zelle-before-card",
        reference="zelle-before-card",
    )
    readiness = await provider_readiness(db_session, tenant)
    assert readiness.status == "ready", readiness.reasons
    card = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("40.00"), rail="card",
        expected_settlement_version=zelle.settlement.version,
        idempotency_key="card-after-zelle", source="customer_portal",
        subject_type="customer", subject_id=customer.id,
    )
    assert money(card.attempt.card_fee_amount) == Decimal("1.20")
    assert money(card.attempt.card_fee_tax_amount) == Decimal("0.06")
    assert money(card.attempt.provider_charge_amount) == Decimal("41.26")


@pytest.mark.asyncio
async def test_cross_tenant_attempt_confirmation_is_generic_not_found(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db_session, monkeypatch, fee=Decimal("0"))
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    creation = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("20"), rail="check",
        expected_settlement_version=settlement.version,
        idempotency_key="tenant-a-attempt", source="staff", subject_type="staff",
        subject_id=owner.id, sender_evidence={"reference_number": "C-1"},
    )
    foreign = Tenant(name="Foreign", slug=f"foreign-{uuid4().hex}")
    db_session.add(foreign)
    await db_session.flush()
    with pytest.raises(SettlementDomainError) as error:
        await confirm_attempt(
            db_session, attempt_id=creation.attempt.id, tenant=foreign, actor=None,
            expected_attempt_version=creation.attempt.version,
            idempotency_key="foreign-confirm", reference="C-1",
        )
    assert error.value.status_code == 404
    assert error.value.code == "invoice_not_found"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("invoice", "deleted_at", "now"),
        ("invoice", "voided_at", "now"),
        ("invoice", "status", InvoiceStatus.CANCELLED),
        ("order", "deleted_at", "now"),
        ("order", "status", RepairOrderStatus.CANCELLED),
    ],
)
async def test_confirm_attempt_rejects_inaccessible_lifecycle_before_mutation(
    db_session, monkeypatch, target, field, value,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    creation = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("25"), rail="check",
        expected_settlement_version=settlement.version,
        idempotency_key=f"lifecycle-{target}-{field}", source="staff",
        subject_type="staff", subject_id=owner.id,
        sender_evidence={"reference_number": f"LIFE-{target}-{field}"},
    )
    await db_session.flush()
    subject = invoice if target == "invoice" else invoice.repair_order
    setattr(subject, field, datetime.now(timezone.utc) if value == "now" else value)
    await db_session.flush()
    payment_count_before = await db_session.scalar(select(func.count(Payment.id)).where(
        Payment.invoice_id == invoice.id,
    ))
    event_count_before = await db_session.scalar(select(func.count(InvoicePaymentLedgerEvent.id)).where(
        InvoicePaymentLedgerEvent.settlement_id == settlement.id,
    ))
    pending_before = money(settlement.active_pending_principal)

    with pytest.raises(SettlementDomainError) as error:
        await confirm_attempt(
            db_session, attempt_id=creation.attempt.id, tenant=tenant,
            actor=owner, expected_attempt_version=creation.attempt.version,
            idempotency_key=f"confirm-{target}-{field}",
            reference=f"LIFE-{target}-{field}",
        )

    assert error.value.code == "invoice_not_found"
    assert error.value.status_code == 404
    assert await db_session.scalar(select(func.count(Payment.id)).where(
        Payment.invoice_id == invoice.id,
    )) == payment_count_before
    assert await db_session.scalar(select(func.count(InvoicePaymentLedgerEvent.id)).where(
        InvoicePaymentLedgerEvent.settlement_id == settlement.id,
    )) == event_count_before
    assert creation.attempt.state == "pending"
    assert money(settlement.active_pending_principal) == pending_before
    assert money(settlement.confirmed_principal) == Decimal("0.00")


@pytest.mark.asyncio
async def test_confirmed_attempt_replay_rechecks_lifecycle_before_returning_money(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    creation = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("25"), rail="check",
        expected_settlement_version=settlement.version,
        idempotency_key="confirmed-replay-lifecycle-create", source="staff",
        subject_type="staff", subject_id=owner.id,
        sender_evidence={"reference_number": "CONFIRMED-REPLAY"},
    )
    confirmed = await confirm_attempt(
        db_session, attempt_id=creation.attempt.id, tenant=tenant, actor=owner,
        expected_attempt_version=creation.attempt.version,
        idempotency_key="confirmed-replay-lifecycle-confirm",
        reference="CONFIRMED-REPLAY",
    )
    await db_session.flush()
    invoice.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()
    payment_count = await db_session.scalar(select(func.count(Payment.id)).where(
        Payment.invoice_id == invoice.id,
    ))
    event_count = await db_session.scalar(select(func.count(InvoicePaymentLedgerEvent.id)).where(
        InvoicePaymentLedgerEvent.settlement_id == settlement.id,
    ))
    settlement_version = settlement.version
    attempt_version = confirmed.attempt.version

    with pytest.raises(SettlementDomainError) as error:
        await confirm_attempt(
            db_session, attempt_id=confirmed.attempt.id, tenant=tenant,
            actor=owner, expected_attempt_version=confirmed.attempt.version,
            idempotency_key="confirmed-replay-lifecycle-replay",
            reference="CONFIRMED-REPLAY",
        )

    assert error.value.code == "invoice_not_found"
    assert error.value.status_code == 404
    assert await db_session.scalar(select(func.count(Payment.id)).where(
        Payment.invoice_id == invoice.id,
    )) == payment_count
    assert await db_session.scalar(select(func.count(InvoicePaymentLedgerEvent.id)).where(
        InvoicePaymentLedgerEvent.settlement_id == settlement.id,
    )) == event_count
    assert settlement.version == settlement_version
    assert confirmed.attempt.version == attempt_version


@pytest.mark.asyncio
async def test_provider_settings_mutation_replays_and_rejects_key_reuse(db_session, monkeypatch):
    tenant, owner, _customer, _invoice = await _financial_context(db_session, monkeypatch)
    body = CardProviderConfigurationUpdate(
        selected_provider="stripe_connect",
        expected_version=1,
        stripe_clearing_account="Stripe Clearing 2",
    )
    first = await update_card_provider_configuration(
        body=body,
        idempotency_header="settings-change-1",
        db=db_session,
        current_user=owner,
    )
    replay = await update_card_provider_configuration(
        body=body,
        idempotency_header="settings-change-1",
        db=db_session,
        current_user=owner,
    )
    assert first.configuration_version == replay.configuration_version == 2
    assert first.selected_provider == replay.selected_provider == "stripe_connect"
    with pytest.raises(SettlementDomainError) as error:
        await update_card_provider_configuration(
            body=CardProviderConfigurationUpdate(
                selected_provider="stripe_connect",
                expected_version=2,
                stripe_clearing_account="Different account",
            ),
            idempotency_header="settings-change-1",
            db=db_session,
            current_user=owner,
        )
    assert error.value.code == "idempotency_key_reused"


@pytest.mark.asyncio
async def test_quickbooks_payments_provider_setting_is_dormant_and_nonmutating(
    db_session, monkeypatch,
):
    tenant, owner, _customer, _invoice = await _financial_context(
        db_session, monkeypatch,
    )
    active_before = await load_active_configuration(db_session, tenant.id)
    count_before = await db_session.scalar(select(func.count(
        TenantPaymentProviderConfiguration.id
    )).where(TenantPaymentProviderConfiguration.tenant_id == tenant.id))

    with pytest.raises(SettlementDomainError) as error:
        await update_card_provider_configuration(
            body=CardProviderConfigurationUpdate(
                selected_provider="quickbooks_payments",
                expected_version=active_before.version,
            ),
            idempotency_header="qbp-remains-dormant",
            db=db_session,
            current_user=owner,
        )
    assert error.value.code == "quickbooks_payments_platform_approval_missing"
    assert await db_session.scalar(select(func.count(
        TenantPaymentProviderConfiguration.id
    )).where(TenantPaymentProviderConfiguration.tenant_id == tenant.id)) == count_before
    active_after = await load_active_configuration(db_session, tenant.id)
    assert active_after.id == active_before.id
    assert active_after.is_active is True


@pytest.mark.asyncio
async def test_quickbooks_payments_partial_attempt_uses_scoped_provider_and_confirms(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    connection = await db_session.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant.id,
    ))
    connection.scopes = "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment"
    previous = await load_active_configuration(db_session, tenant.id, lock=True)
    previous.is_active = False
    previous.deactivated_at = datetime.now(timezone.utc)
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=previous.version + 1,
        selected_provider="quickbooks_payments",
        readiness_state="ready",
        is_active=True,
        actor_user_id=owner.id,
        actor_name_snapshot="Garage Owner",
        qbo_realm_snapshot=connection.realm_id,
        writer_strategy="dieselbridge",
        idempotency_key="qbp-partial-provider-config",
        request_hash="q" * 64,
        stripe_clearing_account="Stripe Clearing",
        qbp_clearing_account="QBP Clearing",
        check_deposit_account="Undeposited Funds",
        zelle_ach_account="Zelle Clearing",
        card_fee_income_account="Card Fee Income",
        processor_fee_expense_account="Processor Fees",
        sales_tax_liability_account="Sales Tax Payable",
        checking_account="Checking",
    )
    db_session.add(config)
    await db_session.flush()

    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    creation = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("25.00"),
        rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key="qbp-partial-attempt-create",
        source="staff",
        subject_type="staff",
        subject_id=owner.id,
        sender_evidence={},
    )
    observed = {}

    async def refresh_noop(_db, _connection):
        return _connection

    async def captured_charge(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            id="qbp-charge-partial-25",
            amount=kwargs["amount"],
            status="CAPTURED",
            raw={"context": {"clientTransID": "intuit-client-partial-25"}},
        )

    monkeypatch.setattr(settlement_endpoints, "_refresh_connection_if_needed", refresh_noop)
    monkeypatch.setattr(settlement_endpoints, "create_quickbooks_charge", captured_charge)
    original_attempt_version = creation.attempt.version

    confirmed = await settlement_endpoints.charge_quickbooks_settlement_attempt(
        db_session,
        attempt=creation.attempt,
        invoice=invoice,
        tenant=tenant,
        actor=owner,
        payment_token="opaque-browser-token",
        expected_attempt_version=original_attempt_version,
        idempotency_key="qbp-partial-attempt-charge",
    )

    assert confirmed.attempt.state == "confirmed"
    assert confirmed.attempt.provider == "quickbooks_payments"
    assert confirmed.attempt.provider_charge_id == "qbp-charge-partial-25"
    assert confirmed.attempt.provider_reference == "intuit-client-partial-25"
    assert money(confirmed.settlement.confirmed_principal) == Decimal("25.00")
    assert observed["token"] == "opaque-browser-token"
    assert observed["request_id"] == f"db048-attempt-{creation.attempt.id}"
    assert observed["description"] == (
        f"{tenant.name} invoice {invoice.invoice_number}"
    )
    payment = await db_session.scalar(select(Payment).where(
        Payment.invoice_payment_attempt_id == confirmed.attempt.id,
    ))
    assert payment.method == PaymentMethod.QUICKBOOKS
    assert payment.reference_number == "intuit-client-partial-25"
    assert "opaque-browser-token" not in str(confirmed.attempt.manual_evidence)
    ledger_payloads = (await db_session.execute(select(
        InvoicePaymentLedgerEvent.money_snapshot,
        InvoicePaymentLedgerEvent.evidence_snapshot,
    ).where(
        InvoicePaymentLedgerEvent.attempt_id == confirmed.attempt.id,
    ))).all()
    assert "opaque-browser-token" not in str(ledger_payloads)

    replayed = await settlement_endpoints.charge_quickbooks_settlement_attempt(
        db_session,
        attempt=confirmed.attempt,
        invoice=invoice,
        tenant=tenant,
        actor=owner,
        payment_token="different-retry-token",
        expected_attempt_version=original_attempt_version,
        idempotency_key="qbp-partial-attempt-charge-retry",
    )
    assert replayed.replayed is True
    assert observed["token"] == "opaque-browser-token"


@pytest.mark.asyncio
async def test_quickbooks_payments_unknown_outcome_stays_pending_and_reconciles_safely(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    connection = await db_session.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant.id,
    ))
    connection.scopes = "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment"
    previous = await load_active_configuration(db_session, tenant.id, lock=True)
    previous.is_active = False
    previous.deactivated_at = datetime.now(timezone.utc)
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=previous.version + 1,
        selected_provider="quickbooks_payments",
        readiness_state="ready",
        is_active=True,
        actor_user_id=owner.id,
        actor_name_snapshot="Garage Owner",
        qbo_realm_snapshot=connection.realm_id,
        writer_strategy="dieselbridge",
        idempotency_key="qbp-unknown-provider-config",
        request_hash="u" * 64,
        stripe_clearing_account="Stripe Clearing",
        qbp_clearing_account="QBP Clearing",
        check_deposit_account="Undeposited Funds",
        zelle_ach_account="Zelle Clearing",
        card_fee_income_account="Card Fee Income",
        processor_fee_expense_account="Processor Fees",
        sales_tax_liability_account="Sales Tax Payable",
        checking_account="Checking",
    )
    db_session.add(config)
    await db_session.flush()
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    creation = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("25.00"),
        rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key="qbp-unknown-attempt-create",
        source="staff",
        subject_type="staff",
        subject_id=owner.id,
        sender_evidence={},
    )

    async def refresh_noop(_db, _connection):
        return _connection

    async def unknown_charge(**_kwargs):
        raise QuickBooksPaymentError("provider timed out", outcome_unknown=True)

    monkeypatch.setattr(settlement_endpoints, "_refresh_connection_if_needed", refresh_noop)
    monkeypatch.setattr(settlement_endpoints, "create_quickbooks_charge", unknown_charge)

    with pytest.raises(SettlementDomainError) as error:
        await settlement_endpoints.charge_quickbooks_settlement_attempt(
            db_session,
            attempt=creation.attempt,
            invoice=invoice,
            tenant=tenant,
            actor=owner,
            payment_token="opaque-browser-token",
            expected_attempt_version=creation.attempt.version,
            idempotency_key="qbp-unknown-attempt-charge",
        )
    assert error.value.code == "card_provider_outcome_unknown"
    assert error.value.retryable is True
    await db_session.refresh(creation.attempt)
    assert creation.attempt.state == "pending"
    assert creation.attempt.failure_code == "quickbooks_payment_outcome_unknown"
    assert creation.attempt.received_amount is None
    events = (await db_session.execute(select(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.attempt_id == creation.attempt.id,
        InvoicePaymentLedgerEvent.event_type == "provider_outcome_unknown",
    ))).scalars().all()
    assert len(events) == 1

    async def pending_retry(**kwargs):
        assert kwargs["request_id"] == f"db048-attempt-{creation.attempt.id}"
        return SimpleNamespace(
            id="qbp-charge-recovered-after-timeout",
            amount=kwargs["amount"],
            status="PENDING",
        )

    monkeypatch.setattr(settlement_endpoints, "create_quickbooks_charge", pending_retry)
    assert await settlement_endpoints.charge_quickbooks_settlement_attempt(
        db_session,
        attempt=creation.attempt,
        invoice=invoice,
        tenant=tenant,
        actor=owner,
        payment_token="fresh-opaque-browser-token",
        expected_attempt_version=creation.attempt.version,
        idempotency_key="qbp-unknown-attempt-charge-retry",
    ) is None
    creation.attempt.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    async def captured_reconciliation(**kwargs):
        assert kwargs["charge_id"] == "qbp-charge-recovered-after-timeout"
        return SimpleNamespace(
            id=kwargs["charge_id"],
            amount=money(creation.attempt.provider_charge_amount),
            status="CAPTURED",
        )

    monkeypatch.setattr(reconciliation_service, "get_quickbooks_charge", captured_reconciliation)
    result = await reconcile_due_card_attempts(db_session, tenant_id=tenant.id)
    await db_session.flush()
    assert result == {"checked": 1, "confirmed": 1, "released": 0, "deferred": 0}
    assert creation.attempt.state == "confirmed"
    assert money(settlement.active_pending_principal) == Decimal("0.00")
    assert money(settlement.confirmed_principal) == Decimal("25.00")


@pytest.mark.asyncio
async def test_quickbooks_amount_mismatch_queues_and_completes_full_provider_refund(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    connection = await db_session.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant.id,
    ))
    connection.scopes = "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment"
    previous = await load_active_configuration(db_session, tenant.id, lock=True)
    previous.is_active = False
    previous.deactivated_at = datetime.now(timezone.utc)
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=previous.version + 1,
        selected_provider="quickbooks_payments",
        readiness_state="ready",
        is_active=True,
        actor_user_id=owner.id,
        actor_name_snapshot="Garage Owner",
        qbo_realm_snapshot=connection.realm_id,
        writer_strategy="dieselbridge",
        idempotency_key="qbp-mismatch-provider-config",
        request_hash="m" * 64,
        stripe_clearing_account="Stripe Clearing",
        qbp_clearing_account="QBP Clearing",
        check_deposit_account="Undeposited Funds",
        zelle_ach_account="Zelle Clearing",
        card_fee_income_account="Card Fee Income",
        processor_fee_expense_account="Processor Fees",
        sales_tax_liability_account="Sales Tax Payable",
        checking_account="Checking",
    )
    db_session.add(config)
    await db_session.flush()
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    creation = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("25.00"),
        rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key="qbp-mismatch-attempt-create",
        source="staff",
        subject_type="staff",
        subject_id=owner.id,
        sender_evidence={},
    )

    async def refresh_noop(_db, _connection):
        return _connection

    async def mismatched_charge(**_kwargs):
        return SimpleNamespace(id="qbp-charge-wrong-amount", amount=Decimal("26.00"), status="CAPTURED")

    monkeypatch.setattr(settlement_endpoints, "_refresh_connection_if_needed", refresh_noop)
    monkeypatch.setattr(settlement_endpoints, "create_quickbooks_charge", mismatched_charge)
    with pytest.raises(SettlementDomainError) as error:
        await settlement_endpoints.charge_quickbooks_settlement_attempt(
            db_session,
            attempt=creation.attempt,
            invoice=invoice,
            tenant=tenant,
            actor=owner,
            payment_token="opaque-browser-token",
            expected_attempt_version=creation.attempt.version,
            idempotency_key="qbp-mismatch-attempt-charge",
        )
    assert error.value.code == "provider_payment_mismatch"
    refund = await db_session.scalar(select(PaymentRefund).where(
        PaymentRefund.source_attempt_id == creation.attempt.id,
        PaymentRefund.overpayment_id.is_(None),
    ))
    outbox = await db_session.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.aggregate_id == refund.id,
        ProviderOutboxEvent.event_type == "payment_refund.provider_submit",
    ))
    assert money(refund.amount) == Decimal("26.00")
    assert refund.state == "pending"
    assert money(settlement.active_pending_principal) == Decimal("25.00")
    assert money(settlement.confirmed_principal) == Decimal("0.00")

    async def completed_refund(**kwargs):
        assert kwargs["charge_id"] == "qbp-charge-wrong-amount"
        assert kwargs["amount"] == Decimal("26.00")
        return SimpleNamespace(id="qbp-refund-wrong-amount", amount=Decimal("26.00"), status="COMPLETED")

    monkeypatch.setattr(reconciliation_service, "refund_quickbooks_charge", completed_refund)
    provider_id = await _submit_stripe_refund(db_session, outbox)
    await db_session.flush()
    assert provider_id == "qbp-refund-wrong-amount"
    assert refund.state == "succeeded"
    assert creation.attempt.state == "failed"
    assert creation.attempt.failure_code == "provider_payment_mismatch_refunded"
    assert money(settlement.active_pending_principal) == Decimal("0.00")
    assert money(settlement.confirmed_principal) == Decimal("0.00")
    assert await db_session.scalar(select(func.count(Payment.id)).where(
        Payment.invoice_id == invoice.id,
    )) == 0


@pytest.mark.asyncio
async def test_unimplemented_intuit_native_writer_is_not_ready(db_session, monkeypatch):
    tenant, owner, _customer, _invoice = await _financial_context(db_session, monkeypatch)
    previous = await load_active_configuration(db_session, tenant.id, lock=True)
    previous.is_active = False
    previous.deactivated_at = datetime.now(timezone.utc)
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=previous.version + 1,
        selected_provider="stripe_connect",
        readiness_state="pending_readiness_check",
        is_active=True,
        actor_user_id=owner.id,
        actor_name_snapshot="Garage Owner",
        provider_account_snapshot=tenant.stripe_account_id,
        qbo_realm_snapshot=previous.qbo_realm_snapshot,
        writer_strategy="intuit_native",
        idempotency_key="unsupported-native-writer",
        request_hash="n" * 64,
        stripe_clearing_account="Stripe Clearing",
        qbp_clearing_account="QBP Clearing",
        check_deposit_account="Undeposited Funds",
        zelle_ach_account="Zelle Clearing",
        card_fee_income_account="Card Fee Income",
        processor_fee_expense_account="Processor Fees",
        sales_tax_liability_account="Sales Tax Payable",
        checking_account="Checking",
    )
    db_session.add(config)
    await db_session.flush()
    readiness = await provider_readiness(db_session, tenant, config)
    assert readiness.status == "not_ready"
    assert "accounting_writer_unsupported" in readiness.reasons


@pytest.mark.asyncio
async def test_legacy_quickbooks_charge_route_delegates_to_db048_attempt(
    db_session, monkeypatch,
):
    tenant, _owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    connection = await db_session.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant.id,
    ))
    connection.scopes = "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment"
    previous = await load_active_configuration(db_session, tenant.id, lock=True)
    previous.is_active = False
    previous.deactivated_at = datetime.now(timezone.utc)
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=previous.version + 1,
        selected_provider="quickbooks_payments",
        readiness_state="ready",
        is_active=True,
        actor_user_id=previous.actor_user_id,
        actor_name_snapshot="Garage Owner",
        qbo_realm_snapshot=connection.realm_id,
        writer_strategy="dieselbridge",
        idempotency_key="legacy-qbp-adapter-provider-config",
        request_hash="l" * 64,
        stripe_clearing_account="Stripe Clearing",
        qbp_clearing_account="QBP Clearing",
        check_deposit_account="Undeposited Funds",
        zelle_ach_account="Zelle Clearing",
        card_fee_income_account="Card Fee Income",
        processor_fee_expense_account="Processor Fees",
        sales_tax_liability_account="Sales Tax Payable",
        checking_account="Checking",
    )
    customer_user = User(
        email=f"qbp-customer-{uuid4().hex}@example.test",
        hashed_password="hash",
        first_name="QuickBooks",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        tenant_id=tenant.id,
        customer_id=customer.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([config, customer_user])
    await db_session.flush()
    await get_or_create_settlement(
        db_session,
        invoice=invoice,
        customer_id=customer.id,
        tenant=tenant,
    )
    observed = {}

    async def db048_charge(_db, **kwargs):
        observed.update(kwargs)
        kwargs["attempt"].provider_charge_id = "qbp-adapter-charge"
        return SimpleNamespace(attempt=kwargs["attempt"])

    async def forbidden_legacy_charge(**_kwargs):
        pytest.fail("legacy QuickBooks charge must not bypass DB-048")

    monkeypatch.setattr(settlement_endpoints, "charge_quickbooks_settlement_attempt", db048_charge)
    monkeypatch.setattr(quickbooks_endpoints, "create_charge", forbidden_legacy_charge)
    response = await quickbooks_endpoints.charge_quickbooks_invoice(
        body=QuickBooksChargeRequest(
            invoice_id=invoice.id,
            token="opaque-browser-token",
            idempotency_key="legacy-qbp-adapter-attempt",
        ),
        db=db_session,
        current_user=customer_user,
    )
    attempt = await db_session.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.invoice_id == invoice.id,
        InvoicePaymentAttempt.idempotency_key == "legacy-qbp-adapter-attempt",
    ))
    assert attempt is not None
    assert attempt.provider == "quickbooks_payments"
    assert attempt.principal_amount == Decimal("100.00")
    assert observed["attempt"].id == attempt.id
    assert observed["payment_token"] == "opaque-browser-token"
    assert response.charge_id == "qbp-adapter-charge"


@pytest.mark.asyncio
async def test_invoice_rejects_new_attempt_after_qbo_realm_change(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    first = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("10"), rail="check",
        expected_settlement_version=settlement.version,
        idempotency_key="realm-one-attempt", source="staff",
        subject_type="staff", subject_id=owner.id,
        sender_evidence={"reference_number": "REALM-ONE"},
    )
    await fail_attempt(
        db_session, attempt_id=first.attempt.id, tenant_id=tenant.id,
        actor=owner, expected_attempt_version=first.attempt.version,
        failure_code="cancelled_for_realm_test",
        idempotency_key="realm-one-release",
    )
    config_one = await load_active_configuration(db_session, tenant.id, lock=True)
    config_one.is_active = False
    config_one.deactivated_at = datetime.now(timezone.utc)
    connection = await db_session.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant.id,
    ))
    connection.realm_id = "realm-two"
    config_two = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id, version=2, selected_provider="stripe_connect",
        readiness_state="ready", is_active=True, actor_user_id=owner.id,
        actor_name_snapshot="Garage Owner",
        provider_account_snapshot=tenant.stripe_account_id,
        qbo_realm_snapshot="realm-two", writer_strategy="dieselbridge",
        idempotency_key="realm-two-config", request_hash="2" * 64,
        stripe_clearing_account="Stripe Clearing",
        qbp_clearing_account="QBP Clearing",
        check_deposit_account="Undeposited Funds",
        zelle_ach_account="Zelle Clearing",
        card_fee_income_account="Card Fee Income",
        processor_fee_expense_account="Processor Fees",
        sales_tax_liability_account="Sales Tax Payable",
        checking_account="Checking",
    )
    db_session.add(config_two)
    await db_session.flush()
    count_before = await db_session.scalar(select(func.count(InvoicePaymentAttempt.id)).where(
        InvoicePaymentAttempt.invoice_id == invoice.id,
    ))

    with pytest.raises(SettlementDomainError) as error:
        await create_attempt(
            db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
            actor=owner, amount=Decimal("10"), rail="check",
            expected_settlement_version=settlement.version,
            idempotency_key="realm-two-attempt", source="staff",
            subject_type="staff", subject_id=owner.id,
            sender_evidence={"reference_number": "REALM-TWO"},
        )
    assert error.value.code == "invoice_accounting_realm_mismatch"
    assert await db_session.scalar(select(func.count(InvoicePaymentAttempt.id)).where(
        InvoicePaymentAttempt.invoice_id == invoice.id,
    )) == count_before
    assert settlement.qbo_realm_snapshot != "realm-two"


@pytest.mark.asyncio
async def test_card_hold_is_bounded_and_provider_success_wins_at_expiry(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db_session, monkeypatch, fee=Decimal("0"))
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    creation = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("40"), rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key="card-expiry-success", source="customer_portal",
        subject_type="customer", subject_id=customer.id,
    )
    assert creation.attempt.expires_at is not None
    creation.attempt.provider_intent_id = "pi_expired_success"
    creation.attempt.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    stripe_metadata = {
        "tenant_id": str(tenant.id),
        "invoice_id": str(invoice.id),
        "customer_id": str(customer.id),
        "invoice_payment_attempt_id": str(creation.attempt.id),
        "provider_configuration_version": str(
            creation.attempt.provider_configuration_version
        ),
        "stripe_connected_account_id": creation.attempt.provider_account_id,
        "principal_amount": str(money(creation.attempt.principal_amount)),
        "card_fee_amount": str(money(creation.attempt.card_fee_amount)),
        "card_fee_tax_amount": str(money(creation.attempt.card_fee_tax_amount)),
    }
    result = await reconcile_due_card_attempts(
        db_session,
        retrieve_intent=lambda *_args, **_kwargs: {
            "id": "pi_expired_success", "status": "succeeded",
            "currency": "usd", "amount": 4000, "amount_received": 4000,
            "latest_charge": "ch_expired_success", "metadata": stripe_metadata,
        },
        cancel_intent=lambda *_args, **_kwargs: pytest.fail("successful intent must not be cancelled"),
    )
    await db_session.flush()
    assert result == {"checked": 1, "confirmed": 1, "released": 0, "deferred": 0}
    assert creation.attempt.state == "confirmed"
    assert money(creation.settlement.active_pending_principal) == Decimal("0.00")
    assert money(creation.settlement.confirmed_principal) == Decimal("40.00")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch",
    [
        "amount_one_cent",
        "amount_received_one_cent",
        "currency",
        "tenant_metadata",
        "account_metadata",
        "object_account",
        "missing_latest_charge",
    ],
)
async def test_expired_card_reconciliation_fails_closed_on_provider_envelope_mismatch(
    db_session, monkeypatch, mismatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    creation = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("40"), rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key=f"card-reconcile-mismatch-{mismatch}",
        source="customer_portal", subject_type="customer",
        subject_id=customer.id,
    )
    creation.attempt.provider_intent_id = f"pi_reconcile_{mismatch}"
    creation.attempt.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    metadata = {
        "tenant_id": str(tenant.id), "invoice_id": str(invoice.id),
        "customer_id": str(customer.id),
        "invoice_payment_attempt_id": str(creation.attempt.id),
        "provider_configuration_version": str(
            creation.attempt.provider_configuration_version
        ),
        "stripe_connected_account_id": creation.attempt.provider_account_id,
        "principal_amount": "40.00", "card_fee_amount": "0.00",
        "card_fee_tax_amount": "0.00",
    }
    intent = {
        "id": creation.attempt.provider_intent_id, "status": "succeeded",
        "currency": "usd", "amount": 4000, "amount_received": 4000,
        "latest_charge": f"ch_{mismatch}", "metadata": metadata,
    }
    if mismatch == "amount_one_cent":
        intent["amount"] = 4001
    elif mismatch == "amount_received_one_cent":
        intent["amount_received"] = 3999
    elif mismatch == "currency":
        intent["currency"] = "cad"
    elif mismatch == "tenant_metadata":
        metadata["tenant_id"] = str(uuid4())
    elif mismatch == "account_metadata":
        metadata["stripe_connected_account_id"] = "acct_wrong"
    elif mismatch == "object_account":
        intent["account"] = "acct_wrong"
    elif mismatch == "missing_latest_charge":
        intent["latest_charge"] = None

    before_version = settlement.version
    before_pending = money(settlement.active_pending_principal)
    result = await reconcile_due_card_attempts(
        db_session,
        retrieve_intent=lambda *_args, **_kwargs: intent,
        cancel_intent=lambda *_args, **_kwargs: pytest.fail(
            "mismatched provider envelope must not release the hold"
        ),
    )
    await db_session.flush()

    assert result == {"checked": 1, "confirmed": 0, "released": 0, "deferred": 1}
    assert creation.attempt.state == "pending"
    assert creation.attempt.failure_code is not None
    assert money(settlement.active_pending_principal) == before_pending
    assert money(settlement.confirmed_principal) == Decimal("0.00")
    # Operational failure evidence may advance the attempt but never the
    # settlement money/version or invoice lifecycle.
    assert settlement.version == before_version
    assert invoice.status == InvoiceStatus.SENT
    assert await db_session.scalar(select(func.count(Payment.id)).where(
        Payment.invoice_id == invoice.id,
    )) == 0
    assert await db_session.scalar(select(func.count(InvoicePaymentLedgerEvent.id)).where(
        InvoicePaymentLedgerEvent.attempt_id == creation.attempt.id,
        InvoicePaymentLedgerEvent.event_type == "provider_reconciliation_failed",
    )) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("invoice", "deleted_at", "now"),
        ("invoice", "voided_at", "now"),
        ("order", "status", RepairOrderStatus.CANCELLED),
    ],
)
async def test_expired_card_reconciliation_does_not_touch_inaccessible_lifecycle(
    db_session, monkeypatch, target, field, value,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    creation = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("20"), rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key=f"expired-lifecycle-{target}-{field}",
        source="customer_portal", subject_type="customer",
        subject_id=customer.id,
    )
    creation.attempt.provider_intent_id = f"pi_lifecycle_{target}_{field}"
    creation.attempt.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    subject = invoice if target == "invoice" else invoice.repair_order
    setattr(subject, field, datetime.now(timezone.utc) if value == "now" else value)
    await db_session.flush()
    attempt_version = creation.attempt.version
    settlement_version = settlement.version
    pending = money(settlement.active_pending_principal)

    result = await reconcile_due_card_attempts(
        db_session,
        retrieve_intent=lambda *_args, **_kwargs: pytest.fail(
            "provider must not be queried for inaccessible invoice lifecycle"
        ),
        cancel_intent=lambda *_args, **_kwargs: pytest.fail(
            "provider must not be changed for inaccessible invoice lifecycle"
        ),
    )

    assert result == {"checked": 0, "confirmed": 0, "released": 0, "deferred": 1}
    assert creation.attempt.state == "pending"
    assert creation.attempt.version == attempt_version
    assert settlement.version == settlement_version
    assert money(settlement.active_pending_principal) == pending
    assert money(settlement.confirmed_principal) == Decimal("0.00")
    assert await db_session.scalar(select(func.count(Payment.id)).where(
        Payment.invoice_id == invoice.id,
    )) == 0


@pytest.mark.asyncio
async def test_card_provider_create_failure_retains_failed_audit_and_releases_hold(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db_session, monkeypatch, fee=Decimal("0"))
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    creation = await create_attempt(
        db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("25"), rail="card",
        expected_settlement_version=settlement.version,
        idempotency_key="card-create-fails", source="customer_portal",
        subject_type="customer", subject_id=customer.id,
    )

    async def provider_failure(*_args, **_kwargs):
        raise stripe.error.StripeError("provider unavailable")

    monkeypatch.setattr(settlement_endpoints, "_create_stripe_intent", provider_failure)
    with pytest.raises(SettlementDomainError) as error:
        await settlement_endpoints._persist_and_bind_stripe_intent(
            db_session,
            attempt=creation.attempt,
            tenant=tenant,
            invoice=invoice,
            customer=customer,
            idempotency_key="card-create-fails",
            actor=owner,
        )
    assert error.value.code == "card_provider_error"
    retained = await db_session.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == creation.attempt.id,
    ))
    retained_settlement = await db_session.get(InvoiceSettlement, creation.settlement.id)
    assert retained.state == "failed"
    assert money(retained_settlement.active_pending_principal) == Decimal("0.00")
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.attempt_id == retained.id,
        InvoicePaymentLedgerEvent.event_type == "payment_failed",
    )) == 1


@pytest.mark.asyncio
async def test_disabled_settlement_read_is_non_mutating(db_session, monkeypatch):
    tenant, owner, _customer, invoice = await _financial_context(db_session, monkeypatch, fee=Decimal("0"))
    tenant.invoice_split_payments_enabled = False
    await db_session.flush()
    with pytest.raises(SettlementDomainError) as error:
        await read_invoice_settlement(invoice.id, db=db_session, current_user=owner)
    assert error.value.code == "split_payments_disabled"
    assert await db_session.scalar(select(func.count()).select_from(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id,
    )) == 0


@pytest.mark.asyncio
async def test_gate_off_empty_native_shadow_preserves_legacy_compatibility_path(
    db_session, monkeypatch,
):
    tenant, _owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    shadow = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    assert shadow.legacy_reconciliation_status == "native"
    assert shadow.last_event_sequence == 0
    tenant.invoice_split_payments_enabled = False
    await db_session.flush()
    assert await settlement_for_compatibility_route(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
    ) is None


@pytest.mark.asyncio
async def test_readiness_detects_raw_post_cutoff_invoice_but_accepts_native_shadow(
    db_session, monkeypatch,
):
    tenant, _owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    assert (await provider_readiness(db_session, tenant)).status == "ready"

    raw_invoice = await _add_eligible_invoice(
        db_session,
        tenant=tenant,
        customer=customer,
        reference_invoice=invoice,
        with_shadow_settlement=False,
    )
    stale = await provider_readiness(db_session, tenant)
    assert stale.status == "not_ready"
    assert "invoice_settlement_backfill_stale_invoice" in stale.reasons

    raw_invoice.repair_order.customer = customer
    await get_or_create_settlement(
        db_session,
        invoice=raw_invoice,
        customer_id=customer.id,
        tenant=tenant,
    )
    await db_session.commit()
    assert (await provider_readiness(db_session, tenant)).status == "ready"


@pytest.mark.asyncio
async def test_readiness_detects_unprojected_payment_and_incompatible_attempt_state(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    unprojected = Payment(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        payment_number=f"PAY-STALE-{uuid4().hex[:10]}",
        amount=Decimal("10"),
        method=PaymentMethod.CHECK,
        status=PaymentStatus.COMPLETED,
        reference_number="STALE-10",
        recorded_by_user_id=owner.id,
    )
    db_session.add(unprojected)
    await db_session.commit()
    stale = await provider_readiness(db_session, tenant)
    assert "invoice_settlement_backfill_stale_payment" in stale.reasons

    await db_session.delete(unprojected)
    await db_session.commit()
    pending = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("10"),
        rail="check",
        expected_settlement_version=settlement.version,
        idempotency_key="pending-linked-payment-readiness",
        source="staff",
        subject_type="staff",
        subject_id=owner.id,
        sender_evidence={"reference_number": "PENDING-10"},
    )
    projected_payment = Payment(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        invoice_payment_attempt_id=pending.attempt.id,
        payment_number=f"PAY-PENDING-{uuid4().hex[:10]}",
        amount=Decimal("10"),
        method=PaymentMethod.CHECK,
        status=PaymentStatus.COMPLETED,
        reference_number="PENDING-10",
        recorded_by_user_id=owner.id,
    )
    db_session.add(projected_payment)
    await db_session.flush()
    pending.attempt.payment_id = projected_payment.id
    await db_session.commit()
    mismatched = await provider_readiness(db_session, tenant)
    assert "invoice_settlement_backfill_stale_payment" in mismatched.reasons


@pytest.mark.asyncio
async def test_readiness_requires_exact_current_zelle_submission_marker(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    marker = datetime.now(timezone.utc)
    pending = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("25"),
        rail="zelle",
        expected_settlement_version=settlement.version,
        idempotency_key="current-zelle-readiness",
        source="compatibility_adapter",
        subject_type="customer",
        subject_id=customer.id,
        sender_evidence={"compatibility_submitted_at": marker.isoformat()},
    )
    invoice.zelle_pending_submitted_at = marker
    await db_session.commit()
    assert pending.attempt.state == "pending"
    assert (await provider_readiness(db_session, tenant)).status == "ready"

    invoice.zelle_pending_submitted_at = marker + timedelta(minutes=5)
    await db_session.commit()
    stale = await provider_readiness(db_session, tenant)
    assert stale.status == "not_ready"
    assert "invoice_settlement_backfill_stale_zelle" in stale.reasons


@pytest.mark.asyncio
async def test_gate_off_existing_settlement_remains_read_only_and_blocks_legacy_fallback(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    attempt = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("25.00"),
        rail="zelle",
        expected_settlement_version=settlement.version,
        idempotency_key="rollback-existing-attempt",
        source="customer_portal",
        subject_type="customer",
        subject_id=customer.id,
    )
    tenant.invoice_split_payments_enabled = False
    await db_session.flush()

    summary = await read_invoice_settlement(
        invoice.id, db=db_session, current_user=owner,
    )
    assert summary.invoice_id == invoice.id
    assert summary.feature_enabled is False
    assert summary.allowed_actions.create_attempt is False
    assert summary.allowed_actions.confirm_manual is False
    assert summary.allowed_actions.apply_customer_credit is False
    assert summary.active_pending_principal == Decimal("25.00")
    with pytest.raises(SettlementDomainError) as conflict:
        await settlement_for_compatibility_route(
            db_session,
            invoice=invoice,
            tenant=tenant,
            customer_id=customer.id,
        )
    assert conflict.value.code == "split_payments_disabled"
    assert conflict.value.status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(
        InvoicePaymentAttempt,
    ).where(InvoicePaymentAttempt.invoice_id == invoice.id)) == 1
    assert attempt.attempt.state == "pending"


@pytest.mark.asyncio
async def test_allocation_reference_is_full_for_staff_and_masked_for_customer_and_guest(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    creation = await create_attempt(
        db_session,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("10.00"),
        rail="check",
        expected_settlement_version=settlement.version,
        idempotency_key="private-reference-create",
        source="staff",
        subject_type="staff",
        subject_id=owner.id,
        sender_evidence={"reference_number": "BANK-TRACE-12345678"},
    )
    await confirm_attempt(
        db_session,
        attempt_id=creation.attempt.id,
        tenant=tenant,
        actor=owner,
        expected_attempt_version=creation.attempt.version,
        idempotency_key="private-reference-confirm",
        reference="BANK-TRACE-12345678",
    )
    staff = await allocation_page(
        db_session, invoice=invoice, cursor=None, limit=25, audience="staff",
    )
    customer_page = await allocation_page(
        db_session, invoice=invoice, cursor=None, limit=25, audience="customer",
    )
    guest = await allocation_page(
        db_session, invoice=invoice, cursor=None, limit=25, audience="guest",
    )
    assert staff.items[0].reference == "BANK-TRACE-12345678"
    assert staff.items[0].reference_number == "BANK-TRACE-12345678"
    assert customer_page.items[0].reference == "••••5678"
    assert customer_page.items[0].reference_number == "••••5678"
    assert guest.items[0].reference == "••••5678"
    assert "BANK-TRACE" not in guest.model_dump_json()


@pytest.mark.asyncio
async def test_manual_reference_duplicate_requires_review_across_customer_invoices(db_session, monkeypatch):
    tenant, owner, customer, first_invoice = await _financial_context(
        db_session, monkeypatch, principal=Decimal("50"), fee=Decimal("0"),
    )
    first_settlement = await get_or_create_settlement(
        db_session, invoice=first_invoice, customer_id=customer.id, tenant=tenant,
    )
    first = await create_attempt(
        db_session, invoice=first_invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("10"), rail="check",
        expected_settlement_version=first_settlement.version,
        idempotency_key="first-check", source="staff", subject_type="staff",
        subject_id=owner.id, sender_evidence={"reference_number": "  CHECK 0099 "},
    )
    await confirm_attempt(
        db_session, attempt_id=first.attempt.id, tenant=tenant, actor=owner,
        expected_attempt_version=first.attempt.version,
        idempotency_key="first-check-confirm", reference="CHECK 0099",
    )

    second_order = RepairOrder(
        tenant_id=tenant.id, customer_id=customer.id,
        vehicle_id=first_invoice.repair_order.vehicle_id,
        order_number=f"RO-{uuid4().hex[:10]}", status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0"), total_labor_cost=Decimal("25"),
        total_cost=Decimal("25"),
    )
    db_session.add(second_order)
    await db_session.flush()
    second_invoice = Invoice(
        tenant_id=tenant.id, repair_order_id=second_order.id,
        invoice_number=f"INV-{uuid4().hex[:10]}", status=InvoiceStatus.SENT,
        subtotal=Decimal("25"), shop_supplies_amount=Decimal("0"),
        service_fee_amount=Decimal("0"), tax_amount=Decimal("0"),
        discount_amount=Decimal("0"), total_amount=Decimal("25"),
    )
    db_session.add(second_invoice)
    await db_session.flush()
    second_invoice.repair_order = second_order
    second_order.customer = customer
    second_settlement = await get_or_create_settlement(
        db_session, invoice=second_invoice, customer_id=customer.id, tenant=tenant,
    )
    duplicate = await create_attempt(
        db_session, invoice=second_invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("10"), rail="check",
        expected_settlement_version=second_settlement.version,
        idempotency_key="duplicate-check", source="staff", subject_type="staff",
        subject_id=owner.id, sender_evidence={"reference_number": "check   0099"},
    )
    with pytest.raises(SettlementDomainError) as error:
        await confirm_attempt(
            db_session, attempt_id=duplicate.attempt.id, tenant=tenant, actor=owner,
            expected_attempt_version=duplicate.attempt.version,
            idempotency_key="duplicate-check-confirm", reference="check 0099",
        )
    assert error.value.code == "manual_reference_requires_review"
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_unpaid_vehicle_release_is_manager_only_reasoned_actual_and_idempotent(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, principal=Decimal("100"), fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    receptionist = User(
        email=f"reception-{uuid4().hex}@example.com", hashed_password="hash",
        first_name="Front", last_name="Desk", role=UserRole.RECEPTIONIST,
        tenant_id=tenant.id, is_active=True, is_verified=True,
    )
    db_session.add(receptionist)
    await db_session.flush()
    with pytest.raises(SettlementDomainError) as denied:
        await authorize_early_release(
            db_session, invoice=invoice, tenant=tenant, actor=receptionist,
            reason="Customer requested release", expected_settlement_version=settlement.version,
            idempotency_key="release-denied",
        )
    assert denied.value.code == "invoice_not_found"
    assert denied.value.status_code == 404
    with pytest.raises(SettlementDomainError) as missing_reason:
        await authorize_early_release(
            db_session, invoice=invoice, tenant=tenant, actor=owner,
            reason="", expected_settlement_version=settlement.version,
            idempotency_key="release-no-reason",
        )
    assert missing_reason.value.code == "release_override_reason_required"

    released = await authorize_early_release(
        db_session, invoice=invoice, tenant=tenant, actor=owner,
        reason="Fleet manager accepted open balance", expected_settlement_version=settlement.version,
        idempotency_key="release-approved",
    )
    replay = await authorize_early_release(
        db_session, invoice=invoice, tenant=tenant, actor=owner,
        reason="Fleet manager accepted open balance", expected_settlement_version=1,
        idempotency_key="release-approved",
    )
    await db_session.flush()
    order = await db_session.get(RepairOrder, invoice.repair_order_id)
    assert order.vehicle_released_at is not None
    assert order.vehicle_released_by_user_id == owner.id
    assert order.vehicle_release_reason == "Fleet manager accepted open balance"
    assert replay.id == released.id
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.invoice_id == invoice.id,
        InvoicePaymentLedgerEvent.event_type == "vehicle_release_override",
    )) == 1


@pytest.mark.asyncio
async def test_receptionist_cannot_apply_customer_credit(db_session, monkeypatch):
    tenant, _owner, _customer, invoice = await _financial_context(
        db_session, monkeypatch, principal=Decimal("100"), fee=Decimal("0"),
    )
    receptionist = User(
        email=f"reception-credit-{uuid4().hex}@example.com", hashed_password="hash",
        first_name="Front", last_name="Desk", role=UserRole.RECEPTIONIST,
        tenant_id=tenant.id, is_active=True, is_verified=True,
    )
    db_session.add(receptionist)
    await db_session.flush()
    with pytest.raises(SettlementDomainError) as denied:
        await settlement_endpoints.apply_store_credit(
            credit_id=uuid4(),
            body=CreditApplicationCreate(
                invoice_id=invoice.id,
                amount=Decimal("1.00"),
                expected_settlement_version=1,
            ),
            idempotency_header="reception-credit-denied",
            db=db_session,
            current_user=receptionist,
        )
    assert denied.value.code == "invoice_not_found"
    assert denied.value.status_code == 404

    with pytest.raises(SettlementDomainError) as hidden:
        await settlement_endpoints.read_eligible_customer_credits(
            invoice_id=invoice.id,
            db=db_session,
            current_user=receptionist,
        )
    assert hidden.value.code == "invoice_not_found"
    assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_credit_application_is_capped_by_selected_origin_not_customer_total(
    db_session, monkeypatch,
):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, principal=Decimal("100"), fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(
        db_session, invoice=invoice, customer_id=customer.id, tenant=tenant,
    )
    selected_origin = CustomerCreditEntry(
        tenant_id=tenant.id,
        customer_id=customer.id,
        entry_type="issued",
        amount=Decimal("10.00"),
        actor_user_id=owner.id,
        actor_name_snapshot="Customer",
        idempotency_key="credit-origin-ten",
        request_hash="a" * 64,
    )
    other_origin = CustomerCreditEntry(
        tenant_id=tenant.id,
        customer_id=customer.id,
        entry_type="issued",
        amount=Decimal("100.00"),
        actor_user_id=owner.id,
        actor_name_snapshot="Customer",
        idempotency_key="credit-origin-hundred",
        request_hash="b" * 64,
    )
    db_session.add_all([selected_origin, other_origin])
    await db_session.flush()

    with pytest.raises(SettlementDomainError) as error:
        await apply_customer_credit(
            db_session,
            credit_id=selected_origin.id,
            invoice=invoice,
            tenant=tenant,
            customer_id=customer.id,
            amount=Decimal("50.00"),
            expected_settlement_version=settlement.version,
            actor=owner,
            idempotency_key="credit-origin-overdraw",
        )
    assert error.value.code == "insufficient_credit"
    assert await available_credit(db_session, tenant.id, customer.id) == Decimal("110.00")


@pytest.mark.asyncio
async def test_provider_reversal_reopens_invoices_funded_by_applied_store_credit(
    db_session, monkeypatch,
):
    tenant, owner, customer, source_invoice = await _financial_context(
        db_session, monkeypatch, principal=Decimal("100"), fee=Decimal("0"),
    )
    source_settlement = await get_or_create_settlement(
        db_session,
        invoice=source_invoice,
        customer_id=customer.id,
        tenant=tenant,
    )
    creation = await create_attempt(
        db_session,
        invoice=source_invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("100.00"),
        rail="card",
        expected_settlement_version=source_settlement.version,
        idempotency_key="credit-source-create",
        source="customer_portal",
        subject_type="customer",
        subject_id=customer.id,
    )
    creation.attempt.provider_intent_id = "pi_credit_source"
    creation.attempt.provider_charge_amount = Decimal("110.00")
    confirmed = await confirm_attempt(
        db_session,
        attempt_id=creation.attempt.id,
        tenant=tenant,
        actor=None,
        expected_attempt_version=creation.attempt.version,
        idempotency_key="credit-source-confirm",
        received_principal=Decimal("110.00"),
        reference="pi_credit_source",
        provider_charge_id="ch_credit_source",
        provider_event_id="evt_credit_source",
    )
    origin = await record_credit_consent(
        db_session,
        overpayment_id=confirmed.overpayment.id,
        tenant_id=tenant.id,
        actor=owner,
        subject_customer_id=customer.id,
        channel="in_person",
        note="Keep the excess for my next repair",
        idempotency_key="credit-source-consent",
    )

    target_order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=source_invoice.repair_order.vehicle_id,
        order_number=f"RO-{uuid4().hex[:10]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0"),
        total_labor_cost=Decimal("6"),
        total_cost=Decimal("6"),
    )
    db_session.add(target_order)
    await db_session.flush()
    target_invoice = Invoice(
        tenant_id=tenant.id,
        repair_order_id=target_order.id,
        invoice_number=f"INV-{uuid4().hex[:10]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("6"),
        shop_supplies_amount=Decimal("0"),
        service_fee_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        discount_amount=Decimal("0"),
        total_amount=Decimal("6"),
    )
    db_session.add(target_invoice)
    await db_session.flush()
    target_invoice.repair_order = target_order
    target_order.customer = customer
    target_settlement = await get_or_create_settlement(
        db_session,
        invoice=target_invoice,
        customer_id=customer.id,
        tenant=tenant,
    )
    _application, target_settlement = await apply_customer_credit(
        db_session,
        credit_id=origin.id,
        invoice=target_invoice,
        tenant=tenant,
        customer_id=customer.id,
        amount=Decimal("6.00"),
        expected_settlement_version=target_settlement.version,
        actor=owner,
        idempotency_key="credit-target-application",
    )
    assert target_invoice.status == InvoiceStatus.PAID
    assert target_settlement.confirmed_principal == Decimal("6.00")
    assert await available_credit(db_session, tenant.id, customer.id) == Decimal("4.00")

    reversed_attempt = await reverse_confirmed_attempt(
        db_session,
        tenant_id=tenant.id,
        provider_account_id=tenant.stripe_account_id,
        provider_charge_id="ch_credit_source",
        provider_event_id="evt_credit_source_dispute",
        reason="charge.dispute.created",
    )
    await db_session.flush()

    assert reversed_attempt.state == "reversed"
    assert confirmed.overpayment.state == "reversed"
    assert source_invoice.status == InvoiceStatus.SENT
    assert confirmed.settlement.confirmed_principal == Decimal("0.00")
    assert target_invoice.status == InvoiceStatus.SENT
    assert target_order.status == RepairOrderStatus.INVOICED
    assert target_settlement.confirmed_principal == Decimal("0.00")
    assert target_settlement.accounting_sync_status == "accounting_sync_pending"
    assert await available_credit(db_session, tenant.id, customer.id) == Decimal("0.00")
    assert await db_session.scalar(select(func.count()).select_from(
        InvoicePaymentLedgerEvent,
    ).where(
        InvoicePaymentLedgerEvent.invoice_id == target_invoice.id,
        InvoicePaymentLedgerEvent.event_type == "credit_reversed",
    )) == 1
    assert await db_session.scalar(select(func.count()).select_from(
        CustomerCreditEntry,
    ).where(
        CustomerCreditEntry.source_entry_id == origin.id,
        CustomerCreditEntry.entry_type == "reversed",
        CustomerCreditEntry.amount == Decimal("4.00"),
    )) == 1


@pytest.mark.asyncio
async def test_dispute_win_reapplies_exact_credit_target_and_refunds_replacement_excess(
    db_session,
    monkeypatch,
):
    tenant, owner, customer, source_invoice = await _financial_context(
        db_session, monkeypatch, principal=Decimal("100"), fee=Decimal("0"),
    )
    source_settlement = await get_or_create_settlement(
        db_session,
        invoice=source_invoice,
        customer_id=customer.id,
        tenant=tenant,
    )
    creation = await create_attempt(
        db_session,
        invoice=source_invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("100.00"),
        rail="card",
        expected_settlement_version=source_settlement.version,
        idempotency_key="dispute-credit-source-create",
        source="customer_portal",
        subject_type="customer",
        subject_id=customer.id,
    )
    creation.attempt.provider_intent_id = "pi_dispute_credit"
    creation.attempt.provider_charge_amount = Decimal("110.00")
    confirmed = await confirm_attempt(
        db_session,
        attempt_id=creation.attempt.id,
        tenant=tenant,
        actor=None,
        expected_attempt_version=creation.attempt.version,
        idempotency_key="dispute-credit-source-confirm",
        received_principal=Decimal("110.00"),
        reference="pi_dispute_credit",
        provider_charge_id="ch_dispute_credit",
        provider_event_id="evt_dispute_credit_paid",
    )
    origin = await record_credit_consent(
        db_session,
        overpayment_id=confirmed.overpayment.id,
        tenant_id=tenant.id,
        actor=owner,
        subject_customer_id=customer.id,
        channel="in_person",
        note="Use this receipt on the next invoice",
        idempotency_key="dispute-credit-consent",
    )
    target_order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=source_invoice.repair_order.vehicle_id,
        order_number=f"RO-{uuid4().hex[:10]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0"),
        total_labor_cost=Decimal("6"),
        total_cost=Decimal("6"),
    )
    db_session.add(target_order)
    await db_session.flush()
    target_invoice = Invoice(
        tenant_id=tenant.id,
        repair_order_id=target_order.id,
        invoice_number=f"INV-{uuid4().hex[:10]}",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("6"),
        shop_supplies_amount=Decimal("0"),
        service_fee_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        discount_amount=Decimal("0"),
        total_amount=Decimal("6"),
    )
    db_session.add(target_invoice)
    await db_session.flush()
    target_invoice.repair_order = target_order
    target_order.customer = customer
    target_settlement = await get_or_create_settlement(
        db_session,
        invoice=target_invoice,
        customer_id=customer.id,
        tenant=tenant,
    )
    application, target_settlement = await apply_customer_credit(
        db_session,
        credit_id=origin.id,
        invoice=target_invoice,
        tenant=tenant,
        customer_id=customer.id,
        amount=Decimal("6.00"),
        expected_settlement_version=target_settlement.version,
        actor=owner,
        idempotency_key="dispute-credit-target-application",
    )
    application_link = await db_session.scalar(select(PaymentAccountingLink).where(
        PaymentAccountingLink.financial_object_type
        == "customer_credit_application",
        PaymentAccountingLink.financial_object_id == application.id,
    ))
    application_link.sync_state = "synced"

    dispute = await record_stripe_dispute(
        db_session,
        provider_account_id=tenant.stripe_account_id,
        provider_charge_id="ch_dispute_credit",
        provider_dispute_id="dp_dispute_credit",
        provider_event_id="evt_dispute_credit_open",
        amount=Decimal("110.00"),
        currency="usd",
        reason="fraudulent",
    )
    assert dispute.state == "open"
    assert target_settlement.confirmed_principal == Decimal("0.00")

    # A replacement tender fills half of the target while the dispute is open.
    replacement = await create_attempt(
        db_session,
        invoice=target_invoice,
        tenant=tenant,
        customer_id=customer.id,
        actor=owner,
        amount=Decimal("3.00"),
        rail="check",
        expected_settlement_version=target_settlement.version,
        idempotency_key="dispute-target-replacement-create",
        source="staff",
        subject_type="staff",
        subject_id=owner.id,
        sender_evidence={"reference_number": "CHECK-DISPUTE-3"},
    )
    await confirm_attempt(
        db_session,
        attempt_id=replacement.attempt.id,
        tenant=tenant,
        actor=owner,
        expected_attempt_version=replacement.attempt.version,
        idempotency_key="dispute-target-replacement-confirm",
        reference="CHECK-DISPUTE-3",
    )
    closed = await close_stripe_dispute(
        db_session,
        provider_account_id=tenant.stripe_account_id,
        provider_charge_id="ch_dispute_credit",
        provider_dispute_id="dp_dispute_credit",
        provider_event_id="evt_dispute_credit_won",
        amount=Decimal("110.00"),
        currency="usd",
        outcome="won",
    )
    await db_session.flush()

    assert closed.state == "won"
    assert confirmed.settlement.confirmed_principal == Decimal("100.00")
    assert target_settlement.confirmed_principal == Decimal("6.00")
    assert target_invoice.status == InvoiceStatus.PAID
    credit_reversal = await db_session.scalar(select(CustomerCreditEntry).where(
        CustomerCreditEntry.entry_type == "reversed",
        CustomerCreditEntry.source_entry_id == application.id,
    ))
    recovered_application = await db_session.scalar(select(CustomerCreditEntry).where(
        CustomerCreditEntry.entry_type == "applied",
        CustomerCreditEntry.source_entry_id == credit_reversal.id,
    ))
    assert recovered_application.target_invoice_id == target_invoice.id
    assert money(recovered_application.amount) == Decimal("3.00")
    assert money(confirmed.settlement.unapplied_credit) == Decimal("7.00")
    recovery_refund = await db_session.scalar(select(PaymentRefund).where(
        PaymentRefund.source_attempt_id == creation.attempt.id,
        PaymentRefund.state == "pending",
    ))
    assert money(recovery_refund.amount) == Decimal("7.00")
    assert await db_session.scalar(select(func.count()).select_from(
        PaymentAccountingLink,
    ).where(
        PaymentAccountingLink.financial_object_type
        == "payment_dispute_recovery",
        PaymentAccountingLink.financial_object_id == dispute.id,
    )) == 1
