"""Real database receipts and rollback recovery; provider calls are synthetic."""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.customer_payment_profile import CustomerPaymentProfile, SavedCardOperation
from app.services import customer_card_service as service
from app.services.quickbooks_vault_client import VaultCard, VaultError


@pytest_asyncio.fixture
async def wallet(db_session, monkeypatch):
    db = db_session
    tenant = Tenant(id=uuid4(), name='Wallet test', slug=uuid4().hex)
    db.add(tenant)
    await db.flush()
    customer = Customer(id=uuid4(), tenant_id=tenant.id, first_name='Test', last_name='Driver', email='wallet@example.invalid')
    db.add(customer)
    await db.commit()
    user = NS(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, role='customer')
    context = NS(tenant=NS(id=tenant.id), customer=NS(id=customer.id), provider='quickbooks_payments', account='realm_test', environment='sandbox', key='a'*64, connection=NS(encrypted_access_token='cipher'), principal=user)
    resolve = AsyncMock(return_value=context)
    monkeypatch.setattr(service, 'refreshed_context', resolve)
    monkeypatch.setattr(service, 'resolve_card_context', resolve)
    create = AsyncMock(return_value=VaultCard('card_saved', 'visa', '4242', 12, 2034))
    monkeypatch.setattr(service.vault, 'create_card_from_token', create)
    return NS(db=db, user=user, context=context, create=create, resolve=resolve)


async def save(w, key='request_one', token='opaque_card_token_one'):
    return await service.save_quickbooks_card(w.db, w.user, w.context.key, key, token)


@pytest.mark.asyncio
async def test_success_is_durable_and_exact_retry_does_not_dispatch(wallet):
    w=wallet
    assert await save(w) == {'status':'saved'}
    assert await save(w) == {'status':'saved'}
    assert w.create.await_count == 1
    profile = await w.db.scalar(select(CustomerPaymentProfile))
    operation = await w.db.scalar(select(SavedCardOperation))
    assert profile.provider_customer_id == 'dbv1_'+profile.id.hex
    assert w.create.call_args.kwargs['customer_id'] == profile.provider_customer_id
    assert operation.state == 'confirmed' and operation.provider_card_id == 'card_saved'
    assert operation.token_hash != 'opaque_card_token_one' and len(operation.token_hash)==64
    with pytest.raises(HTTPException) as error:
        await save(w, token='different_opaque_token')
    assert error.value.status_code == 409
    assert w.create.await_count == 1


@pytest.mark.asyncio
async def test_unknown_receipt_blocks_new_requests_without_matching_masked_cards(wallet):
    w=wallet
    w.create.side_effect=VaultError('unavailable', outcome_unknown=True)
    for key in ['request_one','request_two']:
        with pytest.raises(HTTPException) as error:
            await save(w,key=key,token='opaque_'+key)
        assert error.value.status_code==409
    assert w.create.await_count==1
    operation=await w.db.scalar(select(SavedCardOperation))
    assert operation.state=='unconfirmed' and operation.provider_card_id is None


@pytest.mark.asyncio
async def test_known_rejection_allows_fresh_form_but_never_consumed_token(wallet):
    w=wallet
    w.create.side_effect=VaultError('declined')
    with pytest.raises(HTTPException) as error:
        await save(w)
    assert error.value.status_code==400
    w.create.side_effect=None
    with pytest.raises(HTTPException) as error:
        await save(w,key='new_request')
    assert error.value.status_code==409
    assert w.create.await_count==1
    assert await save(w,key='fresh_request',token='fresh_opaque_token')=={'status':'saved'}


@pytest.mark.asyncio
async def test_persistence_failure_after_provider_success_preserves_pending_hold(wallet,monkeypatch):
    w=wallet
    original=w.db.commit
    count=0
    async def commit():
        nonlocal count
        count+=1
        if count==2:
            raise SQLAlchemyError('synthetic receipt write failure')
        return await original()
    monkeypatch.setattr(w.db,'commit',commit)
    with pytest.raises(HTTPException) as error:
        await save(w)
    assert error.value.status_code==409
    operation=await w.db.scalar(select(SavedCardOperation))
    assert operation.state=='pending'
    with pytest.raises(HTTPException):
        await save(w,key='fresh_request',token='fresh_opaque_token')
    assert w.create.await_count==1


@pytest.mark.asyncio
async def test_context_changes_before_dispatch_mark_request_failed(wallet):
    w=wallet
    w.resolve.side_effect=[w.context,HTTPException(status_code=409,detail='Refresh payment settings')]
    with pytest.raises(HTTPException) as error:
        await save(w)
    assert error.value.status_code==409
    w.create.assert_not_awaited()
    assert await w.db.scalar(select(SavedCardOperation.state))=='failed'


@pytest.mark.asyncio
async def test_database_prevents_concurrent_open_receipts(wallet):
    w=wallet
    profile=await service.get_profile(w.db,w.context,create=True)
    values=dict(tenant_id=w.user.tenant_id,customer_id=w.user.customer_id,profile_id=profile.id,context_key=w.context.key,state='pending')
    w.db.add(SavedCardOperation(**values,idempotency_key='first',token_hash='a'*64))
    await w.db.commit()
    w.db.add(SavedCardOperation(**values,idempotency_key='second',token_hash='b'*64))
    with pytest.raises(IntegrityError):
        await w.db.commit()
    await w.db.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize('token',['4242-4242-4242-4242','4242.4242.4242.4242','12-3','4242_4242_4242_4242'])
async def test_formatted_numeric_card_data_never_dispatches(wallet,token):
    with pytest.raises(HTTPException) as error:
        await save(wallet,token=token)
    assert error.value.status_code==422
    wallet.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_listing_refreshes_oauth_without_creating_a_vault(wallet,monkeypatch):
    w=wallet
    listing=AsyncMock(return_value=[])
    monkeypatch.setattr(service.vault,'list_cards',listing)
    assert await service.list_customer_cards(w.db,w.context)==[]
    w.resolve.assert_awaited_once_with(w.db,w.user,w.context.key)
    listing.assert_not_awaited()
    assert await w.db.scalar(select(CustomerPaymentProfile.id)) is None
    assert await w.db.scalar(select(SavedCardOperation.id)) is None
