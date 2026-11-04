"""Customer card orchestration; provider choice is server-owned, never a picker."""
from dataclasses import dataclass
from hashlib import sha256
import re
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import stripe

from app.db.models.customer_payment_profile import CustomerPaymentProfile, SavedCardOperation
from app.services.customer_card_context import resolve_card_context, unavailable, PENDING
from app.services import quickbooks_vault_client as vault

UNCONFIRMED = {'pending', 'unconfirmed'}
TEMPORARY = 'Saved cards are temporarily unavailable. Please try again.'


@dataclass(frozen=True)
class _OperationIdentity:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    profile_id: UUID


def _principal(user):
    # Rollback expires ORM fields. Request identity survives without lazy SQL.
    return SimpleNamespace(id=user.id, tenant_id=user.tenant_id,
                           customer_id=user.customer_id, role=user.role)


async def get_profile(db, context, *, create=False):
    query = select(CustomerPaymentProfile).where(
        CustomerPaymentProfile.tenant_id == context.tenant.id,
        CustomerPaymentProfile.customer_id == context.customer.id,
        CustomerPaymentProfile.provider == context.provider,
        CustomerPaymentProfile.provider_account_id == context.account,
        CustomerPaymentProfile.environment == context.environment,
        CustomerPaymentProfile.deleted_at.is_(None),
    )
    profile = await db.scalar(query.execution_options(populate_existing=True))
    if profile is None and create:
        profile = CustomerPaymentProfile(
            id=uuid4(), tenant_id=context.tenant.id, customer_id=context.customer.id,
            provider=context.provider, provider_account_id=context.account,
            environment=context.environment,
        )
        if context.provider == 'quickbooks_payments':
            # Cards API accepts an application-owned Payments customer identity.
            # This does not create or mutate a QBO accounting Customer.
            profile.provider_customer_id = f'dbv1_{profile.id.hex}'
        db.add(profile)
        await db.flush()
    return profile


async def pending_save(db, profile):
    if profile is None:
        return False
    return bool(await db.scalar(select(SavedCardOperation.id).where(
        SavedCardOperation.profile_id == profile.id,
        SavedCardOperation.state.in_(UNCONFIRMED), SavedCardOperation.deleted_at.is_(None),
    ).limit(1)))


async def refreshed_context(db, user, expected):
    principal = _principal(user)
    context = await resolve_card_context(db, principal, expected=expected, lock=True)
    if context.connection is not None:
        from app.api.v1.endpoints.quickbooks import _refresh_connection_if_needed
        await _refresh_connection_if_needed(db, context.connection)
        context = await resolve_card_context(db, principal, expected=expected, lock=True)
    return context


def card_view(card, default_id=None):
    return dict(id=card.id, brand=card.brand, last4=card.last4, exp_month=card.exp_month,
                exp_year=card.exp_year, is_default=card.id == default_id)


def stripe_customer_id(context, profile):
    return (profile.provider_customer_id if profile and profile.provider_customer_id
            else context.customer.stripe_customer_id)


async def list_customer_cards(db, context):
    if context.connection is not None:
        # Read operations can refresh an expiring OAuth credential, but never
        # create/repair a vault profile, accounting customer, card or charge.
        context = await refreshed_context(db, context.principal, context.key)
    profile = await get_profile(db, context)
    if context.provider == 'stripe_connect':
        cid = stripe_customer_id(context, profile)
        if not cid:
            return []
        try:
            methods = stripe.PaymentMethod.list(customer=cid, type='card', stripe_account=context.account)
            customer = stripe.Customer.retrieve(cid, stripe_account=context.account)
            if customer.get('deleted'):
                raise HTTPException(status_code=409, detail='Saved cards could not be loaded. Add a card to reconnect your payment profile.')
            default = customer.invoice_settings.default_payment_method
            return [dict(id=p.id, brand=p.card.brand, last4=p.card.last4, exp_month=p.card.exp_month,
                         exp_year=p.card.exp_year, is_default=p.id == default) for p in methods.data]
        except stripe.error.StripeError:
            raise HTTPException(status_code=409, detail='Saved cards could not be loaded. Add a card to reconnect your payment profile.') from None
    if profile is None:
        return []
    if not profile.provider_customer_id:
        # An existing incomplete binding is not proof of an empty provider vault.
        raise HTTPException(status_code=409, detail=PENDING if await pending_save(db, profile)
                            else 'Saved card ownership requires review. Please contact the shop.')
    try:
        cards = await vault.list_cards(
            connection=context.connection, environment=context.environment,
            customer_id=profile.provider_customer_id, request_id=f'wallet-list-{profile.id}',
        )
        return [card_view(card, profile.default_method_id) for card in cards]
    except vault.VaultError:
        raise HTTPException(status_code=503, detail='Saved cards could not be loaded. Please try again.') from None


async def prepare_stripe_card(db, user, expected, key):
    principal = _principal(user)
    context = await resolve_card_context(db, principal, expected=expected, lock=True)
    if context.provider != 'stripe_connect':
        unavailable()
    profile = await get_profile(db, context, create=True)
    if profile.provider_customer_id:
        # A bound vault owns its original customer even if another processor or
        # environment temporarily changed the legacy single-reference column.
        context.customer.stripe_customer_id = profile.provider_customer_id
        await db.flush()
    from app.services.stripe_customer_service import ensure_connected_stripe_customer
    cid = await ensure_connected_stripe_customer(db, context.customer, context.account)
    # The legacy helper may commit customer recovery. Recheck selection before
    # creating an intent and use only the matching provider/account profile.
    context = await resolve_card_context(db, principal, expected=expected, lock=True)
    profile = await get_profile(db, context, create=True)
    profile.provider_customer_id = cid
    await db.commit()
    context = await resolve_card_context(db, principal, expected=expected, lock=True)
    try:
        intent = stripe.SetupIntent.create(
            customer=cid, payment_method_types=['card'], stripe_account=context.account,
            idempotency_key='wallet-' + sha256(f'{context.key}:{key}'.encode()).hexdigest(),
        )
    except stripe.error.StripeError:
        raise HTTPException(status_code=503, detail='Unable to prepare your card. Please try again.') from None
    return {'client_secret': intent.client_secret, 'stripe_account_id': context.account}


def _receipt_predicate(identity):
    return (
        SavedCardOperation.id == identity.id,
        SavedCardOperation.tenant_id == identity.tenant_id,
        SavedCardOperation.customer_id == identity.customer_id,
        SavedCardOperation.profile_id == identity.profile_id,
    )


async def _record_outcome(db, identity, state, card_id=None):
    """Recover a local receipt safely after transaction/commit errors.

    No provider request is retried. Immutable IDs avoid expired ORM access;
    terminal receipts cannot be downgraded by uncertain commit acknowledgments.
    """
    try:
        await db.rollback()
        values = {'state': state}
        if card_id is not None:
            values['provider_card_id'] = card_id
        await db.execute(update(SavedCardOperation).where(
            *_receipt_predicate(identity), SavedCardOperation.state.in_(UNCONFIRMED),
        ).values(**values).execution_options(synchronize_session=False))
        await db.commit()
        return await db.scalar(select(SavedCardOperation.state).where(*_receipt_predicate(identity)))
    except SQLAlchemyError:
        await db.rollback()
        # The pre-dispatch pending receipt is durable. A future request sees the
        # hold rather than dispatching the token again under a new request ID.
        return None


def _token_hash(token):
    if (not isinstance(token, str) or not 1 <= len(token) <= 2048
            or re.sub(r'[^A-Za-z0-9]', '', token).isdigit() or not re.fullmatch(r'[A-Za-z0-9._~\-]+', token)):
        raise HTTPException(status_code=422, detail='A secure card token is required')
    return sha256(token.encode()).hexdigest()


async def save_quickbooks_card(db, user, expected, key, token):
    principal = _principal(user)
    context = await refreshed_context(db, principal, expected)
    if context.provider != 'quickbooks_payments':
        unavailable()
    token_hash = _token_hash(token)
    profile = await get_profile(db, context, create=True)
    if not profile.provider_customer_id:
        raise HTTPException(status_code=409, detail='Saved card ownership requires review. Please contact the shop.')
    existing = await db.scalar(select(SavedCardOperation).where(
        SavedCardOperation.profile_id == profile.id, SavedCardOperation.idempotency_key == key,
    ).execution_options(populate_existing=True))
    if existing is not None:
        if existing.context_key != context.key or existing.token_hash != token_hash:
            raise HTTPException(status_code=409, detail='This card save request has changed. Refresh before trying again.')
        if existing.state == 'confirmed':
            return {'status': 'saved'}
        if existing.state in UNCONFIRMED:
            raise HTTPException(status_code=409, detail=PENDING)
        raise HTTPException(status_code=409, detail='This card save request was not accepted. Start again with the card form.')
    if await pending_save(db, profile):
        raise HTTPException(status_code=409, detail=PENDING)
    operation = SavedCardOperation(
        id=uuid4(), tenant_id=context.tenant.id, customer_id=context.customer.id,
        profile_id=profile.id, context_key=context.key, idempotency_key=key,
        token_hash=token_hash, state='pending',
    )
    identity = _OperationIdentity(operation.id, operation.tenant_id, operation.customer_id, operation.profile_id)
    db.add(operation)
    try:
        await db.commit()  # Profile + request receipt precede the only vault POST.
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail='A card save request is already being checked. Refresh before trying again.') from None
    except SQLAlchemyError:
        await _record_outcome(db, identity, 'failed')
        raise HTTPException(status_code=503, detail=TEMPORARY) from None
    dispatched = False
    try:
        context = await resolve_card_context(db, principal, expected=expected, lock=True)
        profile = await get_profile(db, context)
        if profile is None or profile.id != identity.profile_id or not profile.provider_customer_id:
            raise HTTPException(status_code=409, detail='Saved card ownership requires review. Please contact the shop.')
        dispatched = True
        card = await vault.create_card_from_token(
            connection=context.connection, environment=context.environment,
            customer_id=profile.provider_customer_id, token=token,
            request_id=f'wallet-card-{identity.id}',
        )
        # A validated provider receipt is exact evidence, unlike masked-card
        # comparison. Retrying this local persistence never resends the token.
        state = await _record_outcome(db, identity, 'confirmed', card.id)
        if state == 'confirmed':
            return {'status': 'saved'}
        raise HTTPException(status_code=409, detail=PENDING)
    except vault.VaultError as exc:
        await _record_outcome(db, identity, 'unconfirmed' if exc.outcome_unknown else 'failed')
        raise HTTPException(status_code=409 if exc.outcome_unknown else 400,
                            detail=PENDING if exc.outcome_unknown else 'Your card could not be saved. Please check the details and try again.') from None
    except HTTPException:
        if not dispatched:
            await _record_outcome(db, identity, 'failed')
        raise
    except Exception:
        await _record_outcome(db, identity, 'unconfirmed' if dispatched else 'failed')
        raise HTTPException(status_code=409 if dispatched else 503,
                            detail=PENDING if dispatched else TEMPORARY) from None


async def mutate_card(db, user, expected, method_id, *, remove):
    context = await refreshed_context(db, user, expected)
    profile = await get_profile(db, context)
    if context.provider == 'stripe_connect':
        cid = stripe_customer_id(context, profile)
        if not cid:
            raise HTTPException(status_code=404, detail='Card not found')
        try:
            method = stripe.PaymentMethod.retrieve(method_id, stripe_account=context.account)
            if method.customer != cid:
                raise HTTPException(status_code=404, detail='Card not found')
            if remove:
                stripe.PaymentMethod.detach(method_id, stripe_account=context.account)
            else:
                stripe.Customer.modify(cid, invoice_settings={'default_payment_method': method_id}, stripe_account=context.account)
        except stripe.error.StripeError:
            raise HTTPException(status_code=409, detail='Unable to update this card. Refresh and try again.') from None
        return
    if profile is None or not profile.provider_customer_id:
        raise HTTPException(status_code=404, detail='Card not found')
    try:
        await vault.get_card(
            connection=context.connection, environment=context.environment,
            customer_id=profile.provider_customer_id, card_id=method_id,
            request_id=f'wallet-get-{profile.id}',
        )
        if remove:
            await vault.delete_card(
                connection=context.connection, environment=context.environment,
                customer_id=profile.provider_customer_id, card_id=method_id,
                request_id='wallet-delete-' + sha256(f'{profile.id}:{method_id}'.encode()).hexdigest()[:32],
            )
            if profile.default_method_id == method_id:
                profile.default_method_id = None
        else:
            profile.default_method_id = method_id
        await db.commit()
    except vault.VaultError:
        raise HTTPException(status_code=409, detail='Unable to update this card. Refresh to check its current status.') from None
