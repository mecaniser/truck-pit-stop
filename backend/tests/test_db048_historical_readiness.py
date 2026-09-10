from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.models.invoice_settlement import InvoicePaymentAttempt
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.services.invoice_settlement_service import (
    SettlementDomainError, create_attempt, get_or_create_settlement, provider_readiness,
)
from test_db048_invoice_settlements import _financial_context


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", [None, "native", "reciprocity", "customer", "amount", "deleted_invoice", "tenant"])
async def test_archived_order_historical_payment_readiness(db_session, monkeypatch, defect):
    tenant, owner, customer, invoice = await _financial_context(
        db_session, monkeypatch, principal=Decimal("230.48"), fee=Decimal("0"),
    )
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    attempt_id, payment_id = uuid4(), uuid4()
    attempt = InvoicePaymentAttempt(
        id=attempt_id, tenant_id=uuid4() if defect == "tenant" else tenant.id,
        invoice_id=invoice.id, settlement_id=settlement.id,
        customer_id=uuid4() if defect == "customer" else customer.id,
        payment_id=payment_id, source="staff" if defect == "native" else "backfill",
        rail="check", provider="manual", state="confirmed",
        principal_amount=Decimal("231.03"), provider_charge_amount=Decimal("231.03"),
        received_amount=Decimal("231.03"),
        applied_principal_amount=Decimal("231.03") if defect == "native" else Decimal("230.48"),
        unapplied_amount=Decimal("0") if defect == "native" else Decimal("0.55"),
        provider_configuration_version=1,
        actor_name_snapshot="Historical import", subject_type="system",
        idempotency_key=f"historical-{attempt_id}", request_hash="h" * 64,
    )
    payment = Payment(
        id=payment_id, tenant_id=tenant.id, invoice_id=invoice.id,
        invoice_payment_attempt_id=uuid4() if defect == "reciprocity" else attempt_id,
        payment_number=f"HIST-{payment_id}", amount=Decimal("232.03") if defect == "amount" else Decimal("231.03"),
        method=PaymentMethod.CHECK, status=PaymentStatus.COMPLETED,
    )
    invoice.repair_order.deleted_at = datetime.now(timezone.utc)
    if defect == "deleted_invoice":
        invoice.deleted_at = datetime.now(timezone.utc)
    db_session.add_all([attempt, payment])
    await db_session.commit()
    readiness = await provider_readiness(db_session, tenant)
    if defect is None:
        assert readiness.status == "ready", readiness.reasons
    else:
        assert "invoice_settlement_backfill_stale_payment" in readiness.reasons
    # Historical recognition must never reopen archived work for new checkout.
    with pytest.raises(SettlementDomainError) as exc:
        await create_attempt(
            db_session, invoice=invoice, tenant=tenant, customer_id=customer.id, actor=owner,
            amount=Decimal("1"), rail="check", expected_settlement_version=settlement.version,
            idempotency_key=f"new-{attempt_id}", source="staff", subject_type="staff", subject_id=owner.id,
        )
    assert exc.value.code == "invoice_not_found"
