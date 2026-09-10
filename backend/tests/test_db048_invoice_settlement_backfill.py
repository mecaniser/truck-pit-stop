from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    InvoicePaymentAttempt,
    InvoicePaymentLedgerEvent,
    InvoiceSettlement,
    TenantPaymentProviderConfiguration,
)
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.invoice_settlement_backfill import backfill_tenant_invoice_settlements
from app.services.invoice_settlement_service import (
    append_ledger_event,
    money,
    provider_readiness,
    settlement_state,
)


async def _backfill_fixture(
    db,
    *,
    zelle_age_hours: int = 1,
    include_zelle: bool = True,
    include_payment: bool = True,
    invoice_status: InvoiceStatus = InvoiceStatus.SENT,
    include_ineligible: bool = True,
    qbo_realm_snapshot: str | None = None,
):
    cutoff = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    tenant = Tenant(name="DB048 backfill", slug=f"db048-backfill-{uuid4().hex}")
    db.add(tenant)
    await db.flush()
    owner = User(
        tenant_id=tenant.id,
        email=f"backfill-owner-{uuid4().hex}@example.com",
        hashed_password="hash",
        first_name="Backfill",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Legacy",
        last_name="Customer",
        email=f"legacy-{uuid4().hex}@example.com",
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
        order_number=f"RO-BF-{uuid4().hex[:10]}",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0"),
        total_labor_cost=Decimal("100"),
        total_cost=Decimal("100"),
    )
    db.add(order)
    await db.flush()
    invoice = Invoice(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        invoice_number=f"INV-BF-{uuid4().hex[:10]}",
        status=invoice_status,
        subtotal=Decimal("100"),
        shop_supplies_amount=Decimal("0"),
        service_fee_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        discount_amount=Decimal("0"),
        total_amount=Decimal("100"),
        zelle_pending_submitted_at=(
            cutoff - timedelta(hours=zelle_age_hours) if include_zelle else None
        ),
        zelle_pending_sender_email="legacy@example.com" if include_zelle else None,
        created_at=cutoff - timedelta(days=2),
    )
    db.add(invoice)
    await db.flush()
    payment = None
    if include_payment:
        payment = Payment(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            payment_number=f"PAY-BF-{uuid4().hex[:10]}",
            amount=Decimal("40"),
            method=PaymentMethod.CHECK,
            status=PaymentStatus.COMPLETED,
            reference_number="CHECK-40",
            recorded_by_user_id=owner.id,
            created_at=cutoff - timedelta(hours=2),
        )
        db.add(payment)

    orphan_invoice = orphan_payment = None
    if include_ineligible:
        orphan_invoice = Invoice(
            tenant_id=tenant.id,
            repair_order_id=uuid4(),
            invoice_number=f"INV-BF-ORPHAN-{uuid4().hex[:8]}",
            status=InvoiceStatus.SENT,
            subtotal=Decimal("25"),
            shop_supplies_amount=Decimal("0"),
            service_fee_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            discount_amount=Decimal("0"),
            total_amount=Decimal("25"),
            created_at=cutoff - timedelta(days=2),
        )
        db.add(orphan_invoice)
        await db.flush()
        orphan_payment = Payment(
            tenant_id=tenant.id,
            invoice_id=orphan_invoice.id,
            payment_number=f"PAY-BF-ORPHAN-{uuid4().hex[:8]}",
            amount=Decimal("25"),
            method=PaymentMethod.CHECK,
            status=PaymentStatus.COMPLETED,
            reference_number="ORPHAN-CHECK",
            created_at=cutoff - timedelta(hours=2),
        )
        db.add(orphan_payment)

    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=1,
        selected_provider="stripe_connect",
        readiness_state="not_ready",
        is_active=True,
        actor_user_id=owner.id,
        actor_name_snapshot="Backfill Owner",
        provider_account_snapshot="acct_backfill",
        qbo_realm_snapshot=qbo_realm_snapshot,
        writer_strategy="dieselbridge",
        idempotency_key="backfill-provider-config",
        request_hash="0" * 64,
    )
    db.add(config)
    await db.commit()
    return tenant, invoice, payment, orphan_invoice, orphan_payment, cutoff


@pytest.mark.asyncio
async def test_backfill_overpayment_with_qbo_realm_is_rerunnable(db_session):
    tenant, _invoice, payment, *_rest, cutoff = await _backfill_fixture(
        db_session,
        include_zelle=False,
        include_ineligible=False,
        qbo_realm_snapshot="realm-backfill-overpayment",
    )
    payment.amount = Decimal("120.00")
    await db_session.commit()

    first = await backfill_tenant_invoice_settlements(
        db_session,
        tenant_id=tenant.id,
        cutoff_at=cutoff,
        batch_size=25,
    )
    await db_session.commit()
    rerun = await backfill_tenant_invoice_settlements(
        db_session,
        tenant_id=tenant.id,
        cutoff_at=cutoff,
        batch_size=25,
    )

    assert first.id == rerun.id
    assert rerun.state == "verified"
    attempt = await db_session.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.payment_id == payment.id,
    ))
    assert money(attempt.applied_principal_amount) == Decimal("100.00")
    assert money(attempt.unapplied_amount) == Decimal("20.00")
    readiness = await provider_readiness(db_session, tenant)
    assert "invoice_settlement_backfill_stale_payment" not in readiness.reasons


async def _add_native_payment_projection(
    db,
    *,
    tenant: Tenant,
    invoice: Invoice,
    applied: Decimal,
    received: Decimal | None = None,
    created_at: datetime,
) -> tuple[InvoicePaymentAttempt, Payment]:
    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == tenant.id,
        InvoiceSettlement.invoice_id == invoice.id,
    ))
    received = money(received if received is not None else applied)
    applied = money(applied)
    attempt = InvoicePaymentAttempt(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        settlement_id=settlement.id,
        customer_id=settlement.customer_id,
        source="staff",
        rail="check",
        provider="manual",
        state="confirmed",
        principal_amount=applied,
        provider_charge_amount=received,
        received_amount=received,
        applied_principal_amount=applied,
        unapplied_amount=money(received - applied),
        provider_configuration_version=1,
        actor_name_snapshot="Native DB048 staff",
        subject_type="staff",
        idempotency_key=f"native-payment-{uuid4().hex}",
        request_hash="1" * 64,
        confirmed_at=created_at,
        created_at=created_at,
    )
    db.add(attempt)
    await db.flush()
    payment = Payment(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        invoice_payment_attempt_id=attempt.id,
        payment_number=f"PAY-NATIVE-{uuid4().hex[:10]}",
        amount=applied,
        method=PaymentMethod.CHECK,
        status=PaymentStatus.COMPLETED,
        reference_number=f"NATIVE-{uuid4().hex[:8]}",
        created_at=created_at,
    )
    db.add(payment)
    await db.flush()
    attempt.payment_id = payment.id
    settlement.confirmed_principal = money(settlement.confirmed_principal) + applied
    settlement.unapplied_credit = money(settlement.unapplied_credit) + money(received - applied)
    settlement.version += 1
    settlement.state = settlement_state(settlement)
    if money(settlement.confirmed_principal) >= money(settlement.principal_total):
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = created_at
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="payment_confirmed",
        idempotency_key=f"native-payment-event-{attempt.id}",
        actor=None,
        principal_delta=applied,
        unapplied_delta=money(received - applied),
        evidence={"origin": "native_db048_test_projection"},
    )
    await db.commit()
    return attempt, payment


async def _add_native_pending_zelle_projection(
    db,
    *,
    tenant: Tenant,
    invoice: Invoice,
    amount: Decimal,
    submitted_at: datetime,
) -> InvoicePaymentAttempt:
    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == tenant.id,
        InvoiceSettlement.invoice_id == invoice.id,
    ))
    amount = money(amount)
    marker = submitted_at.astimezone(timezone.utc).isoformat()
    attempt = InvoicePaymentAttempt(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        settlement_id=settlement.id,
        customer_id=settlement.customer_id,
        source="compatibility_adapter",
        rail="zelle",
        provider="manual",
        state="pending",
        principal_amount=amount,
        provider_charge_amount=amount,
        provider_configuration_version=1,
        manual_evidence={"compatibility_submitted_at": marker},
        actor_name_snapshot="Native DB048 customer",
        subject_type="customer",
        idempotency_key=f"native-zelle-{uuid4().hex}",
        request_hash="2" * 64,
        expires_at=submitted_at + timedelta(hours=24),
        created_at=submitted_at,
    )
    db.add(attempt)
    await db.flush()
    invoice.zelle_pending_submitted_at = submitted_at
    invoice.zelle_pending_sender_email = "native-zelle@example.com"
    settlement.active_pending_principal = money(settlement.active_pending_principal) + amount
    settlement.version += 1
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="attempt_created",
        idempotency_key=f"native-zelle-event-{attempt.id}",
        actor=None,
        pending_delta=amount,
        evidence={"origin": "native_db048_test_projection"},
    )
    await db.commit()
    return attempt


@pytest.mark.asyncio
async def test_backfill_reconciles_eligible_sources_and_rechecks_verified_rerun(db_session):
    tenant, invoice, _payment, orphan_invoice, _orphan_payment, cutoff = await _backfill_fixture(
        db_session
    )
    first = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff
    )
    await db_session.commit()

    assert first.state == "verified"
    assert first.source_counts["invoices_total"] == 2
    assert first.source_counts["invoices_eligible"] == 1
    assert first.source_counts["invoices_ineligible"] == 1
    assert first.source_counts["ineligible_invoice_reasons"] == {"missing_repair_order": 1}
    assert first.source_counts["payments_total"] == 2
    assert first.source_counts["payments_eligible"] == 1
    assert first.source_counts["payments_ineligible"] == 1
    assert first.source_counts["pending_zelle_active"] == 1
    assert first.inserted_counts == {"settlements": 1, "attempts": 2, "events": 2}
    assert set(first.source_checksums) == {
        "invoices",
        "payments",
        "pending_zelle",
        "result_settlements",
        "result_attempts",
        "result_events",
    }

    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id
    ))
    assert money(settlement.confirmed_principal) == Decimal("40.00")
    assert money(settlement.active_pending_principal) == Decimal("60.00")
    assert await db_session.scalar(select(func.count()).select_from(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == orphan_invoice.id
    )) == 0

    original_checksums = dict(first.source_checksums)
    original_run_id = first.id
    rerun = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff
    )
    await db_session.commit()
    assert rerun.id == original_run_id
    assert rerun.state == "verified"
    assert rerun.source_checksums == original_checksums
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id == tenant.id,
        InvoicePaymentAttempt.source == "backfill",
    )) == 2
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.tenant_id == tenant.id,
        InvoicePaymentLedgerEvent.idempotency_key.like("backfill:%"),
    )) == 2


@pytest.mark.asyncio
async def test_verified_rerun_rejects_source_checksum_drift(db_session):
    tenant, _invoice, payment, _orphan_invoice, _orphan_payment, cutoff = await _backfill_fixture(
        db_session, include_ineligible=False
    )
    await backfill_tenant_invoice_settlements(db_session, tenant_id=tenant.id, cutoff_at=cutoff)
    await db_session.commit()

    payment.amount = Decimal("41")
    await db_session.commit()
    with pytest.raises(
        ValueError,
        match="Source checksum drift: payments|identity or projection mismatch",
    ):
        await backfill_tenant_invoice_settlements(
            db_session, tenant_id=tenant.id, cutoff_at=cutoff
        )


@pytest.mark.asyncio
async def test_verified_rerun_rejects_result_count_or_checksum_drift(db_session):
    tenant, _invoice, _payment, _orphan_invoice, _orphan_payment, cutoff = await _backfill_fixture(
        db_session, include_ineligible=False
    )
    await backfill_tenant_invoice_settlements(db_session, tenant_id=tenant.id, cutoff_at=cutoff)
    await db_session.commit()

    attempt = await db_session.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id == tenant.id,
        InvoicePaymentAttempt.source == "backfill",
        InvoicePaymentAttempt.rail == "check",
    ))
    attempt.failure_code = "tampered-result-envelope"
    await db_session.commit()
    with pytest.raises(ValueError, match="Baseline result count/checksum drift: attempts"):
        await backfill_tenant_invoice_settlements(
            db_session, tenant_id=tenant.id, cutoff_at=cutoff
        )


@pytest.mark.asyncio
async def test_verified_rerun_rejects_result_checksum_drift_without_count_change(db_session):
    tenant, invoice, _payment, _orphan_invoice, _orphan_payment, cutoff = await _backfill_fixture(
        db_session, include_ineligible=False
    )
    await backfill_tenant_invoice_settlements(db_session, tenant_id=tenant.id, cutoff_at=cutoff)
    await db_session.commit()

    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id
    ))
    settlement.principal_total = Decimal("101")
    await db_session.commit()
    with pytest.raises(ValueError, match="Baseline result count/checksum drift: settlements"):
        await backfill_tenant_invoice_settlements(
            db_session, tenant_id=tenant.id, cutoff_at=cutoff
        )


@pytest.mark.asyncio
async def test_backfill_records_expired_zelle_as_explicit_non_reserving_baseline(db_session):
    tenant, invoice, _payment, _orphan_invoice, _orphan_payment, cutoff = await _backfill_fixture(
        db_session,
        zelle_age_hours=25,
        include_ineligible=False,
    )
    run = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff
    )
    await db_session.commit()

    assert run.source_counts["pending_zelle_active"] == 0
    assert run.source_counts["pending_zelle_expired"] == 1
    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id
    ))
    zelle_attempt = await db_session.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.invoice_id == invoice.id,
        InvoicePaymentAttempt.rail == "zelle",
        InvoicePaymentAttempt.source == "backfill",
    ))
    zelle_event = await db_session.scalar(select(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.invoice_id == invoice.id,
        InvoicePaymentLedgerEvent.event_type == "legacy_zelle_expired_baseline",
    ))
    assert zelle_attempt.state == "expired"
    assert money(settlement.active_pending_principal) == Decimal("0.00")
    assert zelle_event is not None
    assert money(zelle_event.pending_delta) == Decimal("0.00")


@pytest.mark.asyncio
async def test_verified_same_cutoff_rerun_ignores_exact_native_confirmation_projection(
    db_session,
):
    tenant, invoice, _payment, *_rest, cutoff = await _backfill_fixture(
        db_session,
        include_zelle=False,
        include_ineligible=False,
    )
    original = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff,
    )
    await db_session.commit()
    await _add_native_payment_projection(
        db_session,
        tenant=tenant,
        invoice=invoice,
        applied=Decimal("60"),
        created_at=cutoff - timedelta(minutes=30),
    )
    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id,
    ))
    before = (
        money(settlement.confirmed_principal),
        money(settlement.unapplied_credit),
        settlement.version,
        settlement.last_event_sequence,
        invoice.status,
    )

    rerun = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff,
    )
    await db_session.commit()
    await db_session.refresh(settlement)
    await db_session.refresh(invoice)
    assert rerun.id == original.id
    assert rerun.state == "verified"
    assert (
        money(settlement.confirmed_principal),
        money(settlement.unapplied_credit),
        settlement.version,
        settlement.last_event_sequence,
        invoice.status,
    ) == before
    assert await db_session.scalar(select(func.count()).select_from(
        InvoicePaymentAttempt,
    ).where(
        InvoicePaymentAttempt.invoice_id == invoice.id,
        InvoicePaymentAttempt.source == "backfill",
    )) == 1


@pytest.mark.asyncio
async def test_later_cutoff_recognizes_live_overpayment_link_without_replay(db_session):
    tenant, invoice, _payment, *_rest, cutoff = await _backfill_fixture(
        db_session,
        include_zelle=False,
        include_ineligible=False,
    )
    await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff,
    )
    await db_session.commit()
    await _add_native_payment_projection(
        db_session,
        tenant=tenant,
        invoice=invoice,
        applied=Decimal("20"),
        received=Decimal("25"),
        created_at=cutoff + timedelta(hours=1),
    )
    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id,
    ))
    before = (
        money(settlement.confirmed_principal),
        money(settlement.unapplied_credit),
        settlement.version,
        settlement.last_event_sequence,
    )
    attempts_before = await db_session.scalar(select(func.count()).select_from(
        InvoicePaymentAttempt,
    ).where(InvoicePaymentAttempt.invoice_id == invoice.id))
    events_before = await db_session.scalar(select(func.count()).select_from(
        InvoicePaymentLedgerEvent,
    ).where(InvoicePaymentLedgerEvent.invoice_id == invoice.id))
    later_cutoff = cutoff + timedelta(hours=2)

    first = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=later_cutoff,
    )
    await db_session.commit()
    second = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=later_cutoff,
    )
    await db_session.commit()
    await db_session.refresh(settlement)
    assert first.id == second.id
    assert first.source_counts["payments_already_linked"] == 2
    assert (
        money(settlement.confirmed_principal),
        money(settlement.unapplied_credit),
        settlement.version,
        settlement.last_event_sequence,
    ) == before
    assert await db_session.scalar(select(func.count()).select_from(
        InvoicePaymentAttempt,
    ).where(InvoicePaymentAttempt.invoice_id == invoice.id)) == attempts_before
    assert await db_session.scalar(select(func.count()).select_from(
        InvoicePaymentLedgerEvent,
    ).where(InvoicePaymentLedgerEvent.invoice_id == invoice.id)) == events_before


@pytest.mark.asyncio
async def test_later_cutoff_rejects_one_sided_live_payment_link_before_mutation(db_session):
    tenant, invoice, _payment, *_rest, cutoff = await _backfill_fixture(
        db_session,
        include_zelle=False,
        include_ineligible=False,
    )
    await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff,
    )
    await db_session.commit()
    attempt, _native_payment = await _add_native_payment_projection(
        db_session,
        tenant=tenant,
        invoice=invoice,
        applied=Decimal("20"),
        created_at=cutoff + timedelta(hours=1),
    )
    attempt.payment_id = None
    await db_session.commit()
    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id,
    ))
    projection_before = (
        money(settlement.confirmed_principal),
        money(settlement.unapplied_credit),
        settlement.version,
        settlement.last_event_sequence,
    )
    counts_before = (
        await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt)),
        await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent)),
    )
    invoice_id = invoice.id
    with pytest.raises(ValueError, match="non-reciprocal"):
        await backfill_tenant_invoice_settlements(
            db_session,
            tenant_id=tenant.id,
            cutoff_at=cutoff + timedelta(hours=2),
        )
    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice_id,
    ))
    assert (
        money(settlement.confirmed_principal),
        money(settlement.unapplied_credit),
        settlement.version,
        settlement.last_event_sequence,
    ) == projection_before
    assert (
        await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt)),
        await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent)),
    ) == counts_before


@pytest.mark.asyncio
async def test_later_cutoff_preserves_exact_live_pending_zelle_and_rejects_newer_marker(
    db_session,
):
    tenant, invoice, _payment, *_rest, cutoff = await _backfill_fixture(
        db_session,
        include_zelle=False,
        include_ineligible=False,
    )
    await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff,
    )
    await db_session.commit()
    await _add_native_pending_zelle_projection(
        db_session,
        tenant=tenant,
        invoice=invoice,
        amount=Decimal("60"),
        submitted_at=cutoff + timedelta(hours=1),
    )
    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id,
    ))
    projection_before = (
        money(settlement.active_pending_principal),
        settlement.version,
        settlement.last_event_sequence,
    )
    counts_before = (
        await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt)),
        await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent)),
    )
    later_cutoff = cutoff + timedelta(hours=2)
    first = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=later_cutoff,
    )
    await db_session.commit()
    rerun = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=later_cutoff,
    )
    await db_session.commit()
    await db_session.refresh(settlement)
    assert first.id == rerun.id
    assert first.source_counts["pending_zelle_already_linked"] == 1
    assert (
        money(settlement.active_pending_principal),
        settlement.version,
        settlement.last_event_sequence,
    ) == projection_before
    assert (
        await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt)),
        await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent)),
    ) == counts_before

    invoice.zelle_pending_submitted_at = cutoff + timedelta(hours=1, minutes=5)
    await db_session.commit()
    with pytest.raises(ValueError, match="does not match"):
        await backfill_tenant_invoice_settlements(
            db_session,
            tenant_id=tenant.id,
            cutoff_at=cutoff + timedelta(hours=3),
        )


@pytest.mark.asyncio
async def test_paid_without_tender_reruns_and_later_unlinked_payment_fails_closed(db_session):
    tenant, invoice, _payment, *_rest, cutoff = await _backfill_fixture(
        db_session,
        include_zelle=False,
        include_payment=False,
        invoice_status=InvoiceStatus.PAID,
        include_ineligible=False,
    )
    first = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff,
    )
    await db_session.commit()
    rerun = await backfill_tenant_invoice_settlements(
        db_session, tenant_id=tenant.id, cutoff_at=cutoff,
    )
    await db_session.commit()
    assert first.id == rerun.id
    assert first.state == "verified"
    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id,
    ))
    projection_before = (
        money(settlement.confirmed_principal),
        settlement.version,
        settlement.last_event_sequence,
    )
    invoice_id = invoice.id
    db_session.add(Payment(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        payment_number=f"PAY-LATE-{uuid4().hex[:10]}",
        amount=Decimal("100"),
        method=PaymentMethod.CHECK,
        status=PaymentStatus.COMPLETED,
        reference_number="LATE-UNATTRIBUTED",
        created_at=cutoff + timedelta(hours=1),
    ))
    await db_session.commit()
    with pytest.raises(ValueError, match="unattributed paid baseline"):
        await backfill_tenant_invoice_settlements(
            db_session,
            tenant_id=tenant.id,
            cutoff_at=cutoff + timedelta(hours=2),
        )
    settlement = await db_session.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice_id,
    ))
    assert (
        money(settlement.confirmed_principal),
        settlement.version,
        settlement.last_event_sequence,
    ) == projection_before
