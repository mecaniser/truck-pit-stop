"""Provider I/O for booking prepayments; never writes a booking or a receipt.

Only opaque Intuit tokens or Stripe Elements intents cross this boundary. The
caller durably reserves its attempt/idempotency binding before calling create.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import asyncio
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
import stripe

from app.core.config import settings
from app.core.quickbooks_payment_gate import quickbooks_payments_enabled_for_tenant
from app.db.models.invoice_settlement import TenantPaymentProviderConfiguration
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.tenant import Tenant
from app.services import quickbooks_payments_service as qbp


class BookingProviderError(RuntimeError):
    def __init__(self, message: str, *, outcome_unknown: bool = False, code: str = 'booking_payment_unavailable', provider_id: str | None = None):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown
        self.code = code
        self.provider_id = provider_id


@dataclass(frozen=True)
class BookingProviderBinding:
    provider: str
    account_id: str
    configuration_version: int
    environment: str
    tenant_id: UUID


@dataclass(frozen=True)
class BookingProviderCapability:
    available: bool = False
    binding: BookingProviderBinding | None = None
    token_url: str | None = None
    message: str = 'Online reservations are unavailable. You can request a visit.'
    reason_code: str | None = 'booking_payment_unavailable'


@dataclass(frozen=True)
class BookingProviderResult:
    state: str
    provider_id: str
    charge_id: str | None
    amount_received_minor: int
    currency: str
    paid_at: datetime | None
    client_secret: str | None
    proof_digest: str
    metadata: dict[str, str]
    environment: str
    amount_minor: int = 0


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _booking_admitted(tenant_id: UUID) -> bool:
    if not getattr(settings, 'BOOKING_PAYMENTS_ENABLED', False):
        return False
    raw = getattr(settings, 'BOOKING_PAYMENTS_APPROVED_TENANT_IDS', '').strip()
    if not raw:
        return settings.ENVIRONMENT.strip().lower() != 'production'
    try:
        return tenant_id in {UUID(value.strip()) for value in raw.split(',')}
    except (ValueError, TypeError):
        return False


def _stripe_environment() -> str | None:
    key = settings.STRIPE_SECRET_KEY or ''
    if key.startswith(('sk_test_', 'rk_test_')):
        return 'sandbox'
    if key.startswith(('sk_live_', 'rk_live_')):
        return 'production'
    return None


def _environment_admitted(environment: str) -> bool:
    expected = 'production' if settings.ENVIRONMENT.strip().lower() == 'production' else 'sandbox'
    return environment == expected


async def _connection(db, tenant_id: UUID) -> QuickBooksConnection | None:
    return await db.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant_id,
        QuickBooksConnection.deleted_at.is_(None),
    ))


def _healthy_qbo(connection: QuickBooksConnection | None) -> bool:
    now = datetime.now(timezone.utc)
    return bool(connection and connection.status == 'connected' and connection.realm_id
        and connection.encrypted_access_token and connection.encrypted_refresh_token
        and 'com.intuit.quickbooks.payment' in (connection.scopes or '').split()
        and connection.access_token_expires_at and _utc(connection.access_token_expires_at) > now
        and connection.refresh_token_expires_at and _utc(connection.refresh_token_expires_at) > now)


async def booking_provider_capability(db, tenant: Tenant) -> BookingProviderCapability:
    if not tenant or not tenant.is_active or tenant.deleted_at is not None or not _booking_admitted(tenant.id):
        return BookingProviderCapability()
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant.id,
        TenantPaymentProviderConfiguration.is_active.is_(True),
        TenantPaymentProviderConfiguration.deleted_at.is_(None),
    ))
    if not config or config.readiness_state != 'ready' or config.writer_strategy != 'dieselbridge':
        return BookingProviderCapability(reason_code='booking_provider_not_ready')
    if config.selected_provider == 'quickbooks_payments':
        environment = settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower()
        connection = await _connection(db, tenant.id)
        if (not quickbooks_payments_enabled_for_tenant(tenant.id) or environment not in {'sandbox', 'production'}
            or not _environment_admitted(environment)
            or not _healthy_qbo(connection) or str(connection.realm_id) != config.provider_account_snapshot
            or str(connection.realm_id) != config.qbo_realm_snapshot):
            return BookingProviderCapability(reason_code='booking_provider_not_ready')
        binding = BookingProviderBinding('quickbooks_payments', str(connection.realm_id), config.version, environment, tenant.id)
        return BookingProviderCapability(True, binding, f'{qbp.payments_base_url()}/quickbooks/v4/payments/tokens', 'Online reservations are available.', None)
    if config.selected_provider == 'stripe_connect':
        environment = _stripe_environment()
        if (not settings.STRIPE_CONNECT_INVOICE_PAYMENTS_APPROVED or not settings.STRIPE_CONNECT_WEBHOOK_SECRET
            or not tenant.stripe_onboarding_complete or not tenant.stripe_account_id
            or config.provider_account_snapshot != tenant.stripe_account_id or not environment
            or not _environment_admitted(environment)):
            return BookingProviderCapability(reason_code='booking_provider_not_ready')
        return BookingProviderCapability(True, BookingProviderBinding('stripe_connect', tenant.stripe_account_id, config.version, environment, tenant.id), None, 'Online reservations are available.', None)
    return BookingProviderCapability(reason_code='booking_provider_not_ready')


async def _bound_configuration(db, binding: BookingProviderBinding, *, new_charge: bool):
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == binding.tenant_id,
        TenantPaymentProviderConfiguration.version == binding.configuration_version,
        TenantPaymentProviderConfiguration.deleted_at.is_(None),
    ))
    if (not config or config.selected_provider != binding.provider or config.provider_account_snapshot != binding.account_id
        or (new_charge and (not config.is_active or config.readiness_state != 'ready' or config.writer_strategy != 'dieselbridge'
                            or not _booking_admitted(binding.tenant_id) or not _environment_admitted(binding.environment)))):
        raise BookingProviderError('Online payment is unavailable for this reservation.')
    return config


def _metadata(metadata: dict[str, str], binding: BookingProviderBinding) -> dict[str, str]:
    required = {'purpose', 'tenant_id', 'customer_id', 'appointment_id', 'booking_payment_attempt_id', 'price_snapshot_sha256'}
    if (not required.issubset(metadata) or metadata.get('purpose') != 'booking_prepayment_v1'
        or metadata.get('tenant_id') != str(binding.tenant_id) or any(not isinstance(value, str) or not value for value in metadata.values())):
        raise BookingProviderError('The payment identity could not be verified.')
    return {**metadata, 'provider_account_id': binding.account_id}


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def _description(metadata: dict[str, str]) -> str:
    return f"Booking prepayment {metadata['booking_payment_attempt_id']} {_digest(metadata)}"


def _minor(amount: Any) -> int:
    try:
        number = Decimal(str(amount))
        if not number.is_finite() or number < 0 or number * 100 != (number * 100).to_integral_value():
            raise ValueError
        return int(number * 100)
    except (InvalidOperation, ValueError, TypeError):
        raise BookingProviderError('Payment evidence could not be verified.', outcome_unknown=True) from None


def _provider_time(value: Any) -> datetime:
    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, (int, float)):
            moment = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, str):
            moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if moment.tzinfo is None:
                raise ValueError
            moment = moment.astimezone(timezone.utc)
        else:
            raise ValueError
        if moment.timestamp() <= 0 or moment.timestamp() > datetime.now(timezone.utc).timestamp() + 300:
            raise ValueError
        return moment
    except (ValueError, OverflowError, OSError):
        raise BookingProviderError('Payment receipt time could not be verified.', outcome_unknown=True) from None


def _stripe_create_options(binding, amount_minor, metadata, idempotency_key):
    return dict(api_key=settings.STRIPE_SECRET_KEY, amount=amount_minor, currency='usd', metadata=metadata,
                payment_method_types=['card'], capture_method='automatic',
                stripe_account=binding.account_id, idempotency_key=idempotency_key)


def _stripe_result(intent: Any, binding: BookingProviderBinding, metadata: dict[str, str]) -> BookingProviderResult:
    obj = dict(intent)
    if (not isinstance(obj.get('id'), str) or obj.get('metadata') != metadata
        or obj.get('livemode') is not (binding.environment == 'production') or obj.get('currency') != 'usd'
        or isinstance(obj.get('amount'), bool) or not isinstance(obj.get('amount'), int)):
        raise BookingProviderError('Payment evidence could not be verified.', outcome_unknown=True)
    state = str(obj.get('status', 'processing'))
    if state == 'canceled':
        state = 'cancelled'
    charge = obj.get('latest_charge')
    charge_id = charge if isinstance(charge, str) else charge.get('id') if isinstance(charge, dict) else None
    received = obj.get('amount_received')
    if isinstance(received, bool) or not isinstance(received, int) or received < 0:
        raise BookingProviderError('Payment evidence could not be verified.', outcome_unknown=True)
    if (state == 'cancelled' and received != 0) or (state == 'succeeded' and (not charge_id or received != obj['amount'])):
        raise BookingProviderError('Payment evidence could not be verified.', outcome_unknown=True)
    paid_at = None
    if state == 'succeeded':
        if (not isinstance(charge, dict) or charge.get('payment_intent') != obj['id'] or charge.get('currency') != 'usd'
            or charge.get('captured') is not True or charge.get('paid') is not True or charge.get('amount_captured') != received
            or charge.get('livemode') is not (binding.environment == 'production')):
            raise BookingProviderError('Payment charge evidence could not be verified.', outcome_unknown=True)
        paid_at = _provider_time(charge.get('created'))
    return BookingProviderResult(state, obj['id'], charge_id, received, 'usd', paid_at,
        obj.get('client_secret'), _digest({k: obj.get(k) for k in ['id', 'status', 'amount', 'amount_received', 'currency', 'livemode', 'metadata', 'latest_charge']}), metadata, binding.environment, obj['amount'])


def _qbo_result(charge: qbp.QuickBooksCharge, binding: BookingProviderBinding, metadata: dict[str, str]) -> BookingProviderResult:
    raw = charge.raw
    if (not isinstance(raw, dict) or raw.get('id') != charge.id or raw.get('currency', '').lower() != 'usd'
        or raw.get('description') != _description(metadata)):
        raise BookingProviderError('Payment evidence could not be verified.', outcome_unknown=True)
    amount = _minor(raw.get('amount'))
    state = 'succeeded' if qbp.is_successful_charge(charge) else 'failed' if charge.status in {'DECLINED', 'FAILED', 'VOIDED', 'CANCELLED'} else 'processing'
    proof = {'id': charge.id, 'status': charge.status, 'amount_minor': amount, 'currency': 'usd', 'description': raw.get('description'), 'account': binding.account_id, 'environment': binding.environment, 'created': raw.get('created')}
    paid_at = _provider_time(raw.get('created')) if state == 'succeeded' else None
    return BookingProviderResult(state, charge.id, charge.id, amount if state == 'succeeded' else 0, 'usd', paid_at, None, _digest(proof), metadata, binding.environment, amount)


async def create_booking_payment(db, binding: BookingProviderBinding, *, amount_minor: int, currency: str,
                                 metadata: dict[str, str], idempotency_key: str, quickbooks_token: str | None = None) -> BookingProviderResult:
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor < 50 or currency != 'usd' or not idempotency_key:
        raise BookingProviderError('The reservation amount could not be verified.')
    await _bound_configuration(db, binding, new_charge=True)
    metadata = _metadata(metadata, binding)
    if binding.provider == 'quickbooks_payments':
        connection = await _connection(db, binding.tenant_id)
        if (not _healthy_qbo(connection) or str(connection.realm_id) != binding.account_id
            or settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower() != binding.environment
            or not quickbooks_payments_enabled_for_tenant(binding.tenant_id) or not quickbooks_token):
            raise BookingProviderError('Online payment is unavailable for this reservation.')
        charge = None
        try:
            charge = await qbp.create_charge(connection=connection, token=quickbooks_token,
                amount=Decimal(amount_minor) / 100, description=_description(metadata), request_id=idempotency_key)
            verified = await qbp.get_charge(connection=connection, charge_id=charge.id)
        except qbp.QuickBooksPaymentError as exc:
            raise BookingProviderError('Payment verification is pending. Please do not pay again.', outcome_unknown=charge is not None or exc.outcome_unknown, provider_id=charge.id if charge else None) from None
        if verified.id != charge.id:
            raise BookingProviderError('Payment evidence could not be verified.', outcome_unknown=True, provider_id=charge.id)
        try:
            result = _qbo_result(verified, binding, metadata)
        except BookingProviderError as exc:
            exc.provider_id = charge.id
            raise
    elif binding.provider == 'stripe_connect':
        if _stripe_environment() != binding.environment or not settings.STRIPE_CONNECT_INVOICE_PAYMENTS_APPROVED:
            raise BookingProviderError('Online payment is unavailable for this reservation.')
        started = False
        try:
            account = await asyncio.to_thread(stripe.Account.retrieve, binding.account_id, api_key=settings.STRIPE_SECRET_KEY)
            if not account.get('charges_enabled') or not account.get('payouts_enabled'):
                raise BookingProviderError('Online payment is unavailable for this reservation.')
            started = True
            intent = await asyncio.to_thread(stripe.PaymentIntent.create, **_stripe_create_options(binding, amount_minor, metadata, idempotency_key))
            try:
                result = _stripe_result(intent, binding, metadata)
            except BookingProviderError as exc:
                exc.provider_id = intent.get('id')
                raise
        except stripe.error.StripeError:
            raise BookingProviderError('Payment verification is pending. Please do not pay again.', outcome_unknown=started) from None
    else:
        raise BookingProviderError('Online payment is unavailable for this reservation.')
    if result.amount_minor != amount_minor or (result.state == 'succeeded' and result.amount_received_minor != amount_minor):
        raise BookingProviderError('Payment evidence could not be verified.', outcome_unknown=True, provider_id=result.provider_id)
    return result


async def retrieve_booking_payment(db, binding: BookingProviderBinding, provider_id: str, *, expected_metadata: dict[str, str]) -> BookingProviderResult:
    await _bound_configuration(db, binding, new_charge=False)
    metadata = _metadata(expected_metadata, binding)
    if not provider_id:
        raise BookingProviderError('Payment verification is pending.', outcome_unknown=True)
    if binding.provider == 'quickbooks_payments':
        connection = await _connection(db, binding.tenant_id)
        if (not _healthy_qbo(connection) or str(connection.realm_id) != binding.account_id
            or settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower() != binding.environment):
            raise BookingProviderError('Payment verification is pending.', outcome_unknown=True)
        try:
            result = _qbo_result(await qbp.get_charge(connection=connection, charge_id=provider_id), binding, metadata)
        except qbp.QuickBooksPaymentError:
            raise BookingProviderError('Payment verification is pending.', outcome_unknown=True) from None
    elif binding.provider == 'stripe_connect':
        if _stripe_environment() != binding.environment:
            raise BookingProviderError('Payment verification is pending.', outcome_unknown=True)
        try:
            intent = await asyncio.to_thread(stripe.PaymentIntent.retrieve, provider_id, api_key=settings.STRIPE_SECRET_KEY, stripe_account=binding.account_id, expand=['latest_charge'])
            try:
                result = _stripe_result(intent, binding, metadata)
            except BookingProviderError as exc:
                exc.provider_id = provider_id
                raise
        except stripe.error.StripeError:
            raise BookingProviderError('Payment verification is pending.', outcome_unknown=True) from None
    else:
        raise BookingProviderError('Payment verification is pending.', outcome_unknown=True)
    if result.provider_id != provider_id:
        raise BookingProviderError('Payment evidence could not be verified.', outcome_unknown=True, provider_id=provider_id)
    return result


async def cancel_unpaid_booking_payment(db, binding: BookingProviderBinding, provider_id: str, *,
                                       expected_metadata: dict[str, str], idempotency_key: str) -> BookingProviderResult:
    """Expiry may release capacity only after an authoritative unpaid outcome.

    QuickBooks charges are never voided/refunded here. Stripe cancellation is
    limited to an uncompleted intent and is reverified on a concurrent success.
    """
    current = await retrieve_booking_payment(db, binding, provider_id, expected_metadata=expected_metadata)
    if binding.provider != 'stripe_connect' or current.state not in {'requires_payment_method', 'requires_confirmation', 'requires_action'}:
        return current
    metadata = _metadata(expected_metadata, binding)
    try:
        intent = await asyncio.to_thread(stripe.PaymentIntent.cancel, provider_id,
            api_key=settings.STRIPE_SECRET_KEY, stripe_account=binding.account_id,
            cancellation_reason='abandoned', idempotency_key=idempotency_key)
        result = _stripe_result(intent, binding, metadata)
        if result.provider_id != provider_id:
            raise BookingProviderError('Payment verification is pending.', outcome_unknown=True, provider_id=provider_id)
        return result
    except stripe.error.StripeError:
        # A payment can complete while expiry is trying to cancel it. Only a
        # new server retrieval can establish whether capacity may be released.
        return await retrieve_booking_payment(db, binding, provider_id, expected_metadata=expected_metadata)


async def recover_created_booking_payment(db, binding: BookingProviderBinding, *, amount_minor: int, currency: str,
                                          metadata: dict[str, str], idempotency_key: str,
                                          attempt_created_at: datetime, expected_provider_id: str) -> BookingProviderResult:
    """Recover an interrupted intent creation using its original request identity.

    Stripe retains idempotency results for at least 24 hours. Within a stricter
    23-hour window the exact original *unconfirmed* create request can identify
    its canonical intent. Metadata alone never adopts a different paid intent.
    """
    age = (datetime.now(timezone.utc) - _utc(attempt_created_at)).total_seconds()
    if (binding.provider != 'stripe_connect' or not 0 <= age < 23 * 3600 or currency != 'usd'
        or amount_minor < 50 or not idempotency_key or not expected_provider_id
        or _stripe_environment() != binding.environment or not _environment_admitted(binding.environment)):
        raise BookingProviderError('Payment identity needs shop review.', outcome_unknown=True)
    await _bound_configuration(db, binding, new_charge=False)
    identity = _metadata(metadata, binding)
    try:
        canonical = await asyncio.to_thread(stripe.PaymentIntent.create, **_stripe_create_options(binding, amount_minor, identity, idempotency_key))
    except stripe.error.StripeError:
        raise BookingProviderError('Payment identity needs shop review.', outcome_unknown=True) from None
    if canonical.get('id') != expected_provider_id:
        raise BookingProviderError('Payment identity needs shop review.', outcome_unknown=True)
    return await retrieve_booking_payment(db, binding, expected_provider_id, expected_metadata=identity)
