"""DB-048 tenant-scoped staff and customer settlement interfaces."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import CurrentUser, get_current_active_user, get_db, identity_user, user_has_permission
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    CustomerCreditDueDiligenceEvent, CustomerCreditEntry,
    InvoicePaymentAttempt, InvoicePaymentLedgerEvent, InvoiceSettlement,
    PaymentAccountingLink, PaymentOverpayment, PaymentRefund,
    ProviderSettlementBatch, ProviderSettlementEntry,
    TenantPaymentProviderConfiguration,
)
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.schemas.invoice_settlement import (
    AccountingReconciliationRead, AccountingRetryResponse,
    CardProviderConfigurationRead, CardProviderConfigurationUpdate,
    CardProviderReadiness, CreditAgingItem, CreditApplicationCreate,
    CreditDueDiligenceCreate,
    CreditConsentCreate, EarlyReleaseOverride, EligibleCreditItem,
    InvoiceSettlementSummary, ManualRefundConfirm,
    PaymentAllocationItem, PaymentAllocationPage, PaymentAttemptConfirm,
    PaymentAttemptCreate, PaymentAttemptFail, PaymentAttemptResponse,
    QuickBooksAttemptCharge,
    PaymentRefundCreate,
    ProviderOptionReadiness, SettlementAllowedActions,
)
from app.services.invoice_settlement_service import (
    SettlementDomainError, allocatable_balance, apply_customer_credit,
    append_ledger_event, authorize_early_release,
    confirm_attempt, confirm_manual_refund, create_attempt, create_refund,
    fail_attempt, get_or_create_settlement, load_active_configuration,
    money, provider_readiness, record_credit_consent, require_feature_ready,
)
from app.services.stripe_customer_service import ensure_connected_stripe_customer
from app.services.stripe_platform_fee import platform_fee_amount_cents, platform_fee_percent_for
from app.services.quickbooks_accounting_service import quickbooks_invoice_memo
from app.services.quickbooks_payments_service import (
    QuickBooksPaymentError,
    charge_client_transaction_id,
    create_charge as create_quickbooks_charge,
    get_charge as get_quickbooks_charge,
    is_successful_charge as is_successful_quickbooks_charge,
    payments_base_url,
)
from app.api.v1.endpoints.quickbooks import _refresh_connection_if_needed


router = APIRouter()
stripe.api_key = settings.STRIPE_SECRET_KEY
STAFF_ROLES = {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST}


def _idempotency_key(value: Optional[str]) -> str:
    key = (value or "").strip()
    if not key or len(key) > 255:
        raise SettlementDomainError("idempotency_key_required", "A valid Idempotency-Key header is required.", status_code=422)
    return key


def _is_staff(user: CurrentUser) -> bool:
    return user.role in STAFF_ROLES


def _can_manage_money(user: CurrentUser) -> bool:
    return user.role in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN} and user_has_permission(user, "payments")


async def invoice_for_principal(
    db: AsyncSession,
    invoice_id: UUID,
    principal: CurrentUser,
) -> tuple[Invoice, Tenant, UUID]:
    query = (
        select(Invoice)
        .join(RepairOrder, RepairOrder.id == Invoice.repair_order_id)
        .options(
            selectinload(Invoice.repair_order).selectinload(RepairOrder.customer),
            selectinload(Invoice.repair_order).selectinload(RepairOrder.vehicle),
        )
        .where(
            Invoice.id == invoice_id,
            Invoice.deleted_at.is_(None),
            Invoice.status != InvoiceStatus.CANCELLED,
            Invoice.voided_at.is_(None),
            RepairOrder.tenant_id == Invoice.tenant_id,
            RepairOrder.deleted_at.is_(None),
            RepairOrder.status != RepairOrderStatus.CANCELLED,
        )
    )
    if _is_staff(principal):
        query = query.where(Invoice.tenant_id == principal.tenant_id)
    elif principal.role == UserRole.CUSTOMER:
        query = query.where(
            Invoice.tenant_id == principal.tenant_id,
            RepairOrder.customer_id == principal.customer_id,
        )
    else:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    invoice = (await db.execute(query)).scalar_one_or_none()
    if (
        not invoice
        or not invoice.repair_order
        or invoice.repair_order.deleted_at is not None
    ):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id, Tenant.is_active.is_(True)))).scalar_one_or_none()
    if not tenant:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    return invoice, tenant, invoice.repair_order.customer_id


def _public_provider_status(readiness) -> str:
    if not readiness.split_payment_global_gate or not readiness.split_payment_tenant_gate:
        return "feature_disabled"
    if readiness.configuration is None:
        return "not_configured"
    if readiness.status == "unavailable_external_approval":
        return "unavailable_external_approval"
    if not readiness.provider_onboarding_ready:
        return "onboarding_incomplete"
    if not readiness.qbo_accounting_ready:
        return "accounting_unavailable"
    if not readiness.mappings_ready:
        return "accounting_mapping_incomplete"
    return "ready" if readiness.status == "ready" else "not_configured"


def _allowed_actions(
    *,
    settlement: InvoiceSettlement,
    readiness,
    audience: str,
    current_user: Optional[CurrentUser] = None,
) -> SettlementAllowedActions:
    ready = readiness.status == "ready"
    can_create = ready and allocatable_balance(settlement) > Decimal("0.00")
    is_staff = audience == "staff"
    is_customer = audience == "customer"
    manager = bool(current_user and _can_manage_money(current_user))
    rails = ["card", "zelle", "check", "ach"] if is_staff else ["card", "zelle"]
    return SettlementAllowedActions(
        create_attempt=can_create,
        rails=rails if can_create else [],
        confirm_manual=is_staff and ready,
        resolve_overpayment=manager,
        apply_customer_credit=ready and (manager or is_customer),
        authorize_early_release=(
            ready
            and manager
            and money(settlement.confirmed_principal) < money(settlement.principal_total)
        ),
        retry_accounting=manager,
        configure_provider=manager,
    )


async def settlement_summary(
    db: AsyncSession,
    settlement: InvoiceSettlement,
    tenant: Tenant,
    *,
    audience: str,
    current_user: Optional[CurrentUser] = None,
) -> InvoiceSettlementSummary:
    readiness = await provider_readiness(db, tenant)
    feature_enabled = readiness.split_payment_global_gate and readiness.split_payment_tenant_gate
    return InvoiceSettlementSummary(
        invoice_id=settlement.invoice_id,
        currency=settlement.currency,
        principal_total=money(settlement.principal_total),
        confirmed_principal=money(settlement.confirmed_principal),
        active_pending_principal=money(settlement.active_pending_principal),
        outstanding_balance=max(
            Decimal("0.00"),
            money(settlement.principal_total) - money(settlement.confirmed_principal),
        ),
        allocatable_balance=allocatable_balance(settlement),
        unapplied_credit=money(settlement.unapplied_credit),
        refund_pending=money(settlement.refund_pending),
        state=settlement.state,
        version=settlement.version,
        card_provider=readiness.provider,
        card_provider_status=_public_provider_status(readiness),
        accounting_sync_status=settlement.accounting_sync_status,
        feature_enabled=feature_enabled,
        allowed_actions=_allowed_actions(
            settlement=settlement,
            readiness=readiness,
            audience=audience,
            current_user=current_user,
        ),
    )


async def attempt_response(
    db: AsyncSession,
    attempt: InvoicePaymentAttempt,
    settlement: InvoiceSettlement,
    tenant: Tenant,
    client_secret: Optional[str] = None,
    provider_token_url: Optional[str] = None,
    *,
    audience: str,
    current_user: Optional[CurrentUser] = None,
) -> PaymentAttemptResponse:
    return PaymentAttemptResponse(
        attempt_id=attempt.id, invoice_id=attempt.invoice_id,
        principal_amount=money(attempt.principal_amount),
        card_fee_amount=money(attempt.card_fee_amount),
        card_fee_tax_amount=money(attempt.card_fee_tax_amount),
        applied_card_fee_amount=money(attempt.applied_card_fee_amount),
        applied_card_fee_tax_amount=money(attempt.applied_card_fee_tax_amount),
        provider_charge_amount=money(attempt.provider_charge_amount),
        rail=attempt.rail, provider=attempt.provider,
        card_provider=attempt.provider if attempt.rail == "card" else None,
        state=attempt.state,
        expires_at=attempt.expires_at,
        provider_configuration_version=attempt.provider_configuration_version,
        configuration_version=attempt.provider_configuration_version,
        attempt_version=attempt.version,
        failure_code=attempt.failure_code,
        provider_client_secret=client_secret,
        provider_token_url=provider_token_url,
        provider_account_id=attempt.provider_account_id,
        stripe_account_id=attempt.provider_account_id if attempt.provider == "stripe_connect" else None,
        settlement=await settlement_summary(
            db, settlement, tenant, audience=audience, current_user=current_user,
        ),
    )


@router.get("/invoices/{invoice_id}/settlement", response_model=InvoiceSettlementSummary)
async def read_invoice_settlement(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    invoice, tenant, customer_id = await invoice_for_principal(db, invoice_id, current_user)
    settlement = await _settlement_for_read(
        db,
        invoice=invoice,
        tenant=tenant,
        customer_id=customer_id,
    )
    audience = "customer" if current_user.role == UserRole.CUSTOMER else "staff"
    return await settlement_summary(
        db, settlement, tenant, audience=audience, current_user=current_user,
    )


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{row_id}".encode()).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        timestamp, row_id = base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
        return datetime.fromisoformat(timestamp), UUID(row_id)
    except Exception as exc:
        raise SettlementDomainError("invalid_cursor", "The allocation cursor is invalid.", status_code=422) from exc


@router.get("/invoices/{invoice_id}/allocations", response_model=PaymentAllocationPage)
async def list_invoice_allocations(
    invoice_id: UUID,
    cursor: Optional[str] = None,
    limit: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    invoice, tenant, customer_id = await invoice_for_principal(db, invoice_id, current_user)
    await _settlement_for_read(
        db, invoice=invoice, tenant=tenant, customer_id=customer_id,
    )
    audience = "customer" if current_user.role == UserRole.CUSTOMER else "staff"
    return await allocation_page(
        db, invoice=invoice, cursor=cursor, limit=limit, audience=audience,
    )


async def _settlement_for_read(
    db: AsyncSession,
    *,
    invoice: Invoice,
    tenant: Tenant,
    customer_id: UUID,
) -> InvoiceSettlement:
    """Return a pre-existing settlement during rollback without mutating it.

    When no DB-048 state exists, disabled/unverified probes remain a stable
    409 and never create rows that would poison backfill reconciliation.
    """
    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == tenant.id,
        InvoiceSettlement.invoice_id == invoice.id,
        InvoiceSettlement.customer_id == customer_id,
    ))
    if settlement is not None:
        return settlement
    await require_feature_ready(db, tenant)
    settlement = await get_or_create_settlement(
        db,
        invoice=invoice,
        customer_id=customer_id,
        tenant=tenant,
        lock=False,
    )
    await db.commit()
    return settlement


def _masked_payment_reference(reference: Optional[str]) -> Optional[str]:
    """Expose recognition, not full bank/provider evidence, outside staff."""
    if not reference:
        return None
    normalized = str(reference).strip()
    if not normalized:
        return None
    suffix = normalized[-4:] if len(normalized) > 4 else ""
    return f"••••{suffix}" if suffix else "••••"


async def allocation_page(
    db: AsyncSession,
    *,
    invoice: Invoice,
    cursor: Optional[str],
    limit: int,
    audience: str,
) -> PaymentAllocationPage:
    query = select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.invoice_id == invoice.id,
        InvoicePaymentAttempt.tenant_id == invoice.tenant_id,
        InvoicePaymentAttempt.deleted_at.is_(None),
    )
    if cursor:
        cursor_at, cursor_id = _decode_cursor(cursor)
        query = query.where(or_(
            InvoicePaymentAttempt.created_at < cursor_at,
            (InvoicePaymentAttempt.created_at == cursor_at) & (InvoicePaymentAttempt.id < cursor_id),
        ))
    rows = (await db.execute(query.order_by(InvoicePaymentAttempt.created_at.desc(), InvoicePaymentAttempt.id.desc()).limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    attempt_ids = [row.id for row in rows]
    overpayments = {
        row.source_attempt_id: row
        for row in (
            await db.execute(
                select(PaymentOverpayment).where(
                    PaymentOverpayment.tenant_id == invoice.tenant_id,
                    PaymentOverpayment.invoice_id == invoice.id,
                    PaymentOverpayment.source_attempt_id.in_(attempt_ids),
                )
            )
        ).scalars().all()
    } if attempt_ids else {}
    overpayment_ids = [row.id for row in overpayments.values()]
    refunds = {
        row.overpayment_id: row
        for row in (
            await db.execute(
                select(PaymentRefund).where(
                    PaymentRefund.tenant_id == invoice.tenant_id,
                    PaymentRefund.invoice_id == invoice.id,
                    PaymentRefund.overpayment_id.in_(overpayment_ids),
                )
            )
        ).scalars().all()
    } if overpayment_ids else {}
    staff_evidence = audience == "staff"
    return PaymentAllocationPage(
        items=[PaymentAllocationItem(
            id=row.id, attempt_id=row.id, created_at=row.created_at, rail=row.rail,
            provider=row.provider, state=row.state, attempt_version=row.version,
            failure_code=row.failure_code,
            principal_amount=money(row.principal_amount),
            applied_principal_amount=money(row.applied_principal_amount),
            card_fee_amount=money(row.card_fee_amount),
            card_fee_tax_amount=money(row.card_fee_tax_amount),
            applied_card_fee_amount=money(row.applied_card_fee_amount),
            applied_card_fee_tax_amount=money(row.applied_card_fee_tax_amount),
            provider_charge_amount=money(row.provider_charge_amount),
            received_amount=money(row.received_amount) if row.received_amount is not None else None,
            unapplied_amount=money(row.unapplied_amount), expires_at=row.expires_at,
            confirmed_at=row.confirmed_at,
            reference=(
                row.provider_reference
                if staff_evidence else _masked_payment_reference(row.provider_reference)
            ),
            reference_number=(
                row.provider_reference
                if staff_evidence else _masked_payment_reference(row.provider_reference)
            ),
            actor_name=row.actor_name_snapshot,
            accounting_sync_status=(
                "pending" if row.state == "confirmed" and not row.payment_id else None
            ),
            overpayment_id=(overpayments[row.id].id if row.id in overpayments else None),
            overpayment_state=(overpayments[row.id].state if row.id in overpayments else None),
            refund_id=(
                refunds[overpayments[row.id].id].id
                if row.id in overpayments and overpayments[row.id].id in refunds else None
            ),
            refund_state=(
                refunds[overpayments[row.id].id].state
                if row.id in overpayments and overpayments[row.id].id in refunds else None
            ),
        ) for row in rows],
        next_cursor=_encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None,
    )


async def _create_stripe_intent(
    db: AsyncSession,
    *,
    attempt: InvoicePaymentAttempt,
    tenant: Tenant,
    invoice: Invoice,
    customer: Customer,
    idempotency_key: str,
) -> tuple[str, str]:
    provider_account_id = attempt.provider_account_id
    if not provider_account_id:
        raise SettlementDomainError(
            "provider_payment_mismatch",
            "The provider payment configuration is unavailable.",
            status_code=409,
        )
    amount_cents = int(money(attempt.provider_charge_amount) * 100)
    params = {
        "amount": amount_cents, "currency": "usd",
        "metadata": {
            "invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number,
            "tenant_id": str(tenant.id), "customer_id": str(customer.id),
            "invoice_payment_attempt_id": str(attempt.id),
            "provider_configuration_version": str(attempt.provider_configuration_version),
            "principal_amount": str(money(attempt.principal_amount)),
            "card_fee_amount": str(money(attempt.card_fee_amount)),
            "card_fee_tax_amount": str(money(attempt.card_fee_tax_amount)),
            "stripe_connected_account_id": provider_account_id,
        },
        "customer": await ensure_connected_stripe_customer(
            db, customer, provider_account_id,
        ),
        "receipt_email": customer.email,
        "automatic_payment_methods": {"enabled": True},
        "stripe_account": provider_account_id,
        "idempotency_key": f"db048:{tenant.id}:{idempotency_key}",
    }
    platform_fee = platform_fee_amount_cents(amount_cents, platform_fee_percent_for(tenant))
    if platform_fee > 0:
        params["application_fee_amount"] = platform_fee
    intent = stripe.PaymentIntent.create(**params)
    return intent.id, intent.client_secret


async def _persist_and_bind_stripe_intent(
    db: AsyncSession,
    *,
    attempt: InvoicePaymentAttempt,
    tenant: Tenant,
    invoice: Invoice,
    customer: Customer,
    idempotency_key: str,
    actor: Optional[CurrentUser],
) -> tuple[InvoicePaymentAttempt, str]:
    """Durably retain a reservation before provider I/O, then bind its intent.

    Stripe's idempotency key closes the crash window between provider creation
    and the local binding update.  A provider-create failure transitions the
    already-durable attempt to failed and releases only its reservation.
    """
    attempt_id = attempt.id
    tenant_id = tenant.id
    await db.commit()
    persisted = (
        await db.execute(
            select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.id == attempt_id,
                InvoicePaymentAttempt.tenant_id == tenant_id,
            )
        )
    ).scalar_one()
    if persisted.state != "pending":
        raise SettlementDomainError(
            "card_provider_error",
            "The card provider could not create this payment.",
            status_code=502,
            retryable=True,
        )
    try:
        if persisted.provider_intent_id:
            intent = stripe.PaymentIntent.retrieve(
                persisted.provider_intent_id,
                stripe_account=persisted.provider_account_id,
            )
            provider_intent_id = persisted.provider_intent_id
            client_secret = intent.client_secret
        else:
            provider_intent_id, client_secret = await _create_stripe_intent(
                db,
                attempt=persisted,
                tenant=tenant,
                invoice=invoice,
                customer=customer,
                idempotency_key=idempotency_key,
            )
        bound = (
            await db.execute(
                select(InvoicePaymentAttempt)
                .where(
                    InvoicePaymentAttempt.id == attempt_id,
                    InvoicePaymentAttempt.tenant_id == tenant_id,
                )
                .with_for_update()
            )
        ).scalar_one()
        if bound.provider_intent_id and bound.provider_intent_id != provider_intent_id:
            raise SettlementDomainError(
                "provider_attempt_mismatch",
                "The card provider attempt does not match.",
            )
        bound.provider_intent_id = provider_intent_id
        await db.commit()
        return bound, client_secret
    except stripe.error.StripeError as exc:
        await db.rollback()
        current = (
            await db.execute(
                select(InvoicePaymentAttempt).where(
                    InvoicePaymentAttempt.id == attempt_id,
                    InvoicePaymentAttempt.tenant_id == tenant_id,
                )
            )
        ).scalar_one()
        if current.state == "pending":
            await fail_attempt(
                db,
                attempt_id=attempt_id,
                tenant_id=tenant_id,
                # The attempt already holds the immutable creator snapshot;
                # failure reconciliation is a system/provider transition and
                # must not dereference an expired ORM user after rollback.
                actor=None,
                expected_attempt_version=current.version,
                failure_code=type(exc).__name__,
                idempotency_key=f"{idempotency_key}:provider-create-failed",
            )
            await db.commit()
        raise SettlementDomainError(
            "card_provider_error",
            "The card provider could not create this payment.",
            status_code=502,
            retryable=True,
        ) from exc


@router.post("/invoices/{invoice_id}/attempts", response_model=PaymentAttemptResponse)
async def create_invoice_payment_attempt(
    invoice_id: UUID,
    body: PaymentAttemptCreate,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    key = _idempotency_key(idempotency_header)
    invoice, tenant, customer_id = await invoice_for_principal(db, invoice_id, current_user)
    source = "customer_portal" if current_user.role == UserRole.CUSTOMER else "staff"
    subject_type = "customer" if current_user.role == UserRole.CUSTOMER else "staff"
    creation = await create_attempt(
        db, invoice=invoice, tenant=tenant, customer_id=customer_id, actor=current_user,
        amount=body.amount, rail=body.rail,
        expected_settlement_version=body.expected_settlement_version,
        idempotency_key=key, source=source, subject_type=subject_type,
        subject_id=identity_user(current_user).id,
        sender_evidence=body.sender_evidence.model_dump(exclude_none=True) if body.sender_evidence else {},
    )
    client_secret = None
    provider_token_url = None
    if creation.attempt.rail == "card" and creation.attempt.provider == "stripe_connect":
        bound, client_secret = await _persist_and_bind_stripe_intent(
            db,
            attempt=creation.attempt,
            tenant=tenant,
            invoice=invoice,
            customer=invoice.repair_order.customer,
            idempotency_key=key,
            actor=current_user,
        )
        creation = type(creation)(bound, creation.settlement, creation.replayed)
    elif creation.attempt.rail == "card" and creation.attempt.provider == "quickbooks_payments":
        provider_token_url = f"{payments_base_url()}/quickbooks/v4/payments/tokens"
        await db.commit()
    else:
        await db.commit()
    audience = "customer" if current_user.role == UserRole.CUSTOMER else "staff"
    return await attempt_response(
        db, creation.attempt, creation.settlement, tenant, client_secret,
        provider_token_url,
        audience=audience, current_user=current_user,
    )


async def charge_quickbooks_settlement_attempt(
    db: AsyncSession,
    *,
    attempt: InvoicePaymentAttempt,
    invoice: Invoice,
    tenant: Tenant,
    actor: Optional[CurrentUser],
    payment_token: str,
    expected_attempt_version: int,
    idempotency_key: str,
):
    if (
        attempt.invoice_id != invoice.id
        or attempt.tenant_id != tenant.id
        or attempt.rail != "card"
        or attempt.provider != "quickbooks_payments"
    ):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if attempt.state == "confirmed":
        return await confirm_attempt(
            db,
            attempt_id=attempt.id,
            tenant=tenant,
            actor=actor,
            expected_attempt_version=expected_attempt_version,
            idempotency_key=idempotency_key,
            provider_charge_id=attempt.provider_charge_id,
        )
    if attempt.version != expected_attempt_version:
        raise SettlementDomainError(
            "stale_attempt_version",
            "The payment attempt changed. Refresh and try again.",
            current_version=attempt.version,
        )
    if attempt.state != "pending":
        raise SettlementDomainError("attempt_transition_conflict", "This payment attempt cannot be charged.")
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant.id,
        TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version,
        TenantPaymentProviderConfiguration.selected_provider == "quickbooks_payments",
    ))
    connection = await db.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant.id,
        QuickBooksConnection.status == "connected",
        QuickBooksConnection.deleted_at.is_(None),
    ))
    if not (
        config
        and connection
        and connection.realm_id == config.qbo_realm_snapshot
        and "com.intuit.quickbooks.payment" in (connection.scopes or "").split()
    ):
        raise SettlementDomainError(
            "quickbooks_payments_onboarding_incomplete",
            "QuickBooks Payments is not ready for this shop.",
        )
    await _refresh_connection_if_needed(db, connection)
    try:
        if attempt.provider_charge_id:
            charge = await get_quickbooks_charge(
                connection=connection,
                charge_id=attempt.provider_charge_id,
            )
        else:
            charge = await create_quickbooks_charge(
                connection=connection,
                token=payment_token,
                amount=money(attempt.provider_charge_amount),
                description=quickbooks_invoice_memo(
                    invoice,
                    tenant_name=tenant.name,
                ),
                # The provider idempotency identity belongs to the immutable
                # attempt, not a browser retry header.
                request_id=f"db048-attempt-{attempt.id}"[:255],
            )
    except QuickBooksPaymentError as exc:
        if exc.outcome_unknown:
            attempt.failure_code = "quickbooks_payment_outcome_unknown"
            await append_ledger_event(
                db,
                settlement=await db.get(InvoiceSettlement, attempt.settlement_id),
                attempt=attempt,
                event_type="provider_outcome_unknown",
                idempotency_key=f"qbp:{attempt.id}:outcome-unknown:v{attempt.version}",
                actor=actor,
                evidence={
                    "provider": "quickbooks_payments",
                    "retry_request_id": f"db048-attempt-{attempt.id}"[:255],
                },
            )
            await db.commit()
            raise SettlementDomainError(
                "card_provider_outcome_unknown",
                "QuickBooks has not confirmed whether this payment completed. Retry safely; do not create another payment.",
                status_code=503,
                retryable=True,
                current_version=attempt.version,
            ) from exc
        await fail_attempt(
            db,
            attempt_id=attempt.id,
            tenant_id=tenant.id,
            actor=actor,
            expected_attempt_version=attempt.version,
            failure_code="quickbooks_payment_rejected",
            idempotency_key=f"{idempotency_key}:provider-failed",
        )
        await db.commit()
        raise SettlementDomainError(
            "card_provider_error",
            "QuickBooks could not complete this payment.",
            status_code=402,
        ) from exc
    if money(charge.amount) != money(attempt.provider_charge_amount):
        attempt.provider_charge_id = charge.id
        attempt.failure_code = "provider_payment_mismatch"
        settlement = await db.get(InvoiceSettlement, attempt.settlement_id)
        existing_refund = await db.scalar(select(PaymentRefund).where(
            PaymentRefund.tenant_id == tenant.id,
            PaymentRefund.source_attempt_id == attempt.id,
            PaymentRefund.overpayment_id.is_(None),
            PaymentRefund.idempotency_key == f"qbp-mismatch:{attempt.id}:refund:v1",
        ))
        if is_successful_quickbooks_charge(charge) and existing_refund is None:
            # Intuit accepted money different from the immutable request. Do
            # not force it into invoice A/R. Keep the original reservation and
            # durably refund the complete provider charge with the historical
            # provider/configuration before releasing the attempt.
            mismatch_refund = PaymentRefund(
                tenant_id=tenant.id,
                invoice_id=invoice.id,
                source_attempt_id=attempt.id,
                overpayment_id=None,
                amount=money(charge.amount),
                reason="Provider captured an amount different from the authorized invoice attempt",
                destination_rail="card",
                mode="automatic",
                state="pending",
                actor_user_id=None,
                actor_name_snapshot="System",
                idempotency_key=f"qbp-mismatch:{attempt.id}:refund:v1",
                request_hash=hashlib.sha256(
                    f"qbp-mismatch:{attempt.id}:{money(charge.amount)}".encode()
                ).hexdigest(),
            )
            db.add(mismatch_refund)
            await db.flush()
            await append_ledger_event(
                db,
                settlement=settlement,
                attempt=attempt,
                event_type="provider_payment_mismatch",
                idempotency_key=f"qbp:{attempt.id}:amount-mismatch:{charge.id}",
                actor=actor,
                evidence={
                    "provider": "quickbooks_payments",
                    "refund_id": str(mismatch_refund.id),
                    "expected_amount": str(money(attempt.provider_charge_amount)),
                    "received_amount": str(money(charge.amount)),
                },
            )
            db.add(ProviderOutboxEvent(
                tenant_id=tenant.id,
                event_type="payment_refund.provider_submit",
                aggregate_type="payment_refund",
                aggregate_id=mismatch_refund.id,
                payload={
                    "refund_id": str(mismatch_refund.id),
                    "attempt_id": str(attempt.id),
                    "amount": str(money(charge.amount)),
                },
                idempotency_key=f"refund:{mismatch_refund.id}:quickbooks_payments:mismatch",
                status=ProviderOutboxStatus.PENDING.value,
                available_at=datetime.now(timezone.utc),
            ))
        await db.commit()
        raise SettlementDomainError(
            "provider_payment_mismatch",
            "QuickBooks returned an unexpected payment amount. The charge is being refunded before this invoice can accept another payment.",
            status_code=502,
            retryable=True,
        )
    if not is_successful_quickbooks_charge(charge):
        attempt.provider_charge_id = charge.id
        await db.commit()
        return None
    confirmed = await confirm_attempt(
        db,
        attempt_id=attempt.id,
        tenant=tenant,
        actor=actor,
        expected_attempt_version=attempt.version,
        idempotency_key=idempotency_key,
        received_principal=attempt.principal_amount,
        reference=charge_client_transaction_id(charge),
        provider_charge_id=charge.id,
    )
    await db.commit()
    return confirmed


@router.post("/attempts/{attempt_id}/quickbooks-charge", response_model=PaymentAttemptResponse)
async def charge_quickbooks_payment_attempt(
    attempt_id: UUID,
    body: QuickBooksAttemptCharge,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    key = _idempotency_key(idempotency_header)
    attempt = await db.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == attempt_id,
        InvoicePaymentAttempt.tenant_id == current_user.tenant_id,
    ))
    if not attempt:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    invoice, tenant, _customer_id = await invoice_for_principal(db, attempt.invoice_id, current_user)
    await charge_quickbooks_settlement_attempt(
        db,
        attempt=attempt,
        invoice=invoice,
        tenant=tenant,
        actor=current_user,
        payment_token=body.token,
        expected_attempt_version=body.expected_attempt_version,
        idempotency_key=key,
    )
    refreshed_attempt = await db.get(InvoicePaymentAttempt, attempt.id)
    settlement = await db.get(InvoiceSettlement, refreshed_attempt.settlement_id)
    audience = "customer" if current_user.role == UserRole.CUSTOMER else "staff"
    return await attempt_response(
        db,
        refreshed_attempt,
        settlement,
        tenant,
        audience=audience,
        current_user=current_user,
    )


@router.post("/attempts/{attempt_id}/confirm", response_model=PaymentAttemptResponse)
async def confirm_invoice_payment_attempt(
    attempt_id: UUID,
    body: PaymentAttemptConfirm,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _is_staff(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one()
    attempt = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == attempt_id,
        InvoicePaymentAttempt.tenant_id == tenant.id,
    ))).scalar_one_or_none()
    if not attempt:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if attempt.rail == "card":
        raise SettlementDomainError("provider_confirmation_required", "Card settlement requires verified provider confirmation.")
    result = await confirm_attempt(
        db, attempt_id=attempt_id, tenant=tenant, actor=current_user,
        expected_attempt_version=body.expected_attempt_version,
        idempotency_key=_idempotency_key(idempotency_header),
        received_principal=body.received_amount, reference=body.resolved_reference,
    )
    await db.commit()
    audience = "customer" if current_user.role == UserRole.CUSTOMER else "staff"
    return await attempt_response(
        db, result.attempt, result.settlement, tenant,
        audience=audience, current_user=current_user,
    )


@router.post("/attempts/{attempt_id}/fail", response_model=PaymentAttemptResponse)
async def fail_invoice_payment_attempt(
    attempt_id: UUID,
    body: PaymentAttemptFail,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _is_staff(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    attempt, settlement = await fail_attempt(
        db, attempt_id=attempt_id, tenant_id=current_user.tenant_id,
        actor=current_user, expected_attempt_version=body.expected_attempt_version,
        failure_code=body.failure_code,
        idempotency_key=_idempotency_key(idempotency_header),
    )
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one()
    await db.commit()
    audience = "customer" if current_user.role == UserRole.CUSTOMER else "staff"
    return await attempt_response(
        db, attempt, settlement, tenant,
        audience=audience, current_user=current_user,
    )


@router.post("/attempts/{attempt_id}/refunds")
async def create_payment_refund(
    attempt_id: UUID,
    body: PaymentRefundCreate,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    attempt = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == attempt_id,
        InvoicePaymentAttempt.tenant_id == current_user.tenant_id,
    ))).scalar_one_or_none()
    if not attempt:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    refund = await create_refund(
        db, attempt=attempt, tenant_id=current_user.tenant_id, actor=current_user,
        amount=body.amount, reason=body.reason,
        idempotency_key=_idempotency_key(idempotency_header),
    )
    await db.commit()
    return {"refund_id": str(refund.id), "state": refund.state, "amount": str(money(refund.amount))}


@router.post("/refunds/{refund_id}/confirm-manual")
async def confirm_manual_payment_refund(
    refund_id: UUID,
    body: ManualRefundConfirm,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    refund = await confirm_manual_refund(
        db, refund_id=refund_id, tenant_id=current_user.tenant_id,
        actor=current_user, reference=body.reference,
        idempotency_key=_idempotency_key(idempotency_header),
    )
    await db.commit()
    return {"refund_id": str(refund.id), "state": refund.state}


@router.post("/refunds/{refund_id}/retry")
async def retry_failed_payment_refund(
    refund_id: UUID,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    key = _idempotency_key(idempotency_header)
    refund = (await db.execute(select(PaymentRefund).where(
        PaymentRefund.id == refund_id,
        PaymentRefund.tenant_id == current_user.tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if not refund:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    settlement = (await db.execute(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == refund.invoice_id,
        InvoiceSettlement.tenant_id == current_user.tenant_id,
    ).with_for_update())).scalar_one()
    event_key = f"refund-retry:{key}"
    replay = (await db.execute(select(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.tenant_id == current_user.tenant_id,
        InvoicePaymentLedgerEvent.idempotency_key == event_key,
    ))).scalar_one_or_none()
    if replay:
        if replay.evidence_snapshot.get("refund_id") != str(refund_id):
            raise SettlementDomainError(
                "idempotency_key_reused",
                "The Idempotency-Key was already used with a different request.",
                status_code=409,
            )
        return {"refund_id": str(refund.id), "state": refund.state}
    if refund.mode != "automatic" or refund.state != "failed":
        raise SettlementDomainError(
            "refund_retry_not_available", "This refund is not retryable.", status_code=409,
        )
    attempt = (await db.execute(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == refund.source_attempt_id,
        InvoicePaymentAttempt.tenant_id == current_user.tenant_id,
        InvoicePaymentAttempt.provider.in_(["stripe_connect", "quickbooks_payments"]),
    ))).scalar_one_or_none()
    if not attempt:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    outbox = (await db.execute(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == current_user.tenant_id,
        ProviderOutboxEvent.event_type == "payment_refund.provider_submit",
        ProviderOutboxEvent.aggregate_id == refund.id,
    ).with_for_update())).scalar_one_or_none()
    if not outbox:
        raise SettlementDomainError(
            "refund_retry_not_available", "The durable refund operation is unavailable.", status_code=409,
        )
    refund.state = "pending"
    refund.last_error = None
    outbox.status = ProviderOutboxStatus.PENDING.value
    outbox.available_at = datetime.now(timezone.utc)
    outbox.locked_at = outbox.locked_until = None
    outbox.lock_token = None
    outbox.last_error = None
    overpayment = await db.get(PaymentOverpayment, refund.overpayment_id) if refund.overpayment_id else None
    if overpayment:
        overpayment.state = "refund_required"
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="refund_retry_requested",
        idempotency_key=event_key,
        actor=current_user,
        evidence={"refund_id": str(refund.id)},
    )
    await db.commit()
    return {"refund_id": str(refund.id), "state": refund.state}


@router.post("/overpayments/{overpayment_id}/credit-consent")
async def consent_to_store_credit(
    overpayment_id: UUID,
    body: CreditConsentCreate,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    overpayment = (await db.execute(select(PaymentOverpayment).where(PaymentOverpayment.id == overpayment_id))).scalar_one_or_none()
    if not overpayment:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if current_user.role == UserRole.CUSTOMER:
        if overpayment.tenant_id != current_user.tenant_id or overpayment.customer_id != current_user.customer_id:
            raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
        customer_id = current_user.customer_id
        if body.channel != "customer_portal":
            raise SettlementDomainError(
                "consent_channel_invalid",
                "Customer consent must be recorded through the customer portal.",
                status_code=422,
            )
        consent_channel = "customer_portal"
    elif _can_manage_money(current_user) and overpayment.tenant_id == current_user.tenant_id:
        customer_id = overpayment.customer_id
        if body.channel not in {"in_person", "phone"}:
            raise SettlementDomainError(
                "consent_channel_invalid",
                "Staff consent evidence must be recorded as in-person or phone.",
                status_code=422,
            )
        consent_channel = body.channel
    else:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    entry = await record_credit_consent(
        db, overpayment_id=overpayment_id, tenant_id=overpayment.tenant_id,
        actor=current_user, subject_customer_id=customer_id,
        channel=consent_channel, note=body.note,
        idempotency_key=_idempotency_key(idempotency_header),
    )
    await db.commit()
    return {"credit_id": str(entry.id), "state": "available", "amount": str(money(entry.amount))}


@router.post("/customer-credits/{credit_id}/applications")
async def apply_store_credit(
    credit_id: UUID,
    body: CreditApplicationCreate,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if current_user.role == UserRole.CUSTOMER:
        pass
    elif not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    invoice, tenant, customer_id = await invoice_for_principal(db, body.invoice_id, current_user)
    entry, settlement = await apply_customer_credit(
        db, credit_id=credit_id, invoice=invoice, tenant=tenant,
        customer_id=customer_id, amount=body.amount,
        expected_settlement_version=body.expected_settlement_version,
        actor=current_user, idempotency_key=_idempotency_key(idempotency_header),
    )
    await db.commit()
    audience = "customer" if current_user.role == UserRole.CUSTOMER else "staff"
    return {
        "application_id": str(entry.id),
        "settlement": (
            await settlement_summary(
                db, settlement, tenant, audience=audience, current_user=current_user,
            )
        ).model_dump(),
    }


async def _eligible_credit_rows(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    customer_id: UUID,
) -> list[EligibleCreditItem]:
    issued = (
        await db.execute(
            select(CustomerCreditEntry).where(
                CustomerCreditEntry.tenant_id == tenant_id,
                CustomerCreditEntry.customer_id == customer_id,
                CustomerCreditEntry.entry_type == "issued",
            ).order_by(CustomerCreditEntry.occurred_at, CustomerCreditEntry.id)
        )
    ).scalars().all()
    items: list[EligibleCreditItem] = []
    for origin in issued:
        used = (
            await db.execute(
                select(func.coalesce(func.sum(CustomerCreditEntry.amount), 0)).where(
                    CustomerCreditEntry.tenant_id == tenant_id,
                    CustomerCreditEntry.customer_id == customer_id,
                    CustomerCreditEntry.source_entry_id == origin.id,
                    CustomerCreditEntry.entry_type.in_(["applied", "refunded", "reversed"]),
                )
            )
        ).scalar_one()
        remaining = max(Decimal("0.00"), money(origin.amount) - money(used))
        if remaining > Decimal("0.00"):
            items.append(EligibleCreditItem(
                credit_id=origin.id,
                origin_overpayment_id=origin.origin_overpayment_id,
                origin_amount=money(origin.amount),
                remaining_amount=remaining,
                issued_at=origin.occurred_at,
                consent_channel=origin.consent_channel,
            ))
    return items


@router.get("/invoices/{invoice_id}/eligible-credits", response_model=list[EligibleCreditItem])
async def read_eligible_customer_credits(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if current_user.role != UserRole.CUSTOMER and not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    invoice, _tenant, customer_id = await invoice_for_principal(db, invoice_id, current_user)
    # Exact-invoice manager/customer authorization is established above. Guest
    # tokens and receptionists intentionally do not receive customer-account-
    # wide credit access.
    return await _eligible_credit_rows(
        db, tenant_id=invoice.tenant_id, customer_id=customer_id,
    )


@router.post("/invoices/{invoice_id}/early-release", response_model=InvoiceSettlementSummary)
async def authorize_invoice_early_release(
    invoice_id: UUID,
    body: EarlyReleaseOverride,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if body.invoice_id != invoice_id:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    invoice, tenant, _customer_id = await invoice_for_principal(db, invoice_id, current_user)
    # This mutation is part of the DB-048 financial-release contract.  Keep it
    # unavailable until both gates are on and the tenant backfill is verified;
    # otherwise an explicit call could create a settlement while the feature
    # is still intentionally dormant.
    await require_feature_ready(db, tenant)
    settlement = await authorize_early_release(
        db,
        invoice=invoice,
        tenant=tenant,
        actor=current_user,
        reason=body.reason,
        expected_settlement_version=body.expected_settlement_version,
        idempotency_key=_idempotency_key(idempotency_header),
    )
    await db.commit()
    return await settlement_summary(
        db, settlement, tenant, audience="staff", current_user=current_user,
    )


def _safe_csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


async def _credit_aging_rows(db: AsyncSession, tenant_id: UUID) -> list[CreditAgingItem]:
    issued = (await db.execute(
        select(CustomerCreditEntry, Customer)
        .join(Customer, Customer.id == CustomerCreditEntry.customer_id)
        .where(CustomerCreditEntry.tenant_id == tenant_id, CustomerCreditEntry.entry_type == "issued")
        .order_by(CustomerCreditEntry.occurred_at)
    )).all()
    rows: list[CreditAgingItem] = []
    now = datetime.now(timezone.utc)
    for entry, customer in issued:
        used = (await db.execute(select(func.coalesce(func.sum(CustomerCreditEntry.amount), 0)).where(
            CustomerCreditEntry.tenant_id == tenant_id,
            CustomerCreditEntry.source_entry_id == entry.id,
            CustomerCreditEntry.entry_type.in_(["applied", "refunded", "reversed"]),
        ))).scalar_one()
        remaining = max(Decimal("0.00"), money(entry.amount) - money(used))
        if remaining <= 0:
            continue
        last_contact = (await db.execute(
            select(CustomerCreditDueDiligenceEvent).where(
                CustomerCreditDueDiligenceEvent.tenant_id == tenant_id,
                CustomerCreditDueDiligenceEvent.credit_id == entry.id,
            ).order_by(
                CustomerCreditDueDiligenceEvent.occurred_at.desc(),
                CustomerCreditDueDiligenceEvent.id.desc(),
            ).limit(1)
        )).scalar_one_or_none()
        rows.append(CreditAgingItem(
            credit_id=entry.id, customer_id=entry.customer_id,
            customer_name=customer.company_name or f"{customer.first_name} {customer.last_name}".strip(),
            origin_amount=money(entry.amount), remaining_amount=remaining,
            issued_at=entry.occurred_at, age_days=max(0, (now - entry.occurred_at).days),
            consent_channel=entry.consent_channel, consent_note=entry.consent_note,
            last_contact_at=last_contact.occurred_at if last_contact else None,
            last_contact_channel=last_contact.channel if last_contact else None,
            last_contact_note=last_contact.note if last_contact else None,
            next_review_at=last_contact.next_review_at if last_contact else None,
            disposition="available",
        ))
    return rows


@router.post("/customer-credits/{credit_id}/due-diligence")
async def record_customer_credit_due_diligence(
    credit_id: UUID,
    body: CreditDueDiligenceCreate,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """Append tenant-scoped contact evidence without changing customer money."""
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    key = _idempotency_key(idempotency_header)
    credit = (await db.execute(select(CustomerCreditEntry).where(
        CustomerCreditEntry.id == credit_id,
        CustomerCreditEntry.tenant_id == current_user.tenant_id,
        CustomerCreditEntry.entry_type == "issued",
    ))).scalar_one_or_none()
    if not credit:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    request_hash = hashlib.sha256(json.dumps({
        "credit_id": str(credit_id),
        "channel": body.channel,
        "note": body.note.strip(),
        "next_review_at": body.next_review_at.isoformat() if body.next_review_at else None,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = (await db.execute(select(CustomerCreditDueDiligenceEvent).where(
        CustomerCreditDueDiligenceEvent.tenant_id == current_user.tenant_id,
        CustomerCreditDueDiligenceEvent.idempotency_key == key,
    ))).scalar_one_or_none()
    if existing:
        if existing.request_hash != request_hash:
            raise SettlementDomainError(
                "idempotency_conflict",
                "The Idempotency-Key was already used with a different request.",
                status_code=409,
            )
        return {
            "event_id": str(existing.id),
            "credit_id": str(existing.credit_id),
            "occurred_at": existing.occurred_at,
            "next_review_at": existing.next_review_at,
        }
    actor = identity_user(current_user)
    event = CustomerCreditDueDiligenceEvent(
        tenant_id=current_user.tenant_id,
        customer_id=credit.customer_id,
        credit_id=credit.id,
        actor_user_id=actor.id,
        actor_name_snapshot=(f"{actor.first_name} {actor.last_name}".strip() or "Shop manager")[:255],
        channel=body.channel,
        note=body.note.strip(),
        next_review_at=body.next_review_at,
        idempotency_key=key,
        request_hash=request_hash,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return {
        "event_id": str(event.id),
        "credit_id": str(event.credit_id),
        "occurred_at": event.occurred_at,
        "next_review_at": event.next_review_at,
    }


@router.get("/customer-credits/aging", response_model=list[CreditAgingItem])
async def customer_credit_aging(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    return await _credit_aging_rows(db, current_user.tenant_id)


@router.get("/customer-credits/aging/export.csv")
async def export_customer_credit_aging(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "credit_id", "customer_id", "customer_name", "origin_amount",
        "remaining_amount", "issued_at", "age_days", "consent_channel",
        "consent_note", "last_contact_at", "last_contact_channel",
        "last_contact_note", "next_review_at", "disposition",
    ])
    for row in await _credit_aging_rows(db, current_user.tenant_id):
        writer.writerow([_safe_csv_cell(value) for value in (
            row.credit_id, row.customer_id, row.customer_name, row.origin_amount,
            row.remaining_amount, row.issued_at.isoformat(), row.age_days,
            row.consent_channel, row.consent_note,
            row.last_contact_at.isoformat() if row.last_contact_at else None,
            row.last_contact_channel, row.last_contact_note,
            row.next_review_at.isoformat() if row.next_review_at else None,
            row.disposition,
        )])
    return Response(
        content=output.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customer-credit-aging.csv"},
    )


async def _config_read(db: AsyncSession, tenant: Tenant) -> CardProviderConfigurationRead:
    config = await load_active_configuration(db, tenant.id)
    readiness = await provider_readiness(db, tenant, config)
    mapping_keys = (
        "stripe_clearing_account", "qbp_clearing_account", "check_deposit_account",
        "zelle_ach_account", "card_fee_income_account", "processor_fee_expense_account",
        "sales_tax_liability_account", "checking_account",
    )
    return CardProviderConfigurationRead(
        selected_provider=config.selected_provider if config else None,
        readiness_state=readiness.status, version=config.version if config else None,
        effective_at=config.effective_at if config else None,
        writer_strategy=config.writer_strategy if config else None,
        provider_account_snapshot=config.provider_account_snapshot if config else None,
        qbo_realm_snapshot=config.qbo_realm_snapshot if config else None,
        mappings={key: getattr(config, key) if config else None for key in mapping_keys},
    )


async def _readiness_response(
    db: AsyncSession,
    tenant: Tenant,
    current_user: CurrentUser,
    config_override: Optional[TenantPaymentProviderConfiguration] = None,
) -> CardProviderReadiness:
    readiness = await provider_readiness(db, tenant, config_override)
    config = readiness.configuration
    mappings = _configuration_mapping_values(config)
    feature_enabled = readiness.split_payment_global_gate and readiness.split_payment_tenant_gate
    selected_status = _public_provider_status(readiness)
    stripe_approved = bool(settings.STRIPE_CONNECT_INVOICE_PAYMENTS_APPROVED)
    stripe_tenant_ready = bool(
        stripe_approved and tenant.stripe_account_id and tenant.stripe_onboarding_complete
    )
    qbo_connection = await db.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant.id,
        QuickBooksConnection.status == "connected",
        QuickBooksConnection.deleted_at.is_(None),
    ))
    qbp_approved = bool(settings.QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED)
    qbp_tenant_ready = bool(
        qbo_connection
        and qbo_connection.realm_id
        and "com.intuit.quickbooks.payment" in (qbo_connection.scopes or "").split()
    )
    if not stripe_approved:
        stripe_status = "not_configured"
    elif not stripe_tenant_ready:
        stripe_status = "onboarding_incomplete"
    elif not readiness.qbo_accounting_ready:
        stripe_status = "accounting_unavailable"
    elif not all(mappings.get(key) for key in (
        "stripe_clearing_account", "check_deposit_account", "zelle_ach_account",
        "card_fee_income_account", "processor_fee_expense_account",
        "sales_tax_liability_account", "checking_account",
    )):
        stripe_status = "accounting_mapping_incomplete"
    else:
        stripe_status = "ready"
    allowed = SettlementAllowedActions(configure_provider=_can_manage_money(current_user))
    return CardProviderReadiness(
        feature_enabled=feature_enabled,
        selected_provider=readiness.provider,
        selected_provider_status=selected_status,
        configuration_version=config.version if config else None,
        stripe_connect=ProviderOptionReadiness(
            approved=stripe_approved,
            tenant_ready=stripe_tenant_ready,
            status=stripe_status,
            message=None if stripe_status == "ready" else "Stripe requires approved onboarding and complete accounting mappings.",
        ),
        quickbooks_payments=ProviderOptionReadiness(
            approved=qbp_approved,
            tenant_ready=qbp_tenant_ready,
            status=(
                "unavailable_external_approval"
                if not qbp_approved
                else "onboarding_incomplete"
                if not qbp_tenant_ready
                else "accounting_unavailable"
                if not readiness.qbo_accounting_ready
                else "accounting_mapping_incomplete"
                if not all(mappings.get(key) for key in (
                    "qbp_clearing_account", "check_deposit_account", "zelle_ach_account",
                    "card_fee_income_account", "processor_fee_expense_account",
                    "sales_tax_liability_account", "checking_account",
                ))
                else "ready"
            ),
            message=(
                None
                if qbp_approved and qbp_tenant_ready
                else "QuickBooks Payments requires the platform gate and a connected payment scope."
            ),
        ),
        accounting_ready=readiness.qbo_accounting_ready and readiness.mappings_ready,
        accounting_message=(
            None
            if readiness.qbo_accounting_ready and readiness.mappings_ready
            else "Connect QuickBooks Accounting and complete the required account mappings."
        ),
        writer_strategy=config.writer_strategy if config else None,
        qbo_realm_snapshot=config.qbo_realm_snapshot if config else None,
        mappings=mappings,
        allowed_actions=allowed,
        provider=readiness.provider,
        status=readiness.status,
        split_payment_global_gate=readiness.split_payment_global_gate,
        split_payment_tenant_gate=readiness.split_payment_tenant_gate,
        provider_global_gate=readiness.provider_global_gate,
        provider_onboarding_ready=readiness.provider_onboarding_ready,
        qbo_accounting_ready=readiness.qbo_accounting_ready,
        mappings_ready=readiness.mappings_ready,
        reasons=list(readiness.reasons),
    )


def _configuration_mapping_values(
    config: Optional[TenantPaymentProviderConfiguration],
) -> dict[str, Optional[str]]:
    keys = (
        "stripe_clearing_account", "qbp_clearing_account", "check_deposit_account",
        "zelle_ach_account", "card_fee_income_account", "processor_fee_expense_account",
        "sales_tax_liability_account", "checking_account",
    )
    return {key: getattr(config, key) if config else None for key in keys}


@router.get("/settings/card-provider", response_model=CardProviderConfigurationRead)
async def read_card_provider_configuration(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _is_staff(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one()
    return await _config_read(db, tenant)


@router.put("/settings/card-provider", response_model=CardProviderReadiness)
async def update_card_provider_configuration(
    body: CardProviderConfigurationUpdate,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    idempotency_key = _idempotency_key(idempotency_header)
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one()
    request_hash = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    replay = (await db.execute(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant.id,
        TenantPaymentProviderConfiguration.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if replay:
        if replay.request_hash != request_hash:
            raise SettlementDomainError(
                "idempotency_key_reused",
                "The Idempotency-Key was already used with a different request.",
                status_code=409,
            )
        return await _readiness_response(db, tenant, current_user, replay)
    current = await load_active_configuration(db, tenant.id, lock=True)
    current_version = current.version if current else 0
    if body.expected_version is not None and body.expected_version != current_version:
        raise SettlementDomainError("stale_provider_configuration", "The provider configuration changed.", current_version=current_version)
    selected_provider = body.resolved_provider
    if selected_provider == "quickbooks_payments":
        if not settings.QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED:
            raise SettlementDomainError(
                "quickbooks_payments_platform_approval_missing",
                "QuickBooks Payments is not approved for this environment.",
            )
        qbp_connection = await db.scalar(select(QuickBooksConnection).where(
            QuickBooksConnection.tenant_id == tenant.id,
            QuickBooksConnection.status == "connected",
            QuickBooksConnection.deleted_at.is_(None),
        ))
        if not (
            qbp_connection
            and qbp_connection.realm_id
            and "com.intuit.quickbooks.payment" in (qbp_connection.scopes or "").split()
        ):
            raise SettlementDomainError(
                "quickbooks_payments_onboarding_incomplete",
                "Connect a QuickBooks company with Payments enabled before selecting this provider.",
            )
    mapping_names = (
        "stripe_clearing_account", "qbp_clearing_account", "check_deposit_account",
        "zelle_ach_account", "card_fee_income_account", "processor_fee_expense_account",
        "sales_tax_liability_account", "checking_account",
    )
    requested_mappings = {
        name: getattr(body, name) if getattr(body, name) is not None else (getattr(current, name) if current else None)
        for name in mapping_names
    }
    writer_strategy = body.writer_strategy or (current.writer_strategy if current else "dieselbridge")
    if writer_strategy != "dieselbridge":
        raise SettlementDomainError(
            "provider_writer_invalid",
            "Invoice payment accounting must be written by DieselBridge until a verified native importer is available.",
            status_code=422,
        )
    if current:
        current.is_active = False
        current.deactivated_at = datetime.now(timezone.utc)
        await db.flush()
    actor = identity_user(current_user)
    qbo_connection = await db.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant.id,
        QuickBooksConnection.status == "connected",
        QuickBooksConnection.deleted_at.is_(None),
    ))
    config = TenantPaymentProviderConfiguration(
        tenant_id=tenant.id, version=current_version + 1,
        selected_provider=selected_provider,
        readiness_state="pending_readiness_check", is_active=True,
        actor_user_id=actor.id,
        actor_name_snapshot=f"{actor.first_name} {actor.last_name}".strip(),
        # QBP settlement rows are partitioned by the connected Intuit company
        # realm. Freeze that same provider identity on the configuration so
        # attempts and later Deposit/Payment/Purchase imports share one
        # database-enforced identity boundary.
        provider_account_snapshot=(
            tenant.stripe_account_id
            if selected_provider == "stripe_connect"
            else str(qbo_connection.realm_id)
            if qbo_connection and qbo_connection.realm_id
            else None
        ),
        qbo_realm_snapshot=qbo_connection.realm_id if qbo_connection else None,
        writer_strategy=writer_strategy,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        **requested_mappings,
    )
    # Configuration rows are immutable snapshots once inserted. Resolve the
    # initial readiness value before the INSERT rather than updating history
    # in place after a flush.
    config.readiness_state = (await provider_readiness(db, tenant, config)).status
    db.add(config)
    await db.commit()
    return await _readiness_response(db, tenant, current_user)


@router.get("/settings/card-provider/readiness", response_model=CardProviderReadiness)
async def read_card_provider_readiness(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _is_staff(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one()
    return await _readiness_response(db, tenant, current_user)


@router.get("/invoices/{invoice_id}/accounting-reconciliation", response_model=AccountingReconciliationRead)
async def read_accounting_reconciliation(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    invoice, _tenant, _customer_id = await invoice_for_principal(db, invoice_id, current_user)
    if not _is_staff(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    links = (await db.execute(select(PaymentAccountingLink).where(
        PaymentAccountingLink.tenant_id == invoice.tenant_id,
        PaymentAccountingLink.invoice_id == invoice.id,
    ))).scalars().all()
    pending = sum(link.sync_state in {"pending", "processing"} for link in links)
    failed = sum(link.sync_state in {"failed", "dead"} for link in links)
    synced = sum(link.sync_state == "synced" for link in links)
    state = "failed" if failed else "pending" if pending else "synced" if links else "not_required"
    return AccountingReconciliationRead(
        invoice_id=invoice.id, state=state, pending_operations=pending,
        failed_operations=failed, synced_operations=synced,
        links=[{"id": str(link.id), "type": link.financial_object_type,
                "state": link.sync_state, "provider_object_id": link.provider_object_id,
                "error": link.sync_error} for link in links],
    )


@router.get("/payout-reconciliations")
async def read_payout_reconciliations(
    limit: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    rows = (await db.execute(select(ProviderSettlementBatch).where(
        ProviderSettlementBatch.tenant_id == current_user.tenant_id,
    ).order_by(ProviderSettlementBatch.created_at.desc()).limit(limit))).scalars().all()
    outbox_rows = (await db.execute(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == current_user.tenant_id,
        ProviderOutboxEvent.event_type == "stripe_payout.reconcile",
    ).order_by(ProviderOutboxEvent.created_at.desc()))).scalars().all()
    operations = {
        (
            str((event.payload or {}).get("provider_account_id") or ""),
            str((event.payload or {}).get("payout_id") or ""),
        ): event
        for event in outbox_rows
    }
    batch_ids = [row.id for row in rows]
    payout_entries = (await db.execute(select(ProviderSettlementEntry).where(
        ProviderSettlementEntry.tenant_id == current_user.tenant_id,
        ProviderSettlementEntry.batch_id.in_(batch_ids),
    ))).scalars().all() if batch_ids else []
    partitions_by_batch: dict[UUID, dict[tuple[int, str, str, str], int]] = {}
    fee_purchase_ids_by_batch: dict[UUID, list[str]] = {}
    for entry in payout_entries:
        key = (
            entry.provider_configuration_version,
            entry.qbo_realm_snapshot,
            entry.owning_writer,
            entry.account_mapping_hash,
        )
        partitions = partitions_by_batch.setdefault(entry.batch_id, {})
        partitions[key] = partitions.get(key, 0) + 1
        if entry.entry_type == "qbp_fee_purchase":
            fee_purchase_ids_by_batch.setdefault(entry.batch_id, []).append(
                entry.provider_entry_id.removeprefix("fee:")
            )
    return [{
        "provider": row.provider,
        "payout_id": row.provider_batch_id,
        "provider_account_id": row.provider_account_id,
        "qbo_realm_snapshot": row.qbo_realm_snapshot,
        "entry_manifest_hash": row.entry_manifest_hash,
        "configuration_partitions": [
            {
                "provider_configuration_version": key[0],
                "qbo_realm_snapshot": key[1],
                "owning_writer": key[2],
                "account_mapping_hash": key[3],
                "entry_count": entry_count,
            }
            for key, entry_count in sorted(
                partitions_by_batch.get(row.id, {}).items(),
                key=lambda item: item[0],
            )
        ],
        "gross_receipts": str(money(row.gross_receipts)),
        "customer_card_fees": str(money(row.customer_card_fees)),
        "card_fee_tax": str(money(row.card_fee_tax)),
        "processor_fees": str(money(row.processor_fees)),
        "net_payout": str(money(row.net_payout)),
        "state": row.reconciliation_state,
        "mismatch_reason": row.mismatch_reason,
        "qbo_deposit_id": row.qbo_deposit_id,
        "qbo_fee_purchase_ids": sorted(
            fee_purchase_ids_by_batch.get(row.id, [])
        ),
        "settled_at": row.settled_at,
        "operation_id": (
            str(operation.id)
            if (operation := operations.get(
                (row.provider_account_id, row.provider_batch_id)
            )) else None
        ),
        "operation_state": operation.status if operation else None,
        "retryable": bool(
            row.provider == "stripe_connect"
            and operation
            and operation.status == ProviderOutboxStatus.DEAD.value
            and row.reconciliation_state == "accounting_failed"
        ),
    } for row in rows]


@router.post(
    "/payout-reconciliations/{operation_id}/retry",
    response_model=AccountingRetryResponse,
)
async def retry_payout_reconciliation(
    operation_id: UUID,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    idempotency_key = _idempotency_key(idempotency_header)
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    audit_key = f"stripe-payout-retry:{idempotency_key}"
    replay = await db.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == current_user.tenant_id,
        ProviderOutboxEvent.event_type == "stripe_payout.retry_requested",
        ProviderOutboxEvent.idempotency_key == audit_key,
    ))
    if replay:
        if str((replay.payload or {}).get("operation_id") or "") != str(operation_id):
            raise SettlementDomainError(
                "idempotency_key_reused",
                "The Idempotency-Key was already used with a different request.",
                status_code=409,
            )
        target = await db.get(ProviderOutboxEvent, operation_id)
        return AccountingRetryResponse(
            operation_id=operation_id,
            state=target.status if target else ProviderOutboxStatus.PENDING.value,
        )
    event = await db.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.id == operation_id,
        ProviderOutboxEvent.tenant_id == current_user.tenant_id,
        ProviderOutboxEvent.event_type == "stripe_payout.reconcile",
    ).with_for_update())
    if not event:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    payload = event.payload or {}
    batch = await db.scalar(select(ProviderSettlementBatch).where(
        ProviderSettlementBatch.tenant_id == current_user.tenant_id,
        ProviderSettlementBatch.provider == "stripe_connect",
        ProviderSettlementBatch.provider_account_id
        == str(payload.get("provider_account_id") or ""),
        ProviderSettlementBatch.provider_batch_id
        == str(payload.get("payout_id") or ""),
    ).with_for_update())
    if (
        event.status != ProviderOutboxStatus.DEAD.value
        or not batch
        or batch.reconciliation_state != "accounting_failed"
    ):
        raise SettlementDomainError(
            "accounting_retry_not_available",
            "This payout accounting operation is not retryable.",
        )
    event.status = ProviderOutboxStatus.PENDING.value
    event.available_at = datetime.now(timezone.utc)
    event.locked_at = event.locked_until = None
    event.lock_token = None
    event.last_error = None
    event.completed_at = None
    batch.reconciliation_state = "matched"
    batch.mismatch_reason = None
    db.add(ProviderOutboxEvent(
        tenant_id=current_user.tenant_id,
        event_type="stripe_payout.retry_requested",
        aggregate_type="provider_outbox_event",
        aggregate_id=event.id,
        payload={"operation_id": str(event.id), "payout_id": batch.provider_batch_id},
        idempotency_key=audit_key,
        status=ProviderOutboxStatus.SUCCEEDED.value,
        available_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    return AccountingRetryResponse(operation_id=event.id, state=event.status)


@router.post("/accounting-operations/{operation_id}/retry", response_model=AccountingRetryResponse)
async def retry_accounting_operation(
    operation_id: UUID,
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    idempotency_key = _idempotency_key(idempotency_header)
    if not _can_manage_money(current_user):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    link = (await db.execute(select(PaymentAccountingLink).where(
        PaymentAccountingLink.id == operation_id,
        PaymentAccountingLink.tenant_id == current_user.tenant_id,
    ))).scalar_one_or_none()
    if not link:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    settlement = (await db.execute(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == current_user.tenant_id,
        InvoiceSettlement.invoice_id == link.invoice_id,
    ).with_for_update())).scalar_one_or_none()
    if not settlement:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    audit_key = f"accounting-retry:{idempotency_key}"
    replay = (await db.execute(select(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.tenant_id == current_user.tenant_id,
        InvoicePaymentLedgerEvent.idempotency_key == audit_key,
    ))).scalar_one_or_none()
    if replay:
        if replay.evidence_snapshot.get("operation_id") != str(operation_id):
            raise SettlementDomainError(
                "idempotency_key_reused",
                "The Idempotency-Key was already used with a different request.",
                status_code=409,
            )
        return AccountingRetryResponse(operation_id=link.id, state=link.sync_state)
    link = (await db.execute(select(PaymentAccountingLink).where(
        PaymentAccountingLink.id == operation_id,
        PaymentAccountingLink.tenant_id == current_user.tenant_id,
    ).with_for_update())).scalar_one()
    if link.sync_state not in {"failed", "dead"}:
        raise SettlementDomainError("accounting_retry_not_available", "This accounting operation is not retryable.")
    outbox = (await db.execute(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == current_user.tenant_id,
        ProviderOutboxEvent.aggregate_id == link.financial_object_id,
        ProviderOutboxEvent.event_type.in_([
            "invoice_payment.accounting_sync", "customer_credit.accounting_sync",
            "invoice_refund.accounting_sync", "payment_reversal.accounting_sync",
            "payment_dispute.accounting_sync",
            "payment_dispute_recovery.accounting_sync",
        ]),
    ).with_for_update())).scalar_one_or_none()
    if not outbox:
        raise SettlementDomainError("accounting_operation_missing", "The durable accounting operation is unavailable.")
    outbox.status = ProviderOutboxStatus.PENDING.value
    outbox.available_at = datetime.now(timezone.utc)
    outbox.locked_at = outbox.locked_until = None
    outbox.lock_token = None
    outbox.last_error = None
    link.sync_state = "pending"
    link.sync_error = None
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=(await db.get(InvoicePaymentAttempt, link.attempt_id)) if link.attempt_id else None,
        event_type="accounting_retry_requested",
        idempotency_key=audit_key,
        actor=current_user,
        evidence={"operation_id": str(operation_id)},
    )
    await db.commit()
    return AccountingRetryResponse(operation_id=link.id, state=link.sync_state)
