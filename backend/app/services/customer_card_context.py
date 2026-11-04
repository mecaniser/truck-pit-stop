"""Selected-processor admission for customer vaults, independent of invoices."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.core.quickbooks_payment_gate import quickbooks_payments_enabled_for_tenant
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.invoice_settlement import TenantPaymentProviderConfiguration
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.quickbooks_shop_activation import QuickBooksShopActivation
from app.services.financial_transaction_lock import lock_tenant_financials

UNAVAILABLE = 'Saved cards are not available for this shop right now. Please contact the shop.'
PENDING = 'We could not confirm whether your card was saved. Please contact the shop before trying again.'


@dataclass(frozen=True)
class CardContext:
    customer: Customer
    tenant: Tenant
    config: TenantPaymentProviderConfiguration
    provider: str
    account: str
    environment: str
    key: str
    connection: QuickBooksConnection | None = None
    principal: Any = None


def unavailable():
    raise HTTPException(status_code=409, detail=UNAVAILABLE)


def _expired(value):
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= datetime.now(timezone.utc)


async def _scalar(db, query):
    return await db.scalar(query.execution_options(populate_existing=True))


async def resolve_card_context(db, user, *, expected=None, lock=False):
    if user.role != UserRole.CUSTOMER or not user.customer_id or not user.tenant_id:
        raise HTTPException(status_code=403, detail='Only customers can manage saved cards')
    if lock:
        await lock_tenant_financials(db, user.tenant_id)
    query = select(Customer).where(
        Customer.id == user.customer_id, Customer.tenant_id == user.tenant_id,
        Customer.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    customer = await _scalar(db, query)
    if customer is None:
        raise HTTPException(status_code=404, detail='Customer not found')
    tenant = await _scalar(db, select(Tenant).where(
        Tenant.id == user.tenant_id, Tenant.is_active.is_(True), Tenant.deleted_at.is_(None),
    ))
    config = await _scalar(db, select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == user.tenant_id,
        TenantPaymentProviderConfiguration.is_active.is_(True),
        TenantPaymentProviderConfiguration.deleted_at.is_(None),
    ))
    if tenant is None or config is None:
        unavailable()
    connection = activation = None
    if config.selected_provider == 'stripe_connect':
        if (not tenant.stripe_account_id or not tenant.stripe_onboarding_complete
                or config.provider_account_snapshot != tenant.stripe_account_id):
            unavailable()
        account = tenant.stripe_account_id
        secret = settings.STRIPE_SECRET_KEY
        if secret.startswith(('sk_test_', 'rk_test_')):
            environment = 'test'
        elif secret.startswith(('sk_live_', 'rk_live_')):
            environment = 'live'
        else:
            unavailable()
    elif config.selected_provider == 'quickbooks_payments':
        if not quickbooks_payments_enabled_for_tenant(tenant.id):
            unavailable()
        connection = await _scalar(db, select(QuickBooksConnection).where(
            QuickBooksConnection.tenant_id == tenant.id, QuickBooksConnection.deleted_at.is_(None),
        ))
        environment = settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower()
        if (environment not in {'sandbox', 'production'} or connection is None
                or connection.status != 'connected' or not connection.realm_id
                or not connection.encrypted_access_token or not connection.encrypted_refresh_token
                or 'com.intuit.quickbooks.payment' not in (connection.scopes or '').split()
                or config.provider_account_snapshot != connection.realm_id
                or config.qbo_realm_snapshot != connection.realm_id
                or _expired(getattr(connection, 'refresh_token_expires_at', None))):
            unavailable()
        activation = await _scalar(db, select(QuickBooksShopActivation).where(
            QuickBooksShopActivation.tenant_id == tenant.id,
        ))
        if activation is not None and (
            not activation.enabled or not activation.activated_at
            or activation.realm_id != connection.realm_id or activation.environment != environment
            or activation.writer != config.writer_strategy
        ):
            unavailable()
        account = connection.realm_id
    else:
        unavailable()
    # Credential refreshes do not change identity. Reconnection, selection,
    # account/environment or activation changes invalidate an open card form.
    identity = [user.id, user.tenant_id, user.customer_id, config.id, config.version,
                config.selected_provider, account, environment]
    if connection is not None:
        identity += [getattr(connection, 'id', None), getattr(connection, 'connected_at', None)]
    else:
        identity += [settings.STRIPE_PUBLISHABLE_KEY]
    if activation is not None:
        identity += [activation.id, activation.version, activation.activated_at]
    digest = sha256('|'.join(map(str, identity)).encode()).hexdigest()
    if expected is not None and digest != expected:
        raise HTTPException(status_code=409, detail='Card settings changed. Refresh before trying again.')
    return CardContext(customer, tenant, config, config.selected_provider, account,
                       environment, digest, connection, user)
