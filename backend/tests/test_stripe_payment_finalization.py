from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import stripe_webhooks
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    InvoicePaymentAttempt,
    TenantPaymentProviderConfiguration,
)
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services import stripe_payment_finalization as svc


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FinalizeSession:
    def __init__(
        self,
        existing_payment: Payment | None = None,
        provider_config: TenantPaymentProviderConfiguration | None = None,
    ):
        self.existing_payment = existing_payment
        self.provider_config = provider_config
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshes: list[object] = []
        self.payment_queries = 0

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is Payment:
            self.payment_queries += 1
            return _ScalarResult(self.existing_payment)
        raise AssertionError(f"Unexpected query entity: {entity}")

    async def scalar(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is TenantPaymentProviderConfiguration:
            return self.provider_config
        if entity is InvoicePaymentAttempt:
            return None
        raise AssertionError(f"Unexpected scalar query entity: {entity}")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        self.refreshes.append(obj)


class _WebhookSession:
    def __init__(
        self,
        invoice: Invoice,
        tenant: Tenant,
        provider_config: TenantPaymentProviderConfiguration | None = None,
    ):
        self.invoice = invoice
        self.tenant = tenant
        self.provider_config = provider_config
        self.execute_calls = 0
        self.added: list[object] = []
        self.commits = 0

    async def execute(self, statement):
        self.execute_calls += 1
        entity = statement.column_descriptions[0].get("entity")
        if self.execute_calls == 1:
            assert entity is Invoice
            return _ScalarResult(self.invoice)
        if self.execute_calls == 2:
            assert entity is Tenant
            return _ScalarResult(self.tenant)
        raise AssertionError(f"Unexpected query call #{self.execute_calls} for entity {entity}")

    async def scalar(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is TenantPaymentProviderConfiguration:
            return self.provider_config
        raise AssertionError(f"Unexpected scalar query entity: {entity}")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


class _DB048StripeSession:
    def __init__(
        self,
        *,
        attempt: InvoicePaymentAttempt,
        provider_config: TenantPaymentProviderConfiguration | None,
        tenant: Tenant | None,
        customer: Customer | None,
    ):
        self.attempt = attempt
        self.provider_config = provider_config
        self.tenant = tenant
        self.customer = customer
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is InvoicePaymentAttempt:
            return self.attempt
        if entity is Tenant:
            return self.tenant
        if entity is Customer:
            return self.customer
        if entity is TenantPaymentProviderConfiguration:
            return self.provider_config
        raise AssertionError(f"Unexpected scalar query entity: {entity}")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _entities():
    tenant_id = uuid4()
    customer_id = uuid4()
    order_id = uuid4()
    invoice_id = uuid4()
    vehicle_id = uuid4()

    tenant = Tenant(
        id=tenant_id,
        name="Stripe Flow Garage",
        slug="stripe-flow-garage",
        is_active=True,
        stripe_account_id="acct_123",
        stripe_onboarding_complete=True,
        invoice_split_payments_enabled=False,
    )
    customer = Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Card",
        last_name="Customer",
        email="card@example.com",
    )
    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-STRIPE",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("100.00"),
        total_cost=Decimal("100.00"),
    )
    invoice = Invoice(
        id=invoice_id,
        tenant_id=tenant_id,
        repair_order_id=order_id,
        invoice_number="INV-STRIPE",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("100.00"),
        shop_supplies_amount=Decimal("0.00"),
        service_fee_amount=Decimal("3.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("103.00"),
    )
    invoice.repair_order = order
    order.customer = customer
    return tenant, customer, order, invoice


def _legacy_intent(
    invoice: Invoice,
    tenant: Tenant,
    *,
    payment_intent_id: str = "pi_webhook",
    metadata_tenant_id: str | None = None,
    metadata_account_id: str | None = "acct_123",
    include_tenant_id: bool = True,
) -> dict:
    metadata = {"invoice_id": str(invoice.id)}
    if include_tenant_id:
        metadata["tenant_id"] = metadata_tenant_id or str(tenant.id)
    if metadata_account_id is not None:
        metadata["stripe_connected_account_id"] = metadata_account_id
    return {"id": payment_intent_id, "metadata": metadata}


def _db048_attempt_and_config(
    tenant: Tenant,
    customer: Customer,
    invoice: Invoice,
) -> tuple[InvoicePaymentAttempt, TenantPaymentProviderConfiguration]:
    attempt = InvoicePaymentAttempt(
        id=uuid4(),
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        settlement_id=uuid4(),
        customer_id=customer.id,
        source="customer_portal",
        rail="card",
        provider="stripe_connect",
        state="pending",
        principal_amount=Decimal("100.00"),
        card_fee_amount=Decimal("2.50"),
        card_fee_tax_amount=Decimal("0.50"),
        applied_card_fee_amount=Decimal("0.00"),
        applied_card_fee_tax_amount=Decimal("0.00"),
        provider_charge_amount=Decimal("103.00"),
        applied_principal_amount=Decimal("0.00"),
        unapplied_amount=Decimal("0.00"),
        processor_fee_amount=Decimal("0.00"),
        currency="USD",
        provider_configuration_version=7,
        provider_account_id="acct_historical",
        provider_intent_id="pi_db048",
        actor_name_snapshot="Card Customer",
        subject_type="customer",
        subject_id=customer.id,
        idempotency_key="db048-card-attempt",
        request_hash="c" * 64,
        version=1,
    )
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=7,
        selected_provider="stripe_connect",
        readiness_state="ready",
        # The exact historical row remains authoritative after a switch.
        is_active=False,
        deactivated_at=datetime.now(timezone.utc),
        actor_user_id=uuid4(),
        actor_name_snapshot="Historical Config Owner",
        provider_account_snapshot="acct_historical",
        writer_strategy="dieselbridge",
        idempotency_key="provider-config-7",
        request_hash="d" * 64,
    )
    return attempt, config


def _db048_intent(attempt: InvoicePaymentAttempt, *, status: str = "succeeded") -> dict:
    intent = {
        "id": attempt.provider_intent_id,
        "status": status,
        "currency": "usd",
        "amount": 10300,
        "amount_received": 10300 if status == "succeeded" else 0,
        "latest_charge": "ch_db048" if status == "succeeded" else None,
        "metadata": {
            "tenant_id": str(attempt.tenant_id),
            "invoice_id": str(attempt.invoice_id),
            "customer_id": str(attempt.customer_id),
            "invoice_payment_attempt_id": str(attempt.id),
            "provider_configuration_version": str(
                attempt.provider_configuration_version
            ),
            "stripe_connected_account_id": attempt.provider_account_id,
            "principal_amount": "100.00",
            "card_fee_amount": "2.50",
            "card_fee_tax_amount": "0.50",
        },
    }
    return intent


@pytest.mark.asyncio
async def test_finalize_stripe_invoice_payment_creates_payment_and_marks_paid(monkeypatch):
    tenant, customer, order, invoice = _entities()
    tenant.paid_invoice_webhook_enabled = True
    tenant.paid_invoice_webhook_url = "https://example.test/conversions"
    tenant.paid_invoice_webhook_secret_encrypted = "encrypted-test-secret"
    fake_db = _FinalizeSession()
    broadcasts: list[tuple[str, dict]] = []
    emails: list[dict] = []

    async def _payment_number(_db, _tenant_id):
        return "PAY-TEST-000001"

    async def _broadcast_payment(**kwargs):
        broadcasts.append(("payment", kwargs))

    async def _broadcast_order(**kwargs):
        broadcasts.append(("order", kwargs))

    async def _send_email(**kwargs):
        emails.append(kwargs)

    monkeypatch.setattr(svc, "allocate_next_payment_number", _payment_number)
    monkeypatch.setattr(svc, "broadcast_payment_received", _broadcast_payment)
    monkeypatch.setattr(svc, "broadcast_repair_order_update", _broadcast_order)
    monkeypatch.setattr(svc, "send_invoice_payment_confirmation_email", _send_email)
    monkeypatch.setattr(svc, "record_payment", lambda **_kwargs: None)

    result = await svc.finalize_stripe_invoice_payment(
        db=fake_db,
        invoice=invoice,
        order=order,
        customer=customer,
        tenant=tenant,
        vehicle=None,
        payment_intent={
            "id": "pi_succeeded",
            "metadata": {
                "invoice_id": str(invoice.id),
                "tenant_id": str(tenant.id),
                "stripe_connected_account_id": "acct_123",
                "platform_fee_percent": "1.500",
                "platform_fee_amount_cents": "155",
            },
            "latest_charge": "ch_123",
        },
        payment_note="Payment made by test.",
        provider_account_id="acct_123",
    )

    assert result.created is True
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.paid_at is not None
    assert order.status == RepairOrderStatus.PAID
    assert fake_db.commits == 1
    payment = next(obj for obj in fake_db.added if isinstance(obj, Payment))
    assert payment.payment_number == "PAY-TEST-000001"
    assert payment.method == PaymentMethod.STRIPE
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.stripe_payment_intent_id == "pi_succeeded"
    assert payment.stripe_charge_id == "ch_123"
    assert payment.stripe_connected_account_id == "acct_123"
    assert payment.stripe_platform_fee_percent == Decimal("1.500")
    assert payment.stripe_platform_fee_amount == Decimal("1.55")
    assert len(broadcasts) == 2
    assert len(emails) == 1
    events = [obj for obj in fake_db.added if isinstance(obj, ProviderOutboxEvent)]
    assert len(events) == 1
    assert events[0].event_type == "repair_order.paid"
    assert events[0].payload["repair_order_id"] == "RO-STRIPE"


@pytest.mark.asyncio
async def test_finalize_stripe_invoice_payment_is_idempotent_for_existing_intent(monkeypatch):
    tenant, customer, order, invoice = _entities()
    tenant.paid_invoice_webhook_enabled = True
    tenant.paid_invoice_webhook_url = "https://example.test/conversions"
    tenant.paid_invoice_webhook_secret_encrypted = "encrypted-test-secret"
    invoice.status = InvoiceStatus.PAID
    existing = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number="PAY-TEST-000001",
        amount=invoice.total_amount,
        method=PaymentMethod.STRIPE,
        status=PaymentStatus.COMPLETED,
        stripe_payment_intent_id="pi_succeeded",
    )
    fake_db = _FinalizeSession(existing_payment=existing)
    monkeypatch.setattr(svc, "record_payment", lambda **_kwargs: None)

    result = await svc.finalize_stripe_invoice_payment(
        db=fake_db,
        invoice=invoice,
        order=order,
        customer=customer,
        tenant=tenant,
        vehicle=None,
        payment_intent={
            "id": "pi_succeeded",
            "metadata": {
                "invoice_id": str(invoice.id),
                "tenant_id": str(tenant.id),
                "stripe_connected_account_id": "acct_123",
            },
        },
        payment_note="Payment made by test.",
        provider_account_id="acct_123",
    )

    assert result.created is False
    assert result.payment is existing
    assert fake_db.added == []
    assert fake_db.commits == 0


@pytest.mark.asyncio
async def test_legacy_finalizer_rejects_forged_account_before_idempotent_payment_lookup():
    tenant, customer, order, invoice = _entities()
    existing = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number="PAY-TEST-EXISTING",
        amount=invoice.total_amount,
        method=PaymentMethod.STRIPE,
        status=PaymentStatus.COMPLETED,
        stripe_payment_intent_id="pi_succeeded",
    )
    fake_db = _FinalizeSession(existing_payment=existing)

    with pytest.raises(svc.SettlementDomainError) as exc_info:
        await svc.finalize_stripe_invoice_payment(
            db=fake_db,
            invoice=invoice,
            order=order,
            customer=customer,
            tenant=tenant,
            vehicle=None,
            payment_intent=_legacy_intent(
                invoice,
                tenant,
                payment_intent_id="pi_succeeded",
                metadata_account_id="acct_foreign",
            ),
            payment_note="Payment made by test.",
            provider_account_id="acct_foreign",
        )

    assert exc_info.value.code == "provider_payment_mismatch"
    assert fake_db.payment_queries == 0
    assert fake_db.added == []
    assert fake_db.commits == 0
    assert invoice.status == InvoiceStatus.SENT
    assert order.status == RepairOrderStatus.INVOICED


@pytest.mark.asyncio
async def test_legacy_finalizer_rejects_tenant_without_completed_stripe_onboarding():
    tenant, customer, order, invoice = _entities()
    tenant.stripe_onboarding_complete = False
    fake_db = _FinalizeSession()

    with pytest.raises(svc.SettlementDomainError) as exc_info:
        await svc.finalize_stripe_invoice_payment(
            db=fake_db,
            invoice=invoice,
            order=order,
            customer=customer,
            tenant=tenant,
            vehicle=None,
            payment_intent=_legacy_intent(invoice, tenant),
            payment_note="Payment made by test.",
            provider_account_id="acct_123",
        )

    assert exc_info.value.code == "provider_payment_mismatch"
    assert fake_db.payment_queries == 0
    assert fake_db.added == []
    assert fake_db.commits == 0
    assert invoice.status == InvoiceStatus.SENT
    assert order.status == RepairOrderStatus.INVOICED


@pytest.mark.asyncio
async def test_legacy_finalizer_requires_matching_active_provider_snapshot_before_replay():
    tenant, customer, order, invoice = _entities()
    tenant.invoice_split_payments_enabled = True
    existing = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number="PAY-TEST-EXISTING",
        amount=invoice.total_amount,
        method=PaymentMethod.STRIPE,
        status=PaymentStatus.COMPLETED,
        stripe_payment_intent_id="pi_succeeded",
    )
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=1,
        selected_provider="stripe_connect",
        readiness_state="ready",
        is_active=True,
        actor_user_id=uuid4(),
        actor_name_snapshot="Config Owner",
        provider_account_snapshot="acct_123",
        writer_strategy="dieselbridge",
        idempotency_key="provider-config-1",
        request_hash="a" * 64,
    )
    fake_db = _FinalizeSession(existing_payment=existing, provider_config=config)

    result = await svc.finalize_stripe_invoice_payment(
        db=fake_db,
        invoice=invoice,
        order=order,
        customer=customer,
        tenant=tenant,
        vehicle=None,
        payment_intent=_legacy_intent(
            invoice,
            tenant,
            payment_intent_id="pi_succeeded",
        ),
        payment_note="Payment made by test.",
        provider_account_id="acct_123",
    )

    assert result.created is False
    assert result.payment is existing
    assert fake_db.payment_queries == 1
    assert fake_db.added == []
    assert fake_db.commits == 0


@pytest.mark.asyncio
async def test_legacy_finalizer_rejects_mismatched_active_provider_snapshot():
    tenant, customer, order, invoice = _entities()
    tenant.invoice_split_payments_enabled = True
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id,
        version=2,
        selected_provider="stripe_connect",
        readiness_state="ready",
        is_active=True,
        actor_user_id=uuid4(),
        actor_name_snapshot="Config Owner",
        provider_account_snapshot="acct_replaced",
        writer_strategy="dieselbridge",
        idempotency_key="provider-config-2",
        request_hash="b" * 64,
    )
    fake_db = _FinalizeSession(provider_config=config)

    with pytest.raises(svc.SettlementDomainError) as exc_info:
        await svc.finalize_stripe_invoice_payment(
            db=fake_db,
            invoice=invoice,
            order=order,
            customer=customer,
            tenant=tenant,
            vehicle=None,
            payment_intent=_legacy_intent(invoice, tenant),
            payment_note="Payment made by test.",
            provider_account_id="acct_123",
        )

    assert exc_info.value.code == "provider_payment_mismatch"
    assert fake_db.payment_queries == 0
    assert fake_db.added == []
    assert fake_db.commits == 0
    assert invoice.status == InvoiceStatus.SENT
    assert order.status == RepairOrderStatus.INVOICED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "inaccessible_state",
    [
        "invoice_deleted",
        "invoice_voided",
        "invoice_cancelled",
        "order_deleted",
        "order_cancelled",
    ],
)
async def test_legacy_finalizer_rejects_inaccessible_invoice_before_any_lookup_or_mutation(
    inaccessible_state,
):
    tenant, customer, order, invoice = _entities()
    timestamp = datetime.now(timezone.utc)
    if inaccessible_state == "invoice_deleted":
        invoice.deleted_at = timestamp
    elif inaccessible_state == "invoice_voided":
        invoice.voided_at = timestamp
    elif inaccessible_state == "invoice_cancelled":
        invoice.status = InvoiceStatus.CANCELLED
    elif inaccessible_state == "order_deleted":
        order.deleted_at = timestamp
    else:
        order.status = RepairOrderStatus.CANCELLED

    original_invoice_status = invoice.status
    original_order_status = order.status
    fake_db = _FinalizeSession()

    with pytest.raises(svc.SettlementDomainError) as exc_info:
        await svc.finalize_stripe_invoice_payment(
            db=fake_db,
            invoice=invoice,
            order=order,
            customer=customer,
            tenant=tenant,
            vehicle=None,
            payment_intent=_legacy_intent(invoice, tenant),
            payment_note="Payment made by test.",
            provider_account_id="acct_123",
        )

    assert exc_info.value.code == "invoice_not_found"
    assert exc_info.value.status_code == 404
    assert fake_db.payment_queries == 0
    assert fake_db.added == []
    assert fake_db.commits == 0
    assert invoice.status == original_invoice_status
    assert order.status == original_order_status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch",
    [
        "trusted_account",
        "intent_id",
        "intent_id_missing",
        "status",
        "currency",
        "amount",
        "amount_received",
        "latest_charge",
        "tenant_metadata",
        "invoice_metadata",
        "customer_metadata",
        "attempt_metadata",
        "attempt_metadata_missing",
        "configuration_metadata",
        "account_metadata",
        "principal_metadata",
        "card_fee_metadata",
        "card_fee_tax_metadata",
        "top_level_account",
        "tenant_missing",
        "tenant_deleted",
        "tenant_inactive",
        "tenant_identity",
        "customer_missing",
        "customer_deleted",
        "customer_tenant",
        "customer_identity",
        "historical_configuration_missing",
        "historical_configuration_provider",
        "historical_configuration_account",
    ],
)
async def test_db048_stripe_envelope_mismatch_is_zero_mutation(
    monkeypatch,
    mismatch,
):
    tenant, customer, order, invoice = _entities()
    # Prove that finalization follows the immutable attempt/config snapshot,
    # not a tenant's later current Stripe account.
    tenant.stripe_account_id = "acct_current"
    attempt, config = _db048_attempt_and_config(tenant, customer, invoice)
    intent = _db048_intent(attempt)
    trusted_account = "acct_historical"

    if mismatch == "trusted_account":
        trusted_account = None
    elif mismatch == "intent_id":
        intent["id"] = "pi_forged"
    elif mismatch == "intent_id_missing":
        intent.pop("id")
    elif mismatch == "status":
        intent["status"] = "processing"
    elif mismatch == "currency":
        intent["currency"] = "cad"
    elif mismatch == "amount":
        intent["amount"] = 10299
    elif mismatch == "amount_received":
        intent["amount_received"] = 10299
    elif mismatch == "latest_charge":
        intent["latest_charge"] = None
    elif mismatch == "tenant_metadata":
        intent["metadata"]["tenant_id"] = str(uuid4())
    elif mismatch == "invoice_metadata":
        intent["metadata"]["invoice_id"] = str(uuid4())
    elif mismatch == "customer_metadata":
        intent["metadata"]["customer_id"] = str(uuid4())
    elif mismatch == "attempt_metadata":
        intent["metadata"]["invoice_payment_attempt_id"] = str(uuid4())
    elif mismatch == "attempt_metadata_missing":
        intent["metadata"].pop("invoice_payment_attempt_id")
    elif mismatch == "configuration_metadata":
        intent["metadata"]["provider_configuration_version"] = "8"
    elif mismatch == "account_metadata":
        intent["metadata"]["stripe_connected_account_id"] = "acct_forged"
    elif mismatch == "principal_metadata":
        intent["metadata"]["principal_amount"] = "99.99"
    elif mismatch == "card_fee_metadata":
        intent["metadata"]["card_fee_amount"] = "2.49"
    elif mismatch == "card_fee_tax_metadata":
        intent["metadata"]["card_fee_tax_amount"] = "0.49"
    elif mismatch == "top_level_account":
        intent["account"] = "acct_forged"
    elif mismatch == "tenant_missing":
        tenant = None
    elif mismatch == "tenant_deleted":
        tenant.deleted_at = datetime.now(timezone.utc)
    elif mismatch == "tenant_inactive":
        tenant.is_active = False
    elif mismatch == "tenant_identity":
        tenant.id = uuid4()
    elif mismatch == "customer_missing":
        customer = None
    elif mismatch == "customer_deleted":
        customer.deleted_at = datetime.now(timezone.utc)
    elif mismatch == "customer_tenant":
        customer.tenant_id = uuid4()
    elif mismatch == "customer_identity":
        customer.id = uuid4()
    elif mismatch == "historical_configuration_missing":
        config = None
    elif mismatch == "historical_configuration_provider":
        config.selected_provider = "quickbooks_payments"
    elif mismatch == "historical_configuration_account":
        config.provider_account_snapshot = "acct_forged"

    fake_db = _DB048StripeSession(
        attempt=attempt,
        provider_config=config,
        tenant=tenant,
        customer=customer,
    )
    confirm_calls = 0

    async def _confirm_attempt(*_args, **_kwargs):
        nonlocal confirm_calls
        confirm_calls += 1
        raise AssertionError("strict mismatch must not reach financial confirmation")

    monkeypatch.setattr(svc, "confirm_attempt", _confirm_attempt)
    original_invoice_status = invoice.status
    original_order_status = order.status
    original_attempt_state = attempt.state

    with pytest.raises(svc.SettlementDomainError) as exc_info:
        await svc.finalize_stripe_invoice_payment(
            db=fake_db,
            invoice=invoice,
            order=order,
            customer=customer,
            tenant=tenant,
            vehicle=None,
            payment_intent=intent,
            payment_note="DB-048 browser confirmation.",
            provider_account_id=trusted_account,
        )

    assert exc_info.value.code == "provider_payment_mismatch"
    assert confirm_calls == 0
    assert fake_db.added == []
    assert fake_db.commits == 0
    assert fake_db.rollbacks == 0
    assert invoice.status == original_invoice_status
    assert order.status == original_order_status
    assert attempt.state == original_attempt_state


@pytest.mark.asyncio
async def test_db048_stripe_success_uses_historical_config_and_distinct_provider_ids(
    monkeypatch,
):
    tenant, customer, order, invoice = _entities()
    tenant.stripe_account_id = "acct_current"
    attempt, config = _db048_attempt_and_config(tenant, customer, invoice)
    intent = _db048_intent(attempt)
    fake_db = _DB048StripeSession(
        attempt=attempt,
        provider_config=config,
        tenant=tenant,
        customer=customer,
    )
    payment = Payment(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        payment_number="PAY-DB048",
        amount=Decimal("100.00"),
        method=PaymentMethod.STRIPE,
        status=PaymentStatus.COMPLETED,
    )
    confirm_calls: list[dict] = []

    async def _confirm_attempt(*_args, **kwargs):
        confirm_calls.append(kwargs)
        return SimpleNamespace(
            payment=payment,
            paid_transition=False,
            replayed=len(confirm_calls) > 1,
        )

    async def _noop(**_kwargs):
        return None

    monkeypatch.setattr(svc, "confirm_attempt", _confirm_attempt)
    monkeypatch.setattr(svc, "broadcast_payment_received", _noop)
    monkeypatch.setattr(svc, "broadcast_repair_order_update", _noop)
    monkeypatch.setattr(svc, "record_payment", lambda **_kwargs: None)

    first = await svc.finalize_stripe_invoice_payment(
        db=fake_db,
        invoice=invoice,
        order=order,
        customer=customer,
        tenant=tenant,
        vehicle=None,
        payment_intent=intent,
        payment_note="DB-048 webhook confirmation.",
        provider_account_id="acct_historical",
        provider_event_id="evt_db048_succeeded",
    )
    second = await svc.finalize_stripe_invoice_payment(
        db=fake_db,
        invoice=invoice,
        order=order,
        customer=customer,
        tenant=tenant,
        vehicle=None,
        payment_intent=intent,
        payment_note="DB-048 webhook confirmation.",
        provider_account_id="acct_historical",
        provider_event_id="evt_db048_succeeded",
    )

    assert first.created is True
    assert second.created is False
    assert len(confirm_calls) == 2
    assert confirm_calls[0]["reference"] == "pi_db048"
    assert confirm_calls[0]["provider_charge_id"] == "ch_db048"
    assert confirm_calls[0]["provider_event_id"] == "evt_db048_succeeded"
    assert confirm_calls[0]["idempotency_key"].endswith(
        ":evt_db048_succeeded:confirmed"
    )
    assert fake_db.commits == 2
    assert fake_db.added == []


@pytest.mark.asyncio
async def test_db048_failed_webhook_validates_envelope_and_lifecycle_before_release(
    monkeypatch,
):
    tenant, customer, _order, invoice = _entities()
    attempt, config = _db048_attempt_and_config(tenant, customer, invoice)
    intent = _db048_intent(attempt, status="requires_payment_method")
    intent["last_payment_error"] = {
        "code": "card_declined",
        "message": "The card was declined.",
    }
    fake_db = _DB048StripeSession(
        attempt=attempt,
        provider_config=config,
        tenant=tenant,
        customer=customer,
    )
    sequence: list[str] = []
    failure_calls: list[dict] = []

    async def _lifecycle(_db, candidate):
        assert candidate is attempt
        sequence.append("lifecycle")
        return invoice

    async def _fail(_db, **kwargs):
        sequence.append("fail")
        failure_calls.append(kwargs)
        return attempt, SimpleNamespace()

    async def _log_error(**_kwargs):
        sequence.append("error_log")

    monkeypatch.setattr(stripe_webhooks, "locked_accessible_invoice_for_attempt", _lifecycle)
    monkeypatch.setattr(stripe_webhooks, "fail_attempt", _fail)
    monkeypatch.setattr(stripe_webhooks.error_service, "log_error", _log_error)
    monkeypatch.setattr(stripe_webhooks, "record_payment", lambda **_kwargs: None)
    monkeypatch.setattr(stripe_webhooks, "record_payment_error", lambda **_kwargs: None)

    await stripe_webhooks._handle_payment_failed(
        fake_db,
        intent,
        event={"id": "evt_db048_failed", "account": "acct_historical"},
    )

    assert sequence == ["lifecycle", "fail", "error_log"]
    assert failure_calls[0]["attempt_id"] == attempt.id
    assert failure_calls[0]["tenant_id"] == attempt.tenant_id
    assert failure_calls[0]["idempotency_key"].endswith(
        ":evt_db048_failed:failed"
    )
    assert fake_db.added == []
    assert fake_db.commits == 0


@pytest.mark.asyncio
async def test_db048_failed_webhook_lifecycle_denial_has_zero_release_mutation(
    monkeypatch,
):
    tenant, customer, _order, invoice = _entities()
    attempt, config = _db048_attempt_and_config(tenant, customer, invoice)
    intent = _db048_intent(attempt, status="requires_payment_method")
    fake_db = _DB048StripeSession(
        attempt=attempt,
        provider_config=config,
        tenant=tenant,
        customer=customer,
    )
    fail_calls = 0
    error_log_calls = 0

    async def _deny_lifecycle(_db, _attempt):
        raise svc.SettlementDomainError(
            "invoice_not_found", "Invoice not found.", status_code=404,
        )

    async def _fail(*_args, **_kwargs):
        nonlocal fail_calls
        fail_calls += 1

    async def _log_error(**_kwargs):
        nonlocal error_log_calls
        error_log_calls += 1

    monkeypatch.setattr(stripe_webhooks, "locked_accessible_invoice_for_attempt", _deny_lifecycle)
    monkeypatch.setattr(stripe_webhooks, "fail_attempt", _fail)
    monkeypatch.setattr(stripe_webhooks.error_service, "log_error", _log_error)
    monkeypatch.setattr(stripe_webhooks, "record_payment", lambda **_kwargs: None)
    monkeypatch.setattr(stripe_webhooks, "record_payment_error", lambda **_kwargs: None)

    with pytest.raises(svc.SettlementDomainError) as exc_info:
        await stripe_webhooks._handle_payment_failed(
            fake_db,
            intent,
            event={"id": "evt_db048_failed", "account": "acct_historical"},
        )

    assert exc_info.value.code == "invoice_not_found"
    assert fail_calls == 0
    assert error_log_calls == 0
    assert fake_db.added == []
    assert fake_db.commits == 0
    assert attempt.state == "pending"


@pytest.mark.asyncio
async def test_db048_failed_webhook_missing_attempt_metadata_cannot_downgrade(
    monkeypatch,
):
    tenant, customer, _order, invoice = _entities()
    attempt, config = _db048_attempt_and_config(tenant, customer, invoice)
    intent = _db048_intent(attempt, status="requires_payment_method")
    intent["metadata"].pop("invoice_payment_attempt_id")
    fake_db = _DB048StripeSession(
        attempt=attempt,
        provider_config=config,
        tenant=tenant,
        customer=customer,
    )
    lifecycle_calls = 0
    fail_calls = 0
    error_log_calls = 0

    async def _lifecycle(*_args, **_kwargs):
        nonlocal lifecycle_calls
        lifecycle_calls += 1

    async def _fail(*_args, **_kwargs):
        nonlocal fail_calls
        fail_calls += 1

    async def _log_error(**_kwargs):
        nonlocal error_log_calls
        error_log_calls += 1

    monkeypatch.setattr(stripe_webhooks, "locked_accessible_invoice_for_attempt", _lifecycle)
    monkeypatch.setattr(stripe_webhooks, "fail_attempt", _fail)
    monkeypatch.setattr(stripe_webhooks.error_service, "log_error", _log_error)

    with pytest.raises(svc.SettlementDomainError) as exc_info:
        await stripe_webhooks._handle_payment_failed(
            fake_db,
            intent,
            event={"id": "evt_db048_failed", "account": "acct_historical"},
        )

    assert exc_info.value.code == "provider_payment_mismatch"
    assert lifecycle_calls == 0
    assert fail_calls == 0
    assert error_log_calls == 0
    assert fake_db.added == []
    assert fake_db.commits == 0
    assert attempt.state == "pending"


@pytest.mark.asyncio
async def test_payment_succeeded_webhook_invokes_local_finalization(monkeypatch):
    tenant, customer, order, invoice = _entities()
    fake_db = _WebhookSession(invoice=invoice, tenant=tenant)
    captured = {}

    async def _finalize(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(created=True)

    monkeypatch.setattr(stripe_webhooks, "finalize_stripe_invoice_payment", _finalize)

    await stripe_webhooks._handle_payment_succeeded(
        fake_db,
        {
            "id": "pi_webhook",
            "metadata": {
                "invoice_id": str(invoice.id),
                "tenant_id": str(tenant.id),
                "stripe_connected_account_id": "acct_123",
            },
        },
        event={"account": "acct_123"},
    )

    assert fake_db.execute_calls == 2
    assert captured["invoice"] is invoice
    assert captured["order"] is order
    assert captured["customer"] is customer
    assert captured["tenant"] is tenant
    assert captured["payment_intent"]["id"] == "pi_webhook"
    assert captured["allow_already_paid_without_payment"] is True
    assert captured["provider_account_id"] == "acct_123"


@pytest.mark.asyncio
async def test_db048_succeeded_webhook_preserves_signed_event_identity(monkeypatch):
    tenant, customer, order, invoice = _entities()
    attempt, _config = _db048_attempt_and_config(tenant, customer, invoice)
    fake_db = _WebhookSession(invoice=invoice, tenant=tenant)
    captured = {}

    async def _finalize(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(created=True)

    monkeypatch.setattr(stripe_webhooks, "finalize_stripe_invoice_payment", _finalize)

    await stripe_webhooks._handle_payment_succeeded(
        fake_db,
        _db048_intent(attempt),
        event={"id": "evt_signed_success", "account": "acct_historical"},
    )

    assert captured["provider_account_id"] == "acct_historical"
    assert captured["provider_event_id"] == "evt_signed_success"
    assert captured["payment_intent"]["id"] == "pi_db048"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "event",
        "metadata_tenant_id",
        "metadata_account_id",
        "include_tenant_id",
        "expected_query_count",
    ),
    [
        (None, None, "acct_123", True, 0),
        ({"account": "acct_123"}, None, None, True, 0),
        ({"account": "acct_123"}, None, "acct_123", False, 0),
        ({"account": "acct_foreign"}, "foreign-tenant", "acct_foreign", True, 2),
        ({"account": "acct_foreign"}, None, "acct_foreign", True, 2),
    ],
    ids=[
        "missing-signed-account",
        "missing-account-metadata",
        "missing-tenant-metadata",
        "foreign-tenant-and-account",
        "foreign-account",
    ],
)
async def test_legacy_webhook_identity_mismatch_has_zero_financial_mutation(
    monkeypatch,
    event,
    metadata_tenant_id,
    metadata_account_id,
    include_tenant_id,
    expected_query_count,
):
    tenant, _customer, order, invoice = _entities()
    fake_db = _WebhookSession(invoice=invoice, tenant=tenant)
    finalizer_calls = 0

    async def _finalize(**_kwargs):
        nonlocal finalizer_calls
        finalizer_calls += 1
        raise AssertionError("legacy finalizer must not run for mismatched identity")

    monkeypatch.setattr(stripe_webhooks, "finalize_stripe_invoice_payment", _finalize)
    payment_intent = _legacy_intent(
        invoice,
        tenant,
        metadata_tenant_id=metadata_tenant_id,
        metadata_account_id=metadata_account_id,
        include_tenant_id=include_tenant_id,
    )

    expected_exception = HTTPException if expected_query_count == 0 else svc.SettlementDomainError
    with pytest.raises(expected_exception):
        await stripe_webhooks._handle_payment_succeeded(
            fake_db,
            payment_intent,
            event=event,
        )

    assert fake_db.execute_calls == expected_query_count
    assert finalizer_calls == 0
    assert fake_db.added == []
    assert fake_db.commits == 0
    assert invoice.status == InvoiceStatus.SENT
    assert order.status == RepairOrderStatus.INVOICED
