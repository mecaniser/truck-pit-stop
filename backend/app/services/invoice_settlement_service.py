"""Transactional DB-048 repair-invoice settlement domain service.

All mutation entry points lock the settlement projection, transition one
durable attempt, append immutable evidence, and enqueue accounting/provider
work in the caller's transaction.  Provider network I/O belongs outside this
module; provider callbacks resolve the snapshotted attempt before calling a
transition here.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.quickbooks_payment_gate import quickbooks_payments_enabled_for_tenant
from app.core.dependencies import CurrentUser, identity_user, user_has_permission
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
    PaymentRefund,
    TenantPaymentProviderConfiguration,
)
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.services.paid_invoice_webhook_service import enqueue_paid_invoice_webhook
from app.services.payment_number_service import allocate_next_payment_number


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
ZELLE_RESERVATION_HOURS = 24
CARD_RESERVATION_MINUTES = 30
ACCOUNTING_EVENT = "invoice_payment.accounting_sync"


class SettlementDomainError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        retryable: bool = False,
        current_version: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.current_version = current_version


@dataclass(frozen=True)
class ProviderReadiness:
    provider: Optional[str]
    status: str
    split_payment_global_gate: bool
    split_payment_tenant_gate: bool
    provider_global_gate: bool
    provider_onboarding_ready: bool
    qbo_accounting_ready: bool
    mappings_ready: bool
    reasons: tuple[str, ...]
    configuration: Optional[TenantPaymentProviderConfiguration] = None


@dataclass(frozen=True)
class AttemptCreation:
    attempt: InvoicePaymentAttempt
    settlement: InvoiceSettlement
    replayed: bool = False


@dataclass(frozen=True)
class AttemptConfirmation:
    attempt: InvoicePaymentAttempt
    settlement: InvoiceSettlement
    payment: Optional[Payment]
    overpayment: Optional[PaymentOverpayment]
    refund: Optional[PaymentRefund]
    paid_transition: bool
    replayed: bool = False


def money(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def current_zelle_attempt_matches(
    *,
    invoice: Invoice,
    settlement: InvoiceSettlement,
    attempt: InvoicePaymentAttempt,
) -> bool:
    """Bind the mutable legacy Zelle display fields to one immutable attempt.

    A historical attempt on the same invoice must never make a later legacy
    submission look reconciled. Compatibility adapters snapshot the exact
    submission timestamp into attempt evidence and onto the Invoice in the
    same transaction; backfill attempts do the same for legacy rows.
    """
    submitted_at = invoice.zelle_pending_submitted_at
    marker = (attempt.manual_evidence or {}).get("compatibility_submitted_at")
    if submitted_at is None or not marker:
        return False
    try:
        marker_at = datetime.fromisoformat(str(marker).replace("Z", "+00:00"))
    except ValueError:
        return False
    if marker_at.tzinfo is None:
        marker_at = marker_at.replace(tzinfo=timezone.utc)
    normalized_submitted_at = submitted_at
    if normalized_submitted_at.tzinfo is None:
        normalized_submitted_at = normalized_submitted_at.replace(tzinfo=timezone.utc)
    return bool(
        attempt.tenant_id == invoice.tenant_id == settlement.tenant_id
        and attempt.invoice_id == invoice.id == settlement.invoice_id
        and attempt.settlement_id == settlement.id
        and attempt.customer_id == settlement.customer_id
        and attempt.rail == "zelle"
        and attempt.state in {"pending", "expired"}
        and attempt.deleted_at is None
        and marker_at.astimezone(timezone.utc)
        == normalized_submitted_at.astimezone(timezone.utc)
    )


def _actor_snapshot(actor: Optional[CurrentUser], *, fallback: str = "System") -> tuple[Optional[UUID], str, Optional[str]]:
    if actor is None:
        return None, fallback, None
    user = identity_user(actor)
    name = f"{user.first_name} {user.last_name}".strip() or fallback
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return user.id, name[:255], role[:64]


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def invoice_money_snapshot(invoice: Invoice) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Return principal, max card fee, fee tax, sales-tax rate, fee rate.

    Existing invoice totals include the maximum card surcharge.  Separate its
    proportional tax without reconstructing invoice lines or changing the
    authoritative checkout snapshot.
    """
    base = money(invoice.subtotal) + money(invoice.shop_supplies_amount)
    fee = money(invoice.service_fee_amount)
    tax = money(invoice.tax_amount)
    taxable = base + fee
    tax_rate = (tax / taxable) if taxable > ZERO else Decimal("0")
    fee_tax = money(fee * tax_rate)
    principal = max(ZERO, money(invoice.total_amount) - fee - fee_tax)
    fee_rate = (fee / principal * Decimal("100")) if principal > ZERO else Decimal("0")
    return principal, fee, fee_tax, tax_rate * Decimal("100"), fee_rate


def settlement_state(settlement: InvoiceSettlement) -> str:
    confirmed = money(settlement.confirmed_principal)
    pending = money(settlement.active_pending_principal)
    total = money(settlement.principal_total)
    unresolved = money(settlement.unapplied_credit) + money(settlement.refund_pending)
    if confirmed >= total and unresolved > ZERO:
        return "overpayment_resolution"
    if confirmed >= total:
        return "paid"
    if confirmed > ZERO and pending > ZERO:
        return "partially_paid_pending"
    if confirmed > ZERO:
        return "partially_paid"
    if pending > ZERO:
        return "payment_pending"
    return "unpaid"


def allocatable_balance(settlement: InvoiceSettlement) -> Decimal:
    return max(
        ZERO,
        money(settlement.principal_total)
        - money(settlement.confirmed_principal)
        - money(settlement.active_pending_principal),
    )


async def load_active_configuration(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    lock: bool = False,
) -> Optional[TenantPaymentProviderConfiguration]:
    query = select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant_id,
        TenantPaymentProviderConfiguration.is_active.is_(True),
        TenantPaymentProviderConfiguration.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


def _configuration_mappings(config: Optional[TenantPaymentProviderConfiguration]) -> dict[str, Optional[str]]:
    if config is None:
        return {}
    return {
        "stripe_clearing_account": config.stripe_clearing_account,
        "qbp_clearing_account": config.qbp_clearing_account,
        "check_deposit_account": config.check_deposit_account,
        "zelle_ach_account": config.zelle_ach_account,
        "card_fee_income_account": config.card_fee_income_account,
        "qbo_card_fee_item_id": getattr(config, "qbo_card_fee_item_id", None),
        "qbo_card_fee_tax_code_id": getattr(config, "qbo_card_fee_tax_code_id", None),
        "processor_fee_expense_account": config.processor_fee_expense_account,
        "sales_tax_liability_account": config.sales_tax_liability_account,
        "checking_account": config.checking_account,
    }


async def bind_settlement_accounting_realm(
    db: AsyncSession,
    *,
    settlement: InvoiceSettlement,
    config: TenantPaymentProviderConfiguration,
) -> None:
    """Freeze one QBO realm per invoice before its first durable attempt.

    Configuration versions may advance while an invoice is open, but every
    version used by that invoice must point to the same accounting company.
    Historical attempts and accounting links remain authoritative even if the
    tenant later reconnects QuickBooks or changes its active configuration.
    """
    realm = (config.qbo_realm_snapshot or "").strip()
    if not realm:
        raise SettlementDomainError(
            "quickbooks_realm_snapshot_missing",
            "QuickBooks accounting is not ready for invoice payments.",
        )
    prior_attempt_realms = set((await db.scalars(
        select(TenantPaymentProviderConfiguration.qbo_realm_snapshot)
        .join(
            InvoicePaymentAttempt,
            and_(
                InvoicePaymentAttempt.tenant_id
                == TenantPaymentProviderConfiguration.tenant_id,
                InvoicePaymentAttempt.provider_configuration_version
                == TenantPaymentProviderConfiguration.version,
            ),
        )
        .where(
            InvoicePaymentAttempt.tenant_id == settlement.tenant_id,
            InvoicePaymentAttempt.invoice_id == settlement.invoice_id,
            InvoicePaymentAttempt.deleted_at.is_(None),
            TenantPaymentProviderConfiguration.deleted_at.is_(None),
            TenantPaymentProviderConfiguration.qbo_realm_snapshot.is_not(None),
        )
    )).all())
    prior_link_realms = set((await db.scalars(
        select(PaymentAccountingLink.qbo_realm_snapshot).where(
            PaymentAccountingLink.tenant_id == settlement.tenant_id,
            PaymentAccountingLink.invoice_id == settlement.invoice_id,
            PaymentAccountingLink.deleted_at.is_(None),
            PaymentAccountingLink.qbo_realm_snapshot.is_not(None),
        )
    )).all())
    frozen_realms = {
        value.strip() for value in prior_attempt_realms | prior_link_realms
        if value and value.strip()
    }
    settlement_realm = (
        (settlement.qbo_realm_snapshot or "").strip()
        if hasattr(settlement, "qbo_realm_snapshot")
        else ""
    )
    if settlement_realm:
        frozen_realms.add(settlement_realm)
    if frozen_realms and frozen_realms != {realm}:
        raise SettlementDomainError(
            "invoice_accounting_realm_mismatch",
            "This invoice is bound to a different QuickBooks company.",
            status_code=409,
        )
    settlement.qbo_realm_snapshot = realm
    if settlement.initial_provider_configuration_version is None:
        settlement.initial_provider_configuration_version = config.version


async def provider_readiness(
    db: AsyncSession,
    tenant: Tenant,
    config: Optional[TenantPaymentProviderConfiguration] = None,
    *, invoice_id: Optional[UUID] = None,
    lock_ancestry: bool = False,
) -> ProviderReadiness:
    """Settings use tenant-wide reconciliation; checkout scopes it to its invoice.

    Scoping never relaxes provider or verified-backfill gates and does not
    initialize missing settlements or reinterpret legacy payments.
    """
    config = config or await load_active_configuration(db, tenant.id)
    provider = config.selected_provider if config else None
    global_gate = bool(settings.INVOICE_SPLIT_PAYMENTS_ENABLED)
    tenant_gate = bool(tenant.invoice_split_payments_enabled)
    provider_gate = False
    onboarding = False
    reasons: list[str] = []
    scope_ids: list[UUID] = []
    ancestry_reasons: list[str] = []
    current_id = invoice_id
    while current_id is not None:
        if current_id in scope_ids:
            ancestry_reasons.append("invoice_settlement_ancestry_requires_review")
            break
        node = await db.scalar(select(Invoice).where(Invoice.id == current_id,
            Invoice.tenant_id == tenant.id))
        if node is None or node.deleted_at is not None:
            ancestry_reasons.append("invoice_settlement_ancestry_requires_review")
            break
        if lock_ancestry:
            from app.services.invoice_accounting_policy import locked_policy
            await locked_policy(db, node)
        # Column-only refresh preserves eager relationships used by subsequent
        # invoice actions (a full populate_existing would expire them).
        await db.refresh(node, attribute_names=[column.name for column in Invoice.__table__.columns])
        if node.deleted_at is not None or node.tenant_id != tenant.id:
            ancestry_reasons.append("invoice_settlement_ancestry_requires_review")
            break
        coherent_order = await db.scalar(select(RepairOrder.id).join(Customer,
            Customer.id == RepairOrder.customer_id).where(RepairOrder.id == node.repair_order_id,
            RepairOrder.tenant_id == tenant.id, Customer.tenant_id == tenant.id))
        if coherent_order is None:
            ancestry_reasons.append("invoice_settlement_ancestry_requires_review")
            break
        scope_ids.append(current_id)
        if current_id != invoice_id:
            # A replacement may not collect against any predecessor money,
            # even when that money was reconciled or used a legacy cash rail.
            parent_payment = await db.scalar(select(Payment.id).where(
                Payment.tenant_id == tenant.id, Payment.invoice_id == current_id,
                Payment.amount > ZERO).limit(1))
            parent_attempt = await db.scalar(select(InvoicePaymentAttempt.id).where(
                InvoicePaymentAttempt.tenant_id == tenant.id, InvoicePaymentAttempt.invoice_id == current_id,
                or_(InvoicePaymentAttempt.state == "pending", InvoicePaymentAttempt.received_amount > ZERO,
                    InvoicePaymentAttempt.provider_charge_id.is_not(None),
                    InvoicePaymentAttempt.provider_intent_id.is_not(None))).limit(1))
            parent_balance = await db.scalar(select(InvoiceSettlement.id).where(
                InvoiceSettlement.tenant_id == tenant.id, InvoiceSettlement.invoice_id == current_id,
                or_(InvoiceSettlement.confirmed_principal > ZERO, InvoiceSettlement.active_pending_principal > ZERO,
                    InvoiceSettlement.unapplied_credit > ZERO, InvoiceSettlement.refund_pending > ZERO)).limit(1))
            parent_pending = await db.scalar(select(InvoicePaymentAttempt.id).where(
                InvoicePaymentAttempt.tenant_id == tenant.id, InvoicePaymentAttempt.invoice_id == current_id,
                InvoicePaymentAttempt.state == "pending").limit(1))
            parent_reservation = await db.scalar(select(InvoiceSettlement.id).where(
                InvoiceSettlement.tenant_id == tenant.id, InvoiceSettlement.invoice_id == current_id,
                InvoiceSettlement.active_pending_principal > ZERO).limit(1))
            if parent_pending or parent_reservation or node.zelle_pending_submitted_at:
                ancestry_reasons.append("previous_invoice_payment_pending")
            if parent_payment or parent_attempt or parent_balance or node.zelle_pending_submitted_at:
                ancestry_reasons.append("previous_invoice_payment_requires_review")
        current_id = node.supersedes_invoice_id

    qbo = (
        await db.execute(
            select(QuickBooksConnection).where(
                QuickBooksConnection.tenant_id == tenant.id,
                QuickBooksConnection.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    qbo_connection_ready = bool(qbo and qbo.status == "connected" and qbo.realm_id)
    qbp_scope_ready = bool(
        qbo_connection_ready
        and "com.intuit.quickbooks.payment" in (qbo.scopes or "").split()
    )

    if not global_gate:
        reasons.append("split_payment_global_gate_disabled")
    if not tenant_gate:
        reasons.append("split_payment_tenant_gate_disabled")
    if config is None:
        reasons.append("provider_configuration_missing")
    elif provider == "stripe_connect":
        provider_gate = bool(settings.STRIPE_CONNECT_INVOICE_PAYMENTS_APPROVED)
        onboarding = bool(tenant.stripe_account_id and tenant.stripe_onboarding_complete)
        if not provider_gate:
            reasons.append("stripe_connect_platform_approval_missing")
        if not onboarding:
            reasons.append("stripe_connect_onboarding_incomplete")
    elif provider == "quickbooks_payments":
        provider_gate = quickbooks_payments_enabled_for_tenant(tenant.id)
        qbp_provider_identity_ready = bool(
            config
            and qbo
            and qbo.realm_id
            and config.provider_account_snapshot == str(qbo.realm_id)
        )
        onboarding = qbp_scope_ready and qbp_provider_identity_ready
        if not provider_gate:
            reasons.append("quickbooks_payments_platform_approval_missing")
        if not qbp_scope_ready:
            reasons.append("quickbooks_payments_onboarding_incomplete")
        if not qbp_provider_identity_ready:
            reasons.append("quickbooks_payments_provider_identity_missing")
    else:
        reasons.append("provider_not_selected")

    qbo_snapshot_ready = bool(
        config
        and config.qbo_realm_snapshot
        and qbo
        and qbo.realm_id == config.qbo_realm_snapshot
    )
    qbo_ready = qbo_connection_ready and qbo_snapshot_ready
    if not qbo_ready:
        reasons.append("quickbooks_accounting_not_ready")
        if config and not config.qbo_realm_snapshot:
            reasons.append("quickbooks_realm_snapshot_missing")
        elif config and qbo_connection_ready and qbo.realm_id != config.qbo_realm_snapshot:
            reasons.append("quickbooks_realm_snapshot_mismatch")

    latest_backfill = (
        await db.execute(
            select(InvoiceSettlementBackfillRun).where(
                InvoiceSettlementBackfillRun.tenant_id == tenant.id,
            ).order_by(
                InvoiceSettlementBackfillRun.cutoff_at.desc(),
                InvoiceSettlementBackfillRun.created_at.desc(),
                InvoiceSettlementBackfillRun.id.desc(),
            ).limit(1)
        )
    ).scalar_one_or_none()
    backfill_ready = bool(latest_backfill and latest_backfill.state == "verified")
    if backfill_ready:
        supported_methods = (
            PaymentMethod.STRIPE,
            PaymentMethod.QUICKBOOKS,
            PaymentMethod.ZELLE,
            PaymentMethod.CHECK,
            PaymentMethod.ACH,
        )
        unreconciled_invoice = await db.scalar(
            select(Invoice.id)
            .join(RepairOrder, RepairOrder.id == Invoice.repair_order_id)
            .where(
                Invoice.tenant_id == tenant.id,
                Invoice.deleted_at.is_(None),
                RepairOrder.tenant_id == tenant.id,
                or_(invoice_id is None, Invoice.id.in_(scope_ids)),
                RepairOrder.customer_id.is_not(None),
                ~select(InvoiceSettlement.id).where(
                    InvoiceSettlement.tenant_id == tenant.id,
                    InvoiceSettlement.invoice_id == Invoice.id,
                    InvoiceSettlement.customer_id == RepairOrder.customer_id,
                    InvoiceSettlement.deleted_at.is_(None),
                ).correlate(Invoice).exists(),
            )
            .limit(1)
        )
        unreconciled_payment = await db.scalar(
            select(Payment.id).where(
                Payment.tenant_id == tenant.id,
                or_(invoice_id is None, Payment.invoice_id.in_(scope_ids)),
                Payment.deleted_at.is_(None),
                Payment.status.in_([PaymentStatus.COMPLETED, PaymentStatus.REFUNDED]),
                Payment.method.in_(supported_methods),
                Payment.amount > ZERO,
                ~select(InvoicePaymentAttempt.id)
                .join(
                    InvoiceSettlement,
                    and_(
                        InvoiceSettlement.id == InvoicePaymentAttempt.settlement_id,
                        InvoiceSettlement.tenant_id == InvoicePaymentAttempt.tenant_id,
                        InvoiceSettlement.invoice_id == InvoicePaymentAttempt.invoice_id,
                        InvoiceSettlement.customer_id == InvoicePaymentAttempt.customer_id,
                        InvoiceSettlement.deleted_at.is_(None),
                    ),
                )
                .join(
                    Invoice,
                    and_(
                        Invoice.id == InvoicePaymentAttempt.invoice_id,
                        Invoice.tenant_id == InvoicePaymentAttempt.tenant_id,
                        Invoice.deleted_at.is_(None),
                    ),
                )
                .join(
                    RepairOrder,
                    and_(
                        RepairOrder.id == Invoice.repair_order_id,
                        RepairOrder.tenant_id == InvoicePaymentAttempt.tenant_id,
                        RepairOrder.customer_id == InvoicePaymentAttempt.customer_id,
                        or_(
                            RepairOrder.deleted_at.is_(None),
                            InvoicePaymentAttempt.source == "backfill",
                        ),
                    ),
                )
                .where(
                    InvoicePaymentAttempt.tenant_id == tenant.id,
                    InvoicePaymentAttempt.invoice_id == Payment.invoice_id,
                    InvoicePaymentAttempt.payment_id == Payment.id,
                    InvoicePaymentAttempt.id == Payment.invoice_payment_attempt_id,
                    or_(
                        and_(
                            Payment.status == PaymentStatus.COMPLETED,
                            InvoicePaymentAttempt.state == "confirmed",
                        ),
                        and_(
                            Payment.status == PaymentStatus.REFUNDED,
                            InvoicePaymentAttempt.state.in_(["refunded", "reversed"]),
                        ),
                    ),
                    or_(
                        InvoicePaymentAttempt.applied_principal_amount == Payment.amount,
                        and_(
                            InvoicePaymentAttempt.source == "backfill",
                            InvoicePaymentAttempt.received_amount == Payment.amount,
                            or_(
                                and_(
                                    Payment.status == PaymentStatus.COMPLETED,
                                    InvoicePaymentAttempt.state == "confirmed",
                                    (
                                        InvoicePaymentAttempt.applied_principal_amount
                                        + InvoicePaymentAttempt.unapplied_amount
                                    ) == Payment.amount,
                                ),
                                and_(
                                    Payment.status == PaymentStatus.REFUNDED,
                                    InvoicePaymentAttempt.state == "refunded",
                                ),
                            ),
                        ),
                    ),
                    InvoicePaymentAttempt.deleted_at.is_(None),
                ).correlate(Payment).exists(),
            ).limit(1)
        )
        pending_zelle_invoices = (await db.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant.id,
                Invoice.zelle_pending_submitted_at.is_not(None),
                or_(invoice_id is None, Invoice.id.in_(scope_ids)),
                Invoice.deleted_at.is_(None),
            )
        )).scalars().all()
        unreconciled_zelle = None
        if pending_zelle_invoices:
            pending_invoice_ids = {invoice.id for invoice in pending_zelle_invoices}
            zelle_settlements = (await db.execute(select(InvoiceSettlement).where(
                InvoiceSettlement.tenant_id == tenant.id,
                InvoiceSettlement.invoice_id.in_(pending_invoice_ids),
                InvoiceSettlement.deleted_at.is_(None),
            ))).scalars().all()
            settlements_by_invoice = {
                settlement.invoice_id: settlement for settlement in zelle_settlements
            }
            zelle_attempts = (await db.execute(select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.tenant_id == tenant.id,
                InvoicePaymentAttempt.invoice_id.in_(pending_invoice_ids),
                InvoicePaymentAttempt.rail == "zelle",
                InvoicePaymentAttempt.deleted_at.is_(None),
            ))).scalars().all()
            attempts_by_invoice: dict[UUID, list[InvoicePaymentAttempt]] = {}
            for attempt in zelle_attempts:
                attempts_by_invoice.setdefault(attempt.invoice_id, []).append(attempt)
            for pending_invoice in pending_zelle_invoices:
                pending_settlement = settlements_by_invoice.get(pending_invoice.id)
                if pending_settlement is None or not any(
                    current_zelle_attempt_matches(
                        invoice=pending_invoice,
                        settlement=pending_settlement,
                        attempt=attempt,
                    )
                    for attempt in attempts_by_invoice.get(pending_invoice.id, [])
                ):
                    unreconciled_zelle = pending_invoice.id
                    break
        stale_reasons = list(ancestry_reasons)
        if unreconciled_invoice:
            stale_reasons.append("invoice_settlement_backfill_stale_invoice")
        if unreconciled_payment:
            stale_reasons.append("invoice_settlement_backfill_stale_payment")
        if unreconciled_zelle:
            stale_reasons.append("invoice_settlement_backfill_stale_zelle")
        reasons.extend(stale_reasons)
        backfill_ready = not stale_reasons
    if not backfill_ready:
        if not latest_backfill or latest_backfill.state != "verified":
            reasons.append("invoice_settlement_backfill_not_verified")

    mappings = _configuration_mappings(config)
    required = {
        "check_deposit_account",
        "zelle_ach_account",
        "card_fee_income_account",
        "processor_fee_expense_account",
        "sales_tax_liability_account",
        "checking_account",
    }
    if provider == "stripe_connect":
        required.add("stripe_clearing_account")
    if provider == "quickbooks_payments":
        required.add("qbp_clearing_account")
    gross_in_use = await db.scalar(select(InvoiceSettlement.id).where(
        InvoiceSettlement.tenant_id == tenant.id,
        InvoiceSettlement.accounting_composition_version == "gross_invoice_v1",
        InvoiceSettlement.deleted_at.is_(None),
    ).limit(1))
    authorized_gross = await db.scalar(select(InvoicePaymentAttempt.id).where(
        InvoicePaymentAttempt.tenant_id == tenant.id,
        InvoicePaymentAttempt.new_receipt_accounting_authorization.is_not(None),
    ).limit(1))
    if settings.DB048_GROSS_QBO_ACCOUNTING_ENABLED or gross_in_use is not None or authorized_gross is not None:
        required.update({"qbo_card_fee_item_id", "qbo_card_fee_tax_code_id"})
    mappings_ready = bool(config) and all(mappings.get(key) for key in required)
    if not mappings_ready:
        reasons.append("account_mappings_incomplete")
    writer_ready = bool(config) and config.writer_strategy == "dieselbridge"
    if not writer_ready:
        # DB-048 has no verified Intuit-native importer.  Fail closed rather
        # than let a selectable configuration accumulate dead-lettered QBO
        # operations or create accounting through two writers.
        reasons.append("accounting_writer_unsupported")

    ready = (
        global_gate
        and tenant_gate
        and provider_gate
        and onboarding
        and qbo_ready
        and mappings_ready
        and writer_ready
        and backfill_ready
    )
    status = "ready" if ready else (
        "unavailable_external_approval" if provider == "quickbooks_payments" and not provider_gate else "not_ready"
    )
    return ProviderReadiness(
        provider=provider,
        status=status,
        split_payment_global_gate=global_gate,
        split_payment_tenant_gate=tenant_gate,
        provider_global_gate=provider_gate,
        provider_onboarding_ready=onboarding,
        qbo_accounting_ready=qbo_ready,
        mappings_ready=mappings_ready,
        reasons=tuple(dict.fromkeys(reasons)),
        configuration=config,
    )


async def require_feature_ready(db: AsyncSession, tenant: Tenant, *, invoice_id: Optional[UUID] = None,
                                lock_ancestry: bool = False) -> ProviderReadiness:
    readiness = await provider_readiness(db, tenant, invoice_id=invoice_id, lock_ancestry=lock_ancestry)
    if not readiness.split_payment_global_gate or not readiness.split_payment_tenant_gate:
        raise SettlementDomainError("split_payments_disabled", "Partial payments are not enabled for this shop.")
    if readiness.status != "ready":
        if "previous_invoice_payment_pending" in readiness.reasons:
            raise SettlementDomainError("previous_invoice_payment_pending",
                "A previous version of this invoice has a pending payment. Resolve it before collecting another payment.")
        if "previous_invoice_payment_requires_review" in readiness.reasons:
            raise SettlementDomainError("historical_payment_balance_review",
                "A replaced invoice has payment activity. Resolve it before collecting a new payment.")
        code = (
            "quickbooks_payments_external_approval_pending"
            if readiness.status == "unavailable_external_approval"
            else "card_provider_not_ready"
        )
        raise SettlementDomainError(code, "The configured card provider is not ready.")
    return readiness


async def settlement_for_compatibility_route(
    db: AsyncSession,
    *,
    invoice: Invoice,
    tenant: Tenant,
    customer_id: UUID,
    lock: bool = True,
) -> Optional[InvoiceSettlement]:
    """Resolve legacy-route behavior without ever bypassing DB-048 history.

    A clean pre-rollout invoice may continue through its legacy path while the
    feature is disabled. Once an invoice has a DB-048 settlement, disabling a
    gate makes that invoice read-only; it can never fall back to a legacy
    full-balance charge or manual receipt.
    """
    query = select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == tenant.id,
        InvoiceSettlement.invoice_id == invoice.id,
        InvoiceSettlement.customer_id == customer_id,
    )
    from app.services.invoice_accounting_policy import require_standard_payment
    await require_standard_payment(db, invoice, new_entry=True)
    if lock:
        query = query.with_for_update()
    existing = await db.scalar(query)
    enabled = bool(
        settings.INVOICE_SPLIT_PAYMENTS_ENABLED
        and tenant.invoice_split_payments_enabled
    )
    if existing is not None and not enabled:
        has_attempt = await db.scalar(select(InvoicePaymentAttempt.id).where(
            InvoicePaymentAttempt.tenant_id == tenant.id,
            InvoicePaymentAttempt.invoice_id == invoice.id,
            InvoicePaymentAttempt.settlement_id == existing.id,
            InvoicePaymentAttempt.deleted_at.is_(None),
        ).limit(1))
        has_projection = any((
            money(existing.confirmed_principal) > ZERO,
            money(existing.active_pending_principal) > ZERO,
            money(existing.unapplied_credit) > ZERO,
            money(existing.refund_pending) > ZERO,
            int(existing.last_event_sequence or 0) > 0,
            existing.legacy_reconciliation_status != "native",
        ))
        if has_attempt is not None or has_projection:
            raise SettlementDomainError(
                "split_payments_disabled",
                "This invoice has payment activity and is temporarily read-only. Contact the shop.",
            )
    if not enabled:
        return None
    await require_feature_ready(db, tenant, invoice_id=invoice.id, lock_ancestry=lock)
    return existing or await get_or_create_settlement(
        db,
        invoice=invoice,
        customer_id=customer_id,
        tenant=tenant,
        lock=lock,
    )


async def get_or_create_settlement(
    db: AsyncSession,
    *,
    invoice: Invoice,
    customer_id: UUID,
    tenant: Tenant,
    lock: bool = True,
) -> InvoiceSettlement:
    query = select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == invoice.tenant_id,
        InvoiceSettlement.invoice_id == invoice.id,
        InvoiceSettlement.deleted_at.is_(None),
    )
    if lock:
        # A transaction may have waited for a concurrent pre-payment tax edit.
        # Refresh the identity map as well as acquiring the database row lock.
        query = query.with_for_update().execution_options(populate_existing=True)
    settlement = (await db.execute(query)).scalar_one_or_none()
    if settlement:
        return settlement

    principal, fee, fee_tax, tax_rate, fee_rate = invoice_money_snapshot(invoice)
    composition = "legacy_principal_v1"
    if settings.DB048_GROSS_QBO_ACCOUNTING_ENABLED and not invoice.quickbooks_invoice_id and invoice.status != InvoiceStatus.PAID:
        # An existing payment/link is history even if no settlement was lazily
        # initialized yet. Never reinterpret it under the new composition.
        prior_payment = await db.scalar(select(Payment.id).where(
            Payment.tenant_id == invoice.tenant_id, Payment.invoice_id == invoice.id,
        ).limit(1))
        prior_link = await db.scalar(select(PaymentAccountingLink.id).where(
            PaymentAccountingLink.tenant_id == invoice.tenant_id,
            PaymentAccountingLink.invoice_id == invoice.id,
        ).limit(1))
        if prior_payment is None and prior_link is None:
            composition = "gross_invoice_v1"
    settlement = InvoiceSettlement(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        customer_id=customer_id,
        principal_total=principal,
        accounting_composition_version=composition,
        max_card_fee=fee,
        max_card_fee_tax=fee_tax,
        sales_tax_rate_snapshot=tax_rate,
        card_fee_rate_snapshot=fee_rate,
        currency="USD",
        state="paid" if invoice.status == InvoiceStatus.PAID else "unpaid",
        confirmed_principal=principal if invoice.status == InvoiceStatus.PAID else ZERO,
        legacy_reconciliation_status=("legacy_paid_snapshot" if invoice.status == InvoiceStatus.PAID else "native"),
        legacy_reconciliation_note=(
            "Paid invoice baseline; no tender is reconstructed by lazy initialization."
            if invoice.status == InvoiceStatus.PAID
            else None
        ),
    )
    db.add(settlement)
    await db.flush()
    if invoice.status == InvoiceStatus.PAID:
        await append_ledger_event(
            db,
            settlement=settlement,
            event_type="legacy_paid_snapshot",
            idempotency_key=f"settlement:{settlement.id}:legacy-paid",
            actor=None,
            principal_delta=principal,
            evidence={"origin": "baseline", "reconstructed_tender": False},
        )
    return settlement


async def append_ledger_event(
    db: AsyncSession,
    *,
    settlement: InvoiceSettlement,
    event_type: str,
    idempotency_key: str,
    actor: Optional[CurrentUser],
    attempt: Optional[InvoicePaymentAttempt] = None,
    prior_state: Optional[str] = None,
    new_state: Optional[str] = None,
    principal_delta: Decimal = ZERO,
    pending_delta: Decimal = ZERO,
    unapplied_delta: Decimal = ZERO,
    refund_pending_delta: Decimal = ZERO,
    evidence: Optional[dict[str, Any]] = None,
    correlation_id: Optional[UUID] = None,
) -> InvoicePaymentLedgerEvent:
    actor_id, actor_name, actor_role = _actor_snapshot(actor)
    settlement.last_event_sequence = int(settlement.last_event_sequence or 0) + 1
    event_row = InvoicePaymentLedgerEvent(
        tenant_id=settlement.tenant_id,
        invoice_id=settlement.invoice_id,
        settlement_id=settlement.id,
        attempt_id=attempt.id if attempt else None,
        customer_id=settlement.customer_id,
        actor_user_id=actor_id,
        actor_name_snapshot=actor_name,
        actor_role_snapshot=actor_role,
        sequence=settlement.last_event_sequence,
        correlation_id=correlation_id or uuid4(),
        idempotency_key=idempotency_key,
        event_type=event_type,
        prior_state=prior_state,
        new_state=new_state,
        principal_delta=money(principal_delta),
        pending_delta=money(pending_delta),
        unapplied_delta=money(unapplied_delta),
        refund_pending_delta=money(refund_pending_delta),
        money_snapshot={
            "principal_total": str(money(settlement.principal_total)),
            "confirmed_principal": str(money(settlement.confirmed_principal)),
            "active_pending_principal": str(money(settlement.active_pending_principal)),
            "unapplied_credit": str(money(settlement.unapplied_credit)),
            "refund_pending": str(money(settlement.refund_pending)),
        },
        evidence_snapshot=evidence or {},
    )
    db.add(event_row)
    return event_row


async def _allocated_card_components(
    db: AsyncSession,
    settlement_id: UUID,
    *,
    states: tuple[str, ...] = ("pending", "confirmed"),
    exclude_attempt_id: Optional[UUID] = None,
) -> tuple[Decimal, Decimal, Decimal]:
    principal_expression = case(
        (
            InvoicePaymentAttempt.state == "confirmed",
            InvoicePaymentAttempt.applied_principal_amount,
        ),
        else_=InvoicePaymentAttempt.principal_amount,
    )
    fee_expression = case(
        (
            InvoicePaymentAttempt.state == "confirmed",
            InvoicePaymentAttempt.applied_card_fee_amount,
        ),
        else_=InvoicePaymentAttempt.card_fee_amount,
    )
    fee_tax_expression = case(
        (
            InvoicePaymentAttempt.state == "confirmed",
            InvoicePaymentAttempt.applied_card_fee_tax_amount,
        ),
        else_=InvoicePaymentAttempt.card_fee_tax_amount,
    )
    filters = [
        InvoicePaymentAttempt.settlement_id == settlement_id,
        InvoicePaymentAttempt.rail == "card",
        InvoicePaymentAttempt.state.in_(states),
        InvoicePaymentAttempt.deleted_at.is_(None),
    ]
    if exclude_attempt_id is not None:
        filters.append(InvoicePaymentAttempt.id != exclude_attempt_id)
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(principal_expression), 0),
                func.coalesce(func.sum(fee_expression), 0),
                func.coalesce(func.sum(fee_tax_expression), 0),
            ).where(*filters)
        )
    ).one()
    return money(row[0]), money(row[1]), money(row[2])


def _incremental_card_fee(
    *,
    maximum: Decimal,
    principal_total: Decimal,
    prior_card_principal: Decimal,
    new_card_principal: Decimal,
    prior_allocated: Decimal,
) -> Decimal:
    maximum = money(maximum)
    principal_total = money(principal_total)
    if maximum <= ZERO or principal_total <= ZERO or new_card_principal <= ZERO:
        return ZERO
    cumulative_principal = min(
        principal_total,
        money(prior_card_principal) + money(new_card_principal),
    )
    # Only card-funded principal can earn the final rounding remainder. A
    # non-card tender closing A/R must never cause the next card to inherit the
    # full-invoice surcharge.
    cumulative_target = (
        maximum
        if cumulative_principal >= principal_total
        else money(maximum * cumulative_principal / principal_total)
    )
    remaining_maximum = max(ZERO, maximum - money(prior_allocated))
    return min(
        remaining_maximum,
        max(ZERO, money(cumulative_target - money(prior_allocated))),
    )


async def _card_fee_allocation(
    db: AsyncSession,
    settlement: InvoiceSettlement,
    principal: Decimal,
) -> tuple[Decimal, Decimal]:
    total = money(settlement.principal_total)
    if total <= ZERO:
        return ZERO, ZERO
    prior_principal, prior_fee, prior_tax = await _allocated_card_components(
        db, settlement.id,
    )
    return (
        _incremental_card_fee(
            maximum=settlement.max_card_fee,
            principal_total=total,
            prior_card_principal=prior_principal,
            new_card_principal=principal,
            prior_allocated=prior_fee,
        ),
        _incremental_card_fee(
            maximum=settlement.max_card_fee_tax,
            principal_total=total,
            prior_card_principal=prior_principal,
            new_card_principal=principal,
            prior_allocated=prior_tax,
        ),
    )


async def create_attempt(
    db: AsyncSession,
    *,
    invoice: Invoice,
    tenant: Tenant,
    customer_id: UUID,
    actor: Optional[CurrentUser],
    amount: Decimal,
    rail: str,
    expected_settlement_version: int,
    idempotency_key: str,
    source: str,
    subject_type: str,
    subject_id: Optional[UUID],
    sender_evidence: Optional[dict[str, Any]] = None,
) -> AttemptCreation:
    if (
        invoice.tenant_id != tenant.id
        or not tenant.is_active
        or tenant.deleted_at is not None
        or invoice.deleted_at is not None
        or invoice.status == InvoiceStatus.CANCELLED
        or invoice.voided_at is not None
    ):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    active_order_id = await db.scalar(select(RepairOrder.id).where(
        RepairOrder.id == invoice.repair_order_id,
        RepairOrder.tenant_id == tenant.id,
        RepairOrder.customer_id == customer_id,
        RepairOrder.deleted_at.is_(None),
        RepairOrder.status != RepairOrderStatus.CANCELLED,
    ))
    if active_order_id is None:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    active_customer_id = await db.scalar(select(Customer.id).where(
        Customer.id == customer_id,
        Customer.tenant_id == tenant.id,
        Customer.deleted_at.is_(None),
    ))
    if active_customer_id is None:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)

    readiness = await require_feature_ready(db, tenant, invoice_id=invoice.id, lock_ancestry=True)
    if rail not in {"card", "zelle", "check", "ach"}:
        raise SettlementDomainError("payment_rail_disabled", "This payment rail is not available.")
    if subject_type in {"customer", "guest"} and rail not in {"card", "zelle"}:
        raise SettlementDomainError("payment_rail_disabled", "This payment rail is not available.")

    amount = money(amount)
    if amount < CENT:
        raise SettlementDomainError("payment_amount_invalid", "The payment amount must be at least $0.01.", status_code=422)

    request_payload = {
        "tenant_id": str(tenant.id),
        "invoice_id": str(invoice.id),
        "customer_id": str(customer_id),
        "subject_type": subject_type,
        "subject_id": str(subject_id) if subject_id else None,
        "source": source,
        "rail": rail,
        "amount": str(amount),
        "evidence": sender_evidence or {},
    }
    request_hash = _canonical_hash(request_payload)
    existing = (
        await db.execute(
            select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.tenant_id == tenant.id,
                InvoicePaymentAttempt.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.request_hash != request_hash:
            raise SettlementDomainError("idempotency_conflict", "This idempotency key was used for a different request.")
        settlement = await db.get(InvoiceSettlement, existing.settlement_id)
        return AttemptCreation(existing, settlement, replayed=True)

    settlement = await get_or_create_settlement(
        db,
        invoice=invoice,
        customer_id=customer_id,
        tenant=tenant,
        lock=True,
    )
    if settlement.version != expected_settlement_version:
        raise SettlementDomainError(
            "stale_settlement_version",
            "The invoice balance changed. Refresh before paying.",
            retryable=True,
            current_version=settlement.version,
        )
    from app.services.invoice_accounting_policy import require_standard_payment
    await require_standard_payment(db, invoice, new_entry=True)
    available = allocatable_balance(settlement)
    if amount > available:
        raise SettlementDomainError(
            "payment_amount_exceeds_allocatable_balance",
            "The requested amount is no longer available to pay.",
            retryable=True,
            current_version=settlement.version,
        )

    config = readiness.configuration
    await bind_settlement_accounting_realm(
        db,
        settlement=settlement,
        config=config,
    )
    # Materialize the one-time invoice/accounting-realm bind before the first
    # live attempt is inserted.  The database and ORM guards intentionally
    # reject binding a realm after a live attempt exists; flushing both rows in
    # the same unit of work makes INSERT ordering dialect-dependent and can
    # cause the guard to observe the new attempt before the settlement update.
    await db.flush([settlement])
    provider = readiness.provider if rail == "card" else "manual"
    fee = fee_tax = ZERO
    if rail == "card":
        fee, fee_tax = await _card_fee_allocation(db, settlement, amount)
    actor_id, actor_name, actor_role = _actor_snapshot(actor, fallback="Customer")
    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=ZELLE_RESERVATION_HOURS)
        if rail == "zelle"
        else datetime.now(timezone.utc) + timedelta(minutes=CARD_RESERVATION_MINUTES)
        if rail == "card"
        else None
    )
    attempt = InvoicePaymentAttempt(
        id=uuid4(),
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        settlement_id=settlement.id,
        customer_id=customer_id,
        source=source,
        rail=rail,
        provider=provider,
        state="pending",
        principal_amount=amount,
        card_fee_amount=fee,
        card_fee_tax_amount=fee_tax,
        provider_charge_amount=money(amount + fee + fee_tax),
        currency="USD",
        provider_configuration_version=config.version,
        provider_account_id=config.provider_account_snapshot,
        manual_evidence=sender_evidence or {},
        actor_user_id=actor_id,
        actor_name_snapshot=actor_name,
        actor_role_snapshot=actor_role,
        subject_type=subject_type,
        subject_id=subject_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        expires_at=expires_at,
    )
    from app.services.invoice_accounting_policy import HISTORICAL_HOLD
    if invoice.accounting_policy == HISTORICAL_HOLD:
        from app.services.new_receipt_accounting import issue_authorization
        attempt.new_receipt_accounting_authorization = issue_authorization(attempt, config)
    db.add(attempt)
    await db.flush()
    prior_state = settlement.state
    settlement.active_pending_principal = money(settlement.active_pending_principal) + amount
    settlement.version += 1
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="attempt_created",
        idempotency_key=f"attempt:{attempt.id}:created",
        actor=actor,
        prior_state=prior_state,
        new_state=settlement.state,
        pending_delta=amount,
        evidence={"source": source, "rail": rail, "provider": provider},
    )
    if rail != "card" and sender_evidence:
        await append_ledger_event(
            db,
            settlement=settlement,
            attempt=attempt,
            event_type="manual_evidence_recorded",
            idempotency_key=f"attempt:{attempt.id}:evidence",
            actor=actor,
            evidence={"evidence_fields": sorted(key for key, value in sender_evidence.items() if value)},
        )
    return AttemptCreation(attempt, settlement)


def _manual_evidence_reference(attempt: InvoicePaymentAttempt, explicit_reference: Optional[str]) -> Optional[str]:
    if explicit_reference and explicit_reference.strip():
        return explicit_reference.strip()
    evidence = attempt.manual_evidence or {}
    reference = evidence.get("reference") or evidence.get("reference_number")
    return str(reference).strip() if reference else None


async def locked_accessible_invoice_for_attempt(
    db: AsyncSession,
    attempt: InvoicePaymentAttempt,
) -> Invoice:
    """Lock and enforce the generic DB-048 invoice/order lifecycle boundary.

    Provider success can arrive after an invoice or repair order is retired.
    The money must then remain visible for explicit reconciliation, but the
    inaccessible lifecycle can never be resurrected by confirmation.
    """
    invoice = (
        await db.execute(
            select(Invoice)
            .join(RepairOrder, RepairOrder.id == Invoice.repair_order_id)
            .join(
                Customer,
                and_(
                    Customer.id == attempt.customer_id,
                    Customer.tenant_id == attempt.tenant_id,
                    Customer.id == RepairOrder.customer_id,
                    Customer.deleted_at.is_(None),
                ),
            )
            .join(
                Tenant,
                and_(
                    Tenant.id == attempt.tenant_id,
                    Tenant.is_active.is_(True),
                    Tenant.deleted_at.is_(None),
                ),
            )
            .options(
                selectinload(Invoice.repair_order).selectinload(
                    RepairOrder.customer
                )
            )
            .where(
                Invoice.id == attempt.invoice_id,
                Invoice.tenant_id == attempt.tenant_id,
                Invoice.deleted_at.is_(None),
                Invoice.voided_at.is_(None),
                Invoice.status != InvoiceStatus.CANCELLED,
                RepairOrder.tenant_id == attempt.tenant_id,
                RepairOrder.customer_id == attempt.customer_id,
                RepairOrder.deleted_at.is_(None),
                RepairOrder.status != RepairOrderStatus.CANCELLED,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise SettlementDomainError(
            "invoice_not_found", "Invoice not found.", status_code=404
        )
    return invoice


async def _enqueue_accounting(
    db: AsyncSession,
    *,
    settlement: InvoiceSettlement,
    attempt: InvoicePaymentAttempt,
    config: TenantPaymentProviderConfiguration,
) -> PaymentAccountingLink:
    await bind_settlement_accounting_realm(
        db,
        settlement=settlement,
        config=config,
    )
    mappings = _configuration_mappings(config)
    link = PaymentAccountingLink(
        tenant_id=settlement.tenant_id,
        invoice_id=settlement.invoice_id,
        attempt_id=attempt.id,
        financial_object_type="invoice_payment",
        financial_object_id=attempt.id,
        operation_version=1,
        principal_amount_snapshot=money(attempt.applied_principal_amount),
        gross_amount_snapshot=money(attempt.provider_charge_amount),
        owning_writer=config.writer_strategy,
        account_mapping_snapshot=mappings,
        qbo_realm_snapshot=config.qbo_realm_snapshot,
        sync_state="pending",
    )
    db.add(link)
    await db.flush()
    outbox = ProviderOutboxEvent(
        tenant_id=settlement.tenant_id,
        event_type=ACCOUNTING_EVENT,
        aggregate_type="invoice_payment_attempt",
        aggregate_id=attempt.id,
        payload={
            "accounting_link_id": str(link.id),
            "attempt_id": str(attempt.id),
            "invoice_id": str(settlement.invoice_id),
            "principal_amount": str(money(attempt.applied_principal_amount)),
            "applied_card_fee_amount": str(money(attempt.applied_card_fee_amount)),
            "applied_card_fee_tax_amount": str(money(attempt.applied_card_fee_tax_amount)),
            "received_amount": str(money(attempt.received_amount)),
            "unapplied_amount": str(money(attempt.unapplied_amount)),
            "provider": attempt.provider,
            "provider_account": attempt.provider_account_id,
            "configuration_version": attempt.provider_configuration_version,
        },
        idempotency_key=f"invoice-payment:{attempt.id}:v1:{attempt.provider}:{attempt.provider_account_id or 'manual'}",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=datetime.now(timezone.utc),
    )
    db.add(outbox)
    settlement.accounting_sync_status = "accounting_sync_pending"
    from app.services.invoice_accounting_policy import locked_policy, HISTORICAL_HOLD
    invoice = await db.get(Invoice, settlement.invoice_id)
    from app.services.new_receipt_accounting import valid_attempt_authorization
    if await locked_policy(db, invoice) == HISTORICAL_HOLD and not await valid_attempt_authorization(db, attempt):
        link.sync_state = HISTORICAL_HOLD
        settlement.accounting_sync_status = HISTORICAL_HOLD
        outbox.status = "suppressed"
        outbox.payload = {**outbox.payload, "suppression_reason": HISTORICAL_HOLD}
    return link


async def confirm_attempt(
    db: AsyncSession,
    *,
    attempt_id: UUID,
    tenant: Tenant,
    actor: Optional[CurrentUser],
    expected_attempt_version: int,
    idempotency_key: str,
    received_principal: Optional[Decimal] = None,
    reference: Optional[str] = None,
    provider_charge_id: Optional[str] = None,
    provider_event_id: Optional[str] = None,
    processor_fee: Decimal = ZERO,
    verified_provider_fact: bool = False,
) -> AttemptConfirmation:
    settlement_id = (
        await db.execute(
            select(InvoicePaymentAttempt.settlement_id).where(
                InvoicePaymentAttempt.id == attempt_id,
                InvoicePaymentAttempt.tenant_id == tenant.id,
                InvoicePaymentAttempt.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if settlement_id is None:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    settlement = (
        await db.execute(
            select(InvoiceSettlement)
            .where(InvoiceSettlement.id == settlement_id, InvoiceSettlement.tenant_id == tenant.id)
            .with_for_update()
        )
    ).scalar_one()
    attempt = (
        await db.execute(
            select(InvoicePaymentAttempt)
            .where(InvoicePaymentAttempt.id == attempt_id, InvoicePaymentAttempt.tenant_id == tenant.id)
            .with_for_update()
        )
    ).scalar_one()

    # Enforce lifecycle before replay lookup, manual-reference normalization,
    # money projection, accounting enqueue, or paid/order state mutation.
    invoice = await locked_accessible_invoice_for_attempt(db, attempt)
    from app.services.invoice_accounting_policy import require_standard_payment
    await require_standard_payment(db, invoice, attempt=attempt, verified_provider_fact=(
        verified_provider_fact and actor is None and attempt.rail == "card"
        and attempt.provider in {"stripe_connect", "quickbooks_payments"}
        and bool(provider_charge_id or provider_event_id)))

    if attempt.state == "confirmed":
        payment = await db.get(Payment, attempt.payment_id) if attempt.payment_id else None
        overpayment = (
            await db.execute(select(PaymentOverpayment).where(PaymentOverpayment.source_attempt_id == attempt.id))
        ).scalar_one_or_none()
        refund = None
        if overpayment:
            refund = (
                await db.execute(select(PaymentRefund).where(PaymentRefund.overpayment_id == overpayment.id))
            ).scalar_one_or_none()
        return AttemptConfirmation(attempt, settlement, payment, overpayment, refund, False, replayed=True)
    if attempt.version != expected_attempt_version:
        raise SettlementDomainError("stale_attempt_version", "The payment attempt changed. Refresh and try again.", current_version=attempt.version)
    if attempt.state not in {"pending", "failed", "expired"}:
        raise SettlementDomainError("attempt_transition_conflict", "This payment attempt cannot be confirmed.")

    ref = _manual_evidence_reference(attempt, reference)
    if attempt.rail in {"check", "ach", "zelle"} and not ref:
        raise SettlementDomainError("manual_payment_evidence_required", "A transaction reference is required.", status_code=422)
    if attempt.rail in {"check", "ach", "zelle"}:
        # Serialize manual-reference confirmation per customer.  Check numbers
        # can legitimately repeat across unrelated customers, so the safety
        # boundary is tenant + customer + rail rather than a false global
        # unique reference. The stored fingerprint is secret-free evidence.
        await db.execute(
            select(Customer.id).where(
                Customer.id == attempt.customer_id,
                Customer.tenant_id == tenant.id,
            ).with_for_update()
        )
        normalized_reference = " ".join(ref.casefold().split())
        reference_fingerprint = hashlib.sha256(normalized_reference.encode()).hexdigest()
        duplicate = (
            await db.execute(
                select(InvoicePaymentAttempt.id).where(
                    InvoicePaymentAttempt.tenant_id == tenant.id,
                    InvoicePaymentAttempt.customer_id == attempt.customer_id,
                    InvoicePaymentAttempt.rail == attempt.rail,
                    InvoicePaymentAttempt.manual_reference_fingerprint == reference_fingerprint,
                    InvoicePaymentAttempt.id != attempt.id,
                    InvoicePaymentAttempt.state.in_(["confirmed", "refunded", "reversed"]),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if duplicate:
            raise SettlementDomainError(
                "manual_reference_requires_review",
                "This payment reference was already recorded for the customer and requires manager review.",
                status_code=409,
            )
        attempt.manual_reference_fingerprint = reference_fingerprint

    received = money(received_principal if received_principal is not None else attempt.principal_amount)
    if received < CENT:
        raise SettlementDomainError("payment_amount_invalid", "The received amount must be at least $0.01.", status_code=422)
    remaining_before = max(ZERO, money(settlement.principal_total) - money(settlement.confirmed_principal))
    applied = min(received, remaining_before, money(attempt.principal_amount))
    principal_excess = money(received - applied)
    original_card_fee = money(attempt.card_fee_amount)
    original_card_fee_tax = money(attempt.card_fee_tax_amount)
    earned_card_fee = original_card_fee
    earned_card_fee_tax = original_card_fee_tax
    if attempt.rail == "card" and applied < money(attempt.principal_amount):
        prior_card_principal, prior_card_fee, prior_card_fee_tax = (
            await _allocated_card_components(
                db,
                settlement.id,
                states=("confirmed",),
                exclude_attempt_id=attempt.id,
            )
        )
        earned_card_fee = min(
            original_card_fee,
            _incremental_card_fee(
                maximum=settlement.max_card_fee,
                principal_total=settlement.principal_total,
                prior_card_principal=prior_card_principal,
                new_card_principal=applied,
                prior_allocated=prior_card_fee,
            ),
        )
        earned_card_fee_tax = min(
            original_card_fee_tax,
            _incremental_card_fee(
                maximum=settlement.max_card_fee_tax,
                principal_total=settlement.principal_total,
                prior_card_principal=prior_card_principal,
                new_card_principal=applied,
                prior_allocated=prior_card_fee_tax,
            ),
        )
    unearned_card_fee = money(original_card_fee - earned_card_fee)
    unearned_card_fee_tax = money(original_card_fee_tax - earned_card_fee_tax)
    # Stripe has already accepted the immutable provider gross. Retain only
    # the principal and surcharge actually earned by the principal that still
    # fits on the invoice. Everything else—including now-unearned surcharge
    # and its tax—must remain unapplied and be refunded to the original rail.
    unapplied_gross = (
        max(
            ZERO,
            money(attempt.provider_charge_amount)
            - applied
            - earned_card_fee
            - earned_card_fee_tax,
        )
        if attempt.rail == "card"
        else principal_excess
    )
    prior_state = settlement.state
    if attempt.state == "pending":
        settlement.active_pending_principal = max(
            ZERO,
            money(settlement.active_pending_principal) - money(attempt.principal_amount),
        )
    settlement.confirmed_principal = money(settlement.confirmed_principal) + applied
    settlement.unapplied_credit = money(settlement.unapplied_credit) + unapplied_gross
    settlement.version += 1
    attempt.state = "confirmed"
    attempt.received_amount = received
    attempt.applied_principal_amount = applied
    attempt.applied_card_fee_amount = earned_card_fee
    attempt.applied_card_fee_tax_amount = earned_card_fee_tax
    attempt.unapplied_amount = unapplied_gross
    attempt.processor_fee_amount = money(processor_fee)
    attempt.provider_charge_id = provider_charge_id or attempt.provider_charge_id
    attempt.provider_event_id = provider_event_id or attempt.provider_event_id
    attempt.provider_reference = ref or attempt.provider_reference
    attempt.confirmed_at = datetime.now(timezone.utc)
    attempt.failure_code = None
    attempt.version += 1

    payment_method = {
        "card": PaymentMethod.STRIPE if attempt.provider == "stripe_connect" else PaymentMethod.QUICKBOOKS,
        "zelle": PaymentMethod.ZELLE,
        "check": PaymentMethod.CHECK,
        "ach": PaymentMethod.ACH,
    }[attempt.rail]
    payment = Payment(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        payment_number=await allocate_next_payment_number(db, tenant.id),
        # Legacy balance/report consumers sum Payment.amount against invoice
        # principal. Keep that compatibility projection principal-only; card
        # surcharge/tax and provider gross stay on the DB-048 attempt/accounting
        # records and never reduce or inflate A/R.
        amount=applied,
        method=payment_method,
        status=PaymentStatus.COMPLETED,
        stripe_payment_intent_id=attempt.provider_intent_id if attempt.provider == "stripe_connect" else None,
        stripe_charge_id=attempt.provider_charge_id if attempt.provider == "stripe_connect" else None,
        stripe_connected_account_id=attempt.provider_account_id if attempt.provider == "stripe_connect" else None,
        quickbooks_charge_id=attempt.provider_charge_id if attempt.provider == "quickbooks_payments" else None,
        quickbooks_charge_status="CAPTURED" if attempt.provider == "quickbooks_payments" else None,
        payment_provider=attempt.provider,
        reference_number=ref,
        recorded_by_user_id=attempt.actor_user_id,
        notes="DB-048 partial invoice allocation",
        invoice_payment_attempt_id=attempt.id,
    )
    db.add(payment)
    await db.flush()
    attempt.payment_id = payment.id

    config = (
        await db.execute(
            select(TenantPaymentProviderConfiguration).where(
                TenantPaymentProviderConfiguration.tenant_id == tenant.id,
                TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version,
            )
        )
    ).scalar_one_or_none()
    if config is None:
        raise SettlementDomainError("provider_configuration_missing", "The snapshotted provider configuration is unavailable.")
    await _enqueue_accounting(db, settlement=settlement, attempt=attempt, config=config)

    paid_transition = money(settlement.confirmed_principal) >= money(settlement.principal_total) and invoice.status != InvoiceStatus.PAID
    if paid_transition:
        invoice.status = InvoiceStatus.PAID
        if invoice.paid_at is None:
            invoice.paid_at = datetime.now(timezone.utc)
        invoice.repair_order.status = RepairOrderStatus.PAID
        await enqueue_paid_invoice_webhook(
            db,
            tenant=tenant,
            invoice=invoice,
            order=invoice.repair_order,
            customer=invoice.repair_order.customer,
        )
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="payment_confirmed",
        idempotency_key=f"confirm:{idempotency_key}",
        actor=actor,
        prior_state=prior_state,
        new_state=settlement.state,
        principal_delta=applied,
        pending_delta=-money(attempt.principal_amount),
        unapplied_delta=unapplied_gross,
        evidence={
            "received_principal": str(received),
            "provider_charge_amount": str(money(attempt.provider_charge_amount)),
            "principal_excess": str(principal_excess),
            "earned_card_fee": str(earned_card_fee),
            "earned_card_fee_tax": str(earned_card_fee_tax),
            "unearned_card_fee": str(unearned_card_fee),
            "unearned_card_fee_tax": str(unearned_card_fee_tax),
            "reference_present": bool(ref),
            "provider_event_present": bool(provider_event_id),
        },
    )
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="accounting_queued",
        idempotency_key=f"attempt:{attempt.id}:accounting-queued:v1",
        actor=actor,
        evidence={"writer": config.writer_strategy},
    )

    overpayment = refund = None
    if unapplied_gross > ZERO:
        overpayment = PaymentOverpayment(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            settlement_id=settlement.id,
            source_attempt_id=attempt.id,
            customer_id=settlement.customer_id,
            amount=unapplied_gross,
            # Overpayment resolution uses its own lifecycle.  The refund row
            # below tracks submission state independently; keeping the
            # overpayment at ``refund_required`` until the worker accepts the
            # refund avoids conflating a queued request with money in flight.
            state="refund_required",
        )
        db.add(overpayment)
        await db.flush()
        refund = PaymentRefund(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            source_attempt_id=attempt.id,
            overpayment_id=overpayment.id,
            amount=unapplied_gross,
            reason="Accidental payment above the remaining invoice balance",
            destination_rail=attempt.rail,
            mode="automatic" if attempt.rail == "card" else "manual",
            state="pending" if attempt.rail == "card" else "manual_action_required",
            actor_user_id=None,
            actor_name_snapshot="System",
            idempotency_key=f"overpayment:{overpayment.id}:refund:v1",
            request_hash=_canonical_hash({
                "operation": "automatic_overpayment_refund",
                "attempt_id": str(attempt.id),
                "overpayment_id": str(overpayment.id),
                "amount": str(unapplied_gross),
                "reason": "Accidental payment above the remaining invoice balance",
            }),
        )
        db.add(refund)
        await db.flush()
        settlement.refund_pending = money(settlement.refund_pending) + unapplied_gross
        settlement.state = settlement_state(settlement)
        await append_ledger_event(
            db,
            settlement=settlement,
            attempt=attempt,
            event_type="overpayment_detected",
            idempotency_key=f"attempt:{attempt.id}:overpayment",
            actor=None,
            unapplied_delta=unapplied_gross,
            evidence={
                "overpayment_id": str(overpayment.id),
                "refund_mode": refund.mode,
                "principal_excess": str(principal_excess),
                "unearned_card_fee": str(unearned_card_fee),
                "unearned_card_fee_tax": str(unearned_card_fee_tax),
            },
        )
        await append_ledger_event(
            db,
            settlement=settlement,
            attempt=attempt,
            event_type="refund_requested",
            idempotency_key=f"refund:{refund.id}:requested",
            actor=None,
            refund_pending_delta=unapplied_gross,
            evidence={"refund_id": str(refund.id), "mode": refund.mode},
        )
        outbox = ProviderOutboxEvent(
            tenant_id=tenant.id,
            event_type=("payment_refund.provider_submit" if attempt.rail == "card" else "payment_refund.manual_task"),
            aggregate_type="payment_refund",
            aggregate_id=refund.id,
            payload={
                "refund_id": str(refund.id),
                "attempt_id": str(attempt.id),
                "amount": str(unapplied_gross),
            },
            idempotency_key=f"refund:{refund.id}:{attempt.provider}:{attempt.provider_account_id or 'manual'}",
            status=ProviderOutboxStatus.PENDING.value,
            available_at=datetime.now(timezone.utc),
        )
        db.add(outbox)

    return AttemptConfirmation(attempt, settlement, payment, overpayment, refund, paid_transition)


async def fail_attempt(
    db: AsyncSession,
    *,
    attempt_id: UUID,
    tenant_id: UUID,
    actor: Optional[CurrentUser],
    expected_attempt_version: int,
    failure_code: str,
    idempotency_key: str,
    expired: bool = False,
) -> tuple[InvoicePaymentAttempt, InvoiceSettlement]:
    attempt = (
        await db.execute(
            select(InvoicePaymentAttempt)
            .where(InvoicePaymentAttempt.id == attempt_id, InvoicePaymentAttempt.tenant_id == tenant_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not attempt:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    settlement = (
        await db.execute(select(InvoiceSettlement).where(InvoiceSettlement.id == attempt.settlement_id).with_for_update())
    ).scalar_one()
    if attempt.state in {"failed", "expired"}:
        return attempt, settlement
    if attempt.state != "pending" or attempt.version != expected_attempt_version:
        raise SettlementDomainError("attempt_transition_conflict", "This payment attempt cannot be changed.", current_version=attempt.version)
    prior_state = settlement.state
    settlement.active_pending_principal = max(ZERO, money(settlement.active_pending_principal) - money(attempt.principal_amount))
    settlement.version += 1
    attempt.state = "expired" if expired else "failed"
    attempt.failure_code = failure_code[:100]
    attempt.failed_at = datetime.now(timezone.utc)
    attempt.version += 1
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="payment_expired" if expired else "payment_failed",
        idempotency_key=f"fail:{idempotency_key}",
        actor=actor,
        prior_state=prior_state,
        new_state=settlement.state,
        pending_delta=-money(attempt.principal_amount),
        evidence={"failure_code": failure_code[:100]},
    )
    return attempt, settlement


async def create_refund(
    db: AsyncSession,
    *,
    attempt: InvoicePaymentAttempt,
    tenant_id: UUID,
    actor: CurrentUser,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
) -> PaymentRefund:
    if attempt.tenant_id != tenant_id:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if attempt.rail == "cash":
        raise SettlementDomainError("cash_refund_unavailable", "Local cash refunds require a separate supported reversal workflow.")
    amount = money(amount)
    reason = reason.strip()
    request_hash = _canonical_hash({
        "operation": "refund",
        "attempt_id": str(attempt.id),
        "amount": str(amount),
        "reason": reason,
    })
    existing = (
        await db.execute(select(PaymentRefund).where(
            PaymentRefund.tenant_id == tenant_id,
            PaymentRefund.idempotency_key == idempotency_key,
        ))
    ).scalar_one_or_none()
    if existing:
        if existing.request_hash != request_hash:
            raise SettlementDomainError(
                "idempotency_conflict",
                "The Idempotency-Key was already used with a different request.",
                status_code=409,
            )
        return existing
    settlement = (
        await db.execute(select(InvoiceSettlement).where(InvoiceSettlement.id == attempt.settlement_id).with_for_update())
    ).scalar_one()
    from app.services.invoice_accounting_policy import require_standard_payment
    invoice = await db.scalar(select(Invoice).where(Invoice.id == attempt.invoice_id, Invoice.tenant_id == tenant_id))
    if invoice is None:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    await require_standard_payment(db, invoice, attempt=attempt)
    overpayment = (
        await db.execute(select(PaymentOverpayment).where(
            PaymentOverpayment.tenant_id == tenant_id,
            PaymentOverpayment.invoice_id == attempt.invoice_id,
            PaymentOverpayment.source_attempt_id == attempt.id,
        ).with_for_update())
    ).scalar_one_or_none()
    if not overpayment:
        raise SettlementDomainError(
            "refund_source_not_found",
            "No unresolved overpayment belongs to this payment attempt.",
            status_code=409,
        )
    prior_refunds = (
        await db.execute(select(PaymentRefund).where(
            PaymentRefund.tenant_id == tenant_id,
            PaymentRefund.overpayment_id == overpayment.id,
            PaymentRefund.state != "cancelled",
        ).with_for_update())
    ).scalars().all()
    if prior_refunds:
        raise SettlementDomainError(
            "refund_in_progress",
            "This overpayment already has a refund operation. Retry the existing refund if it failed.",
            status_code=409,
        )
    source_remaining = money(overpayment.amount)
    unreserved_unapplied = max(
        ZERO,
        money(settlement.unapplied_credit) - money(settlement.refund_pending),
    )
    if amount > source_remaining or amount > unreserved_unapplied:
        raise SettlementDomainError(
            "refund_amount_exceeds_unapplied",
            "Refund exceeds unapplied money from this payment attempt.",
        )
    actor_id, actor_name, _ = _actor_snapshot(actor)
    refund = PaymentRefund(
        tenant_id=tenant_id,
        invoice_id=attempt.invoice_id,
        source_attempt_id=attempt.id,
        overpayment_id=overpayment.id,
        amount=amount,
        reason=reason,
        destination_rail=attempt.rail,
        mode="automatic" if attempt.rail == "card" else "manual",
        state="pending" if attempt.rail == "card" else "manual_action_required",
        actor_user_id=actor_id,
        actor_name_snapshot=actor_name,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    db.add(refund)
    await db.flush()
    settlement.refund_pending = money(settlement.refund_pending) + amount
    settlement.version += 1
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="refund_requested",
        idempotency_key=f"refund:{refund.id}:requested",
        actor=actor,
        refund_pending_delta=amount,
        evidence={"refund_id": str(refund.id), "mode": refund.mode},
    )
    db.add(ProviderOutboxEvent(
        tenant_id=tenant_id,
        event_type="payment_refund.provider_submit" if attempt.rail == "card" else "payment_refund.manual_task",
        aggregate_type="payment_refund",
        aggregate_id=refund.id,
        payload={"refund_id": str(refund.id), "attempt_id": str(attempt.id), "amount": str(amount)},
        idempotency_key=f"refund:{refund.id}:{attempt.provider}:{attempt.provider_account_id or 'manual'}",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=datetime.now(timezone.utc),
    ))
    return refund


async def confirm_manual_refund(
    db: AsyncSession,
    *,
    refund_id: UUID,
    tenant_id: UUID,
    actor: CurrentUser,
    reference: str,
    idempotency_key: str,
) -> PaymentRefund:
    refund = (
        await db.execute(
            select(PaymentRefund)
            .where(PaymentRefund.id == refund_id, PaymentRefund.tenant_id == tenant_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not refund:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if refund.state == "succeeded":
        return refund
    if refund.state != "manual_action_required":
        raise SettlementDomainError("refund_in_progress", "This refund cannot be manually confirmed.")
    settlement = (
        await db.execute(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == refund.invoice_id).with_for_update())
    ).scalar_one()
    attempt = await db.get(InvoicePaymentAttempt, refund.source_attempt_id)
    refund.state = "succeeded"
    refund.provider_reference = reference.strip()
    refund.completed_at = datetime.now(timezone.utc)
    settlement.refund_pending = max(ZERO, money(settlement.refund_pending) - money(refund.amount))
    settlement.unapplied_credit = max(ZERO, money(settlement.unapplied_credit) - money(refund.amount))
    settlement.version += 1
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=attempt,
        event_type="refund_succeeded",
        idempotency_key=f"manual-refund:{idempotency_key}",
        actor=actor,
        unapplied_delta=-money(refund.amount),
        refund_pending_delta=-money(refund.amount),
        evidence={"refund_id": str(refund.id), "reference_present": True},
    )
    config = (await db.execute(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant_id,
        TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version,
    ))).scalar_one()
    link = PaymentAccountingLink(
        tenant_id=tenant_id,
        invoice_id=refund.invoice_id,
        attempt_id=attempt.id,
        refund_id=refund.id,
        financial_object_type="invoice_refund",
        financial_object_id=refund.id,
        operation_version=1,
        owning_writer=config.writer_strategy,
        account_mapping_snapshot=_configuration_mappings(config),
        qbo_realm_snapshot=config.qbo_realm_snapshot,
        sync_state="pending",
    )
    db.add(link)
    await db.flush()
    db.add(ProviderOutboxEvent(
        tenant_id=tenant_id,
        event_type="invoice_refund.accounting_sync",
        aggregate_type="payment_refund",
        aggregate_id=refund.id,
        payload={
            "accounting_link_id": str(link.id),
            "attempt_id": str(attempt.id),
            "invoice_id": str(refund.invoice_id),
            "refund_id": str(refund.id),
        },
        idempotency_key=f"invoice-refund:{refund.id}:accounting:v1",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=datetime.now(timezone.utc),
    ))
    return refund


async def record_credit_consent(
    db: AsyncSession,
    *,
    overpayment_id: UUID,
    tenant_id: UUID,
    actor: Optional[CurrentUser],
    subject_customer_id: UUID,
    channel: str,
    note: str,
    idempotency_key: str,
) -> CustomerCreditEntry:
    requested_channel = channel.strip()
    if actor is None:
        if requested_channel != "guest_token":
            raise SettlementDomainError(
                "consent_channel_invalid",
                "Guest consent must be recorded through an invoice token.",
                status_code=422,
            )
        channel = "guest_token"
    elif actor.role == UserRole.CUSTOMER:
        if (
            actor.tenant_id != tenant_id
            or actor.customer_id != subject_customer_id
            or requested_channel != "customer_portal"
        ):
            raise SettlementDomainError(
                "consent_channel_invalid",
                "Customer consent must be recorded through the customer portal.",
                status_code=422,
            )
        channel = "customer_portal"
    elif (
        actor.tenant_id == tenant_id
        and actor.role in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN}
        and user_has_permission(actor, "payments")
    ):
        if requested_channel not in {"in_person", "phone"}:
            raise SettlementDomainError(
                "consent_channel_invalid",
                "Staff consent evidence must be recorded as in-person or phone.",
                status_code=422,
            )
        channel = requested_channel
    else:
        raise SettlementDomainError(
            "invoice_not_found",
            "Invoice not found.",
            status_code=404,
        )
    note = note.strip()
    request_hash = _canonical_hash({
        "operation": "credit_consent",
        "overpayment_id": str(overpayment_id),
        "customer_id": str(subject_customer_id),
        "channel": channel,
        "note": note,
    })
    overpayment = (
        await db.execute(
            select(PaymentOverpayment)
            .where(
                PaymentOverpayment.id == overpayment_id,
                PaymentOverpayment.tenant_id == tenant_id,
                PaymentOverpayment.customer_id == subject_customer_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not overpayment:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    existing = (
        await db.execute(select(CustomerCreditEntry).where(CustomerCreditEntry.tenant_id == tenant_id, CustomerCreditEntry.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing:
        if existing.request_hash != request_hash:
            raise SettlementDomainError(
                "idempotency_conflict",
                "The Idempotency-Key was already used with a different request.",
                status_code=409,
            )
        return existing
    source_attempt = (
        await db.execute(
            select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.id == overpayment.source_attempt_id,
                InvoicePaymentAttempt.tenant_id == tenant_id,
                InvoicePaymentAttempt.invoice_id == overpayment.invoice_id,
            )
        )
    ).scalar_one_or_none()
    if source_attempt is None:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    principal_excess = max(
        ZERO,
        money(source_attempt.received_amount)
        - money(source_attempt.applied_principal_amount),
    )
    forced_provider_refund = max(
        ZERO,
        money(source_attempt.unapplied_amount) - principal_excess,
    )
    if source_attempt.rail == "card" and forced_provider_refund > ZERO:
        raise SettlementDomainError(
            "refund_required",
            "The unearned card surcharge and tax must be refunded to the original card.",
        )
    refund = (
        await db.execute(select(PaymentRefund).where(PaymentRefund.overpayment_id == overpayment.id).with_for_update())
    ).scalar_one_or_none()
    if refund and refund.state == "succeeded":
        raise SettlementDomainError("refund_already_submitted", "Refunded money cannot be converted to store credit.")
    if refund and refund.mode == "automatic" and refund.provider_reference:
        raise SettlementDomainError("refund_already_submitted", "The provider already accepted this refund.")
    refund_outbox = None
    if refund:
        refund_outbox = (
            await db.execute(select(ProviderOutboxEvent).where(
                ProviderOutboxEvent.tenant_id == tenant_id,
                ProviderOutboxEvent.aggregate_type == "payment_refund",
                ProviderOutboxEvent.aggregate_id == refund.id,
                ProviderOutboxEvent.event_type.in_([
                    "payment_refund.provider_submit",
                    "payment_refund.manual_task",
                ]),
            ).with_for_update())
        ).scalar_one_or_none()
        if refund_outbox and refund_outbox.status in {
            "processing",
            ProviderOutboxStatus.SUCCEEDED.value,
        }:
            raise SettlementDomainError(
                "refund_already_submitted",
                "The refund is already being processed and cannot become store credit.",
            )
    settlement = (
        await db.execute(select(InvoiceSettlement).where(InvoiceSettlement.id == overpayment.settlement_id).with_for_update())
    ).scalar_one()
    actor_id, actor_name, _ = _actor_snapshot(actor, fallback="Customer")
    entry = CustomerCreditEntry(
        tenant_id=tenant_id,
        customer_id=overpayment.customer_id,
        entry_type="issued",
        amount=overpayment.amount,
        origin_overpayment_id=overpayment.id,
        actor_user_id=actor_id,
        actor_name_snapshot=actor_name,
        consent_channel=channel,
        consent_note=note,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    db.add(entry)
    overpayment.state = "credited"
    overpayment.consent_channel = channel
    overpayment.consent_note = note
    overpayment.consent_actor_user_id = actor_id
    overpayment.consented_at = datetime.now(timezone.utc)
    overpayment.resolved_at = overpayment.consented_at
    if refund and refund.state in {"pending", "manual_action_required", "failed"}:
        refund.state = "cancelled"
        settlement.refund_pending = max(ZERO, money(settlement.refund_pending) - money(refund.amount))
        if refund_outbox and refund_outbox.status in {
            ProviderOutboxStatus.PENDING.value,
            ProviderOutboxStatus.DEAD.value,
        }:
            refund_outbox.status = ProviderOutboxStatus.EXPIRED.value
            refund_outbox.completed_at = datetime.now(timezone.utc)
            refund_outbox.last_error = "Cancelled after explicit customer store-credit consent"
    settlement.unapplied_credit = max(ZERO, money(settlement.unapplied_credit) - money(overpayment.amount))
    settlement.version += 1
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        attempt=await db.get(InvoicePaymentAttempt, overpayment.source_attempt_id),
        event_type="credit_consent_recorded",
        idempotency_key=f"credit:{entry.id}:consent",
        actor=actor,
        evidence={"channel": channel, "note_present": True, "overpayment_id": str(overpayment.id)},
    )
    await append_ledger_event(
        db,
        settlement=settlement,
        event_type="credit_issued",
        idempotency_key=f"credit:{entry.id}:issued",
        actor=actor,
        unapplied_delta=-money(overpayment.amount),
        evidence={"credit_id": str(entry.id)},
    )
    return entry


async def available_credit(db: AsyncSession, tenant_id: UUID, customer_id: UUID) -> Decimal:
    # Availability belongs to each immutable issued origin.  A `reversed`
    # entry linked to an application is audit evidence that the target invoice
    # was reopened; it is deliberately neutral here.  Only entries linked
    # directly to the issued origin consume its wallet balance.
    origins = (
        await db.execute(select(CustomerCreditEntry).where(
            CustomerCreditEntry.tenant_id == tenant_id,
            CustomerCreditEntry.customer_id == customer_id,
            CustomerCreditEntry.entry_type == "issued",
        ))
    ).scalars().all()
    total = ZERO
    for origin in origins:
        used = await db.scalar(select(func.coalesce(func.sum(CustomerCreditEntry.amount), 0)).where(
            CustomerCreditEntry.tenant_id == tenant_id,
            CustomerCreditEntry.customer_id == customer_id,
            CustomerCreditEntry.source_entry_id == origin.id,
            CustomerCreditEntry.entry_type.in_(["applied", "refunded", "reversed"]),
        ))
        total = money(total + max(ZERO, money(origin.amount) - money(used)))
    return total


async def apply_customer_credit(
    db: AsyncSession,
    *,
    credit_id: UUID,
    invoice: Invoice,
    tenant: Tenant,
    customer_id: UUID,
    amount: Decimal,
    expected_settlement_version: int,
    actor: Optional[CurrentUser],
    idempotency_key: str,
) -> tuple[CustomerCreditEntry, InvoiceSettlement]:
    amount = money(amount)
    request_hash = _canonical_hash({
        "operation": "credit_application",
        "credit_id": str(credit_id),
        "invoice_id": str(invoice.id),
        "customer_id": str(customer_id),
        "amount": str(amount),
        "expected_settlement_version": expected_settlement_version,
    })
    existing = (
        await db.execute(select(CustomerCreditEntry).where(
            CustomerCreditEntry.tenant_id == tenant.id,
            CustomerCreditEntry.idempotency_key == idempotency_key,
        ))
    ).scalar_one_or_none()
    settlement = await get_or_create_settlement(db, invoice=invoice, customer_id=customer_id, tenant=tenant, lock=True)
    from app.services.invoice_accounting_policy import require_standard_payment
    await require_standard_payment(db, invoice)
    if existing:
        if existing.request_hash != request_hash:
            raise SettlementDomainError(
                "idempotency_conflict",
                "The Idempotency-Key was already used with a different request.",
                status_code=409,
            )
        return existing, settlement
    origin = (
        await db.execute(
            select(CustomerCreditEntry).where(
                CustomerCreditEntry.id == credit_id,
                CustomerCreditEntry.tenant_id == tenant.id,
                CustomerCreditEntry.customer_id == customer_id,
                CustomerCreditEntry.entry_type == "issued",
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if not origin:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if amount < CENT:
        raise SettlementDomainError("payment_amount_invalid", "The credit amount must be at least $0.01.", status_code=422)
    used_from_origin = (
        await db.execute(
            select(func.coalesce(func.sum(CustomerCreditEntry.amount), 0)).where(
                CustomerCreditEntry.tenant_id == tenant.id,
                CustomerCreditEntry.customer_id == customer_id,
                CustomerCreditEntry.source_entry_id == origin.id,
                CustomerCreditEntry.entry_type.in_(["applied", "refunded", "reversed"]),
            )
        )
    ).scalar_one()
    origin_remaining = max(ZERO, money(origin.amount) - money(used_from_origin))
    if amount > origin_remaining:
        raise SettlementDomainError("insufficient_credit", "The requested store credit is not available.")
    if settlement.version != expected_settlement_version:
        raise SettlementDomainError("stale_settlement_version", "The invoice balance changed.", retryable=True, current_version=settlement.version)
    if amount > allocatable_balance(settlement):
        raise SettlementDomainError("payment_amount_exceeds_allocatable_balance", "The requested amount is no longer available to pay.", retryable=True, current_version=settlement.version)
    overpayment = await db.scalar(select(PaymentOverpayment).where(
        PaymentOverpayment.id == origin.origin_overpayment_id,
        PaymentOverpayment.tenant_id == tenant.id,
        PaymentOverpayment.customer_id == customer_id,
    ))
    source_attempt = await db.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.id == (overpayment.source_attempt_id if overpayment else None),
        InvoicePaymentAttempt.tenant_id == tenant.id,
        InvoicePaymentAttempt.state == "confirmed",
    ))
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant.id,
        TenantPaymentProviderConfiguration.version == (
            source_attempt.provider_configuration_version if source_attempt else None
        ),
    ))
    if not overpayment or not source_attempt or not config:
        raise SettlementDomainError(
            "credit_accounting_source_missing",
            "The customer credit accounting source is unavailable.",
        )
    source_invoice = await db.scalar(select(Invoice).where(
        Invoice.id == source_attempt.invoice_id, Invoice.tenant_id == tenant.id))
    if source_invoice is None:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    await require_standard_payment(db, source_invoice)
    # A customer credit remains accounting money from its original receipt.
    # Applying it to another invoice cannot move that invoice into a different
    # QuickBooks company.
    await bind_settlement_accounting_realm(
        db, settlement=settlement, config=config,
    )
    actor_id, actor_name, _ = _actor_snapshot(actor, fallback="Customer")
    applied = CustomerCreditEntry(
        tenant_id=tenant.id,
        customer_id=customer_id,
        entry_type="applied",
        amount=amount,
        target_invoice_id=invoice.id,
        source_entry_id=origin.id,
        actor_user_id=actor_id,
        actor_name_snapshot=actor_name,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    db.add(applied)
    # ``PaymentAccountingLink.financial_object_id`` is immutable and
    # non-null.  Materialize the credit-entry UUID before constructing the
    # link so both SQLite-focused tests and PostgreSQL enforce the same
    # append-only identity contract.
    await db.flush()
    prior_state = settlement.state
    settlement.confirmed_principal = money(settlement.confirmed_principal) + amount
    settlement.version += 1
    paid_transition = money(settlement.confirmed_principal) >= money(settlement.principal_total) and invoice.status != InvoiceStatus.PAID
    if paid_transition:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = invoice.paid_at or datetime.now(timezone.utc)
        invoice.repair_order.status = RepairOrderStatus.PAID
        await enqueue_paid_invoice_webhook(
            db,
            tenant=tenant,
            invoice=invoice,
            order=invoice.repair_order,
            customer=invoice.repair_order.customer,
        )
    settlement.state = settlement_state(settlement)
    await append_ledger_event(
        db,
        settlement=settlement,
        event_type="credit_applied",
        idempotency_key=f"credit-application:{idempotency_key}",
        actor=actor,
        prior_state=prior_state,
        new_state=settlement.state,
        principal_delta=amount,
        evidence={"credit_id": str(origin.id), "target_invoice_id": str(invoice.id)},
    )
    link = PaymentAccountingLink(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        attempt_id=source_attempt.id,
        financial_object_type="customer_credit_application",
        financial_object_id=applied.id,
        operation_version=1,
        owning_writer=config.writer_strategy,
        account_mapping_snapshot=_configuration_mappings(config),
        qbo_realm_snapshot=config.qbo_realm_snapshot,
        sync_state="pending",
    )
    db.add(link)
    await db.flush()
    db.add(ProviderOutboxEvent(
        tenant_id=tenant.id,
        event_type="customer_credit.accounting_sync",
        aggregate_type="customer_credit_entry",
        aggregate_id=applied.id,
        payload={
            "accounting_link_id": str(link.id),
            "credit_entry_id": str(applied.id),
            "origin_credit_id": str(origin.id),
            "invoice_id": str(invoice.id),
            "source_attempt_id": str(source_attempt.id),
            "amount": str(amount),
        },
        idempotency_key=f"credit-application:{applied.id}:accounting:v1",
        status=ProviderOutboxStatus.PENDING.value,
        available_at=datetime.now(timezone.utc),
    ))
    settlement.accounting_sync_status = "accounting_sync_pending"
    return applied, settlement


async def expire_due_attempts(db: AsyncSession, *, tenant_id: Optional[UUID] = None, limit: int = 100) -> int:
    now = datetime.now(timezone.utc)
    query = select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.state == "pending",
        InvoicePaymentAttempt.expires_at.is_not(None),
        InvoicePaymentAttempt.expires_at <= now,
        # A card reservation may only be released after checking the
        # authoritative provider state.  Card expiry is reconciled by the
        # provider worker; this local expiry path is intentionally limited to
        # manual rails whose state DieselBridge owns.
        InvoicePaymentAttempt.rail != "card",
    )
    if tenant_id:
        query = query.where(InvoicePaymentAttempt.tenant_id == tenant_id)
    attempts = (
        await db.execute(
            query.order_by(InvoicePaymentAttempt.expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    count = 0
    for attempt in attempts:
        settlement = (
            await db.execute(select(InvoiceSettlement).where(InvoiceSettlement.id == attempt.settlement_id).with_for_update())
        ).scalar_one()
        if attempt.state != "pending":
            continue
        prior = settlement.state
        settlement.active_pending_principal = max(ZERO, money(settlement.active_pending_principal) - money(attempt.principal_amount))
        settlement.version += 1
        attempt.state = "expired"
        attempt.failure_code = "reservation_expired"
        attempt.failed_at = now
        attempt.version += 1
        settlement.state = settlement_state(settlement)
        await append_ledger_event(
            db,
            settlement=settlement,
            attempt=attempt,
            event_type="payment_expired",
            idempotency_key=f"attempt:{attempt.id}:expired",
            actor=None,
            prior_state=prior,
            new_state=settlement.state,
            pending_delta=-money(attempt.principal_amount),
        )
        count += 1
    return count


async def authorize_early_release(
    db: AsyncSession,
    *,
    invoice: Invoice,
    tenant: Tenant,
    actor: CurrentUser,
    reason: str,
    expected_settlement_version: int,
    idempotency_key: str,
) -> InvoiceSettlement:
    if actor.role not in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN} or not user_has_permission(actor, "payments"):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    settlement = await get_or_create_settlement(
        db,
        invoice=invoice,
        customer_id=invoice.repair_order.customer_id,
        tenant=tenant,
        lock=True,
    )
    event_key = f"release:{idempotency_key}"
    existing = await db.scalar(select(InvoicePaymentLedgerEvent.id).where(
        InvoicePaymentLedgerEvent.tenant_id == tenant.id,
        InvoicePaymentLedgerEvent.invoice_id == invoice.id,
        InvoicePaymentLedgerEvent.idempotency_key == event_key,
    ).limit(1))
    if existing:
        return settlement
    if settlement.version != expected_settlement_version:
        raise SettlementDomainError("stale_settlement_version", "The invoice balance changed.", current_version=settlement.version)
    outstanding = max(
        ZERO,
        money(settlement.principal_total) - money(settlement.confirmed_principal),
    )
    if outstanding > ZERO and not reason.strip():
        raise SettlementDomainError("release_override_reason_required", "A release reason is required.", status_code=422)
    order = await db.scalar(select(RepairOrder).where(
        RepairOrder.id == invoice.repair_order_id,
        RepairOrder.tenant_id == tenant.id,
    ).with_for_update())
    if not order:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if order.vehicle_released_at is not None:
        raise SettlementDomainError(
            "vehicle_already_released",
            "This vehicle release was already recorded.",
        )
    released_at = datetime.now(timezone.utc)
    order.vehicle_released_at = released_at
    order.vehicle_released_by_user_id = identity_user(actor).id
    order.vehicle_release_reason = reason.strip()[:1000] or "Invoice paid in full"
    prior_state = settlement.state
    settlement.version += 1
    await append_ledger_event(
        db,
        settlement=settlement,
        event_type=("vehicle_release_override" if outstanding > ZERO else "vehicle_released"),
        idempotency_key=event_key,
        actor=actor,
        prior_state=prior_state,
        new_state=settlement.state,
        evidence={
            "reason": order.vehicle_release_reason,
            "outstanding_balance": str(outstanding),
            "released_at": released_at.isoformat(),
        },
    )
    return settlement
