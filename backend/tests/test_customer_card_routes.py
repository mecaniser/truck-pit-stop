"""HTTP contract tests: strict token-only writes and processor-neutral capabilities."""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.api.v1.endpoints import customer_cards as routes
from app.core.dependencies import get_current_active_user, get_db

KEY = 'a' * 64
CARD = dict(id='card_one',brand='visa',last4='4242',exp_month=12,exp_year=2034,is_default=False)


@pytest.fixture
def app_context(monkeypatch):
    db, user = object(), object()
    context = NS(provider='quickbooks_payments',key=KEY,account='realm_one',environment='sandbox')
    resolve = AsyncMock(return_value=context)
    profile, pending = AsyncMock(return_value=None), AsyncMock(return_value=False)
    listed = AsyncMock(return_value=[CARD])
    prepare = AsyncMock(return_value={'client_secret':'synthetic_secret','stripe_account_id':'acct_one'})
    save = AsyncMock(return_value={'status':'saved'})
    mutate = AsyncMock()
    monkeypatch.setattr(routes,'resolve_card_context',resolve)
    for name,mock in [('get_profile',profile),('pending_save',pending),('list_customer_cards',listed),
                      ('prepare_stripe_card',prepare),('save_quickbooks_card',save),('mutate_card',mutate)]:
        monkeypatch.setattr(routes.cards,name,mock)
    app = FastAPI()
    app.include_router(routes.router,prefix='/payments/cards')
    app.dependency_overrides[get_current_active_user] = lambda:user
    app.dependency_overrides[get_db] = lambda:db
    return NS(app=app,db=db,user=user,context=context,resolve=resolve,profile=profile,pending=pending,
              listed=listed,prepare=prepare,save=save,mutate=mutate)


async def call(c,method,path='',**kwargs):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app),base_url='http://test') as client:
        return await client.request(method,'/payments/cards'+path,**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('environment,host',[('sandbox','sandbox.api.intuit.com'),('production','api.intuit.com')])
async def test_quickbooks_capability_returns_only_bound_browser_setup(app_context,environment,host):
    c=app_context;c.context.environment=environment
    result=await call(c,'GET','/config')
    assert result.status_code==200
    data=result.json()
    assert data['provider']=='quickbooks_payments' and data['context_key']==KEY
    assert data['available'] and not data['save_pending']
    assert data['token_url']==f'https://{host}/quickbooks/v4/payments/tokens'
    assert data['stripe_account_id'] is None
    assert 'realm_one' not in result.text
    c.prepare.assert_not_awaited();c.save.assert_not_awaited();c.mutate.assert_not_awaited()


@pytest.mark.asyncio
async def test_stripe_setup_is_exposed_only_for_selected_stripe(app_context):
    c=app_context;c.context.provider='stripe_connect';c.context.account='acct_one';c.context.environment='test'
    result=await call(c,'GET','/config')
    assert result.json()['stripe_account_id']=='acct_one'
    assert result.json()['token_url'] is None


@pytest.mark.asyncio
async def test_unconfirmed_save_is_a_capability_hold_without_mutation(app_context):
    c=app_context;c.pending.return_value=True
    result=await call(c,'GET','/config')
    assert result.json()['save_pending'] is True
    assert 'before trying again' in result.json()['message']
    c.prepare.assert_not_awaited();c.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_unready_provider_is_not_reported_as_an_empty_wallet(app_context):
    c=app_context;c.resolve.side_effect=HTTPException(status_code=409,detail='Saved cards are unavailable.')
    result=await call(c,'GET','/config')
    assert result.status_code==200
    assert result.json()['available'] is False
    assert result.json()['provider'] is None
    assert 'unavailable' in result.json()['message']
    c.profile.assert_not_awaited();c.listed.assert_not_awaited()
    result=await call(c,'GET')
    assert result.status_code==409


@pytest.mark.asyncio
@pytest.mark.parametrize('status',[401,403,404])
async def test_auth_and_identity_failures_are_not_hidden_as_capability_status(app_context,status):
    c=app_context;c.resolve.side_effect=HTTPException(status_code=status,detail='Denied')
    result=await call(c,'GET','/config')
    assert result.status_code==status
    c.profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_checks_expected_context_and_returns_masked_contract(app_context):
    c=app_context
    result=await call(c,'GET',params={'expected_context':KEY})
    assert result.status_code==200 and result.json()==[CARD]
    c.resolve.assert_awaited_once_with(c.db,c.user,expected=KEY)
    c.listed.assert_awaited_once_with(c.db,c.context)


@pytest.mark.asyncio
async def test_list_provider_failure_is_not_empty_or_partially_successful(app_context):
    c=app_context;c.listed.side_effect=HTTPException(status_code=503,detail='Saved cards could not be loaded.')
    result=await call(c,'GET')
    assert result.status_code==503 and 'could not be loaded' in result.json()['detail']


@pytest.mark.asyncio
async def test_prepare_delegates_only_versioned_idempotent_intent(app_context):
    c=app_context
    result=await call(c,'POST','/prepare',json={'expected_context':KEY,'idempotency_key':'request_one'})
    assert result.status_code==200 and result.json()['stripe_account_id']=='acct_one'
    c.prepare.assert_awaited_once_with(c.db,c.user,KEY,'request_one')
    c.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_token_only_save_delegates_to_orchestrator(app_context):
    c=app_context
    result=await call(c,'POST','/save',json={'expected_context':KEY,'idempotency_key':'request_one','token':'opaque-token-123'})
    assert result.status_code==200 and result.json()=={'status':'saved'}
    c.save.assert_awaited_once_with(c.db,c.user,KEY,'request_one','opaque-token-123')
    c.prepare.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('body',[
    {'expected_context':KEY,'idempotency_key':'request','token':'4242424242424242'},
    {'expected_context':KEY,'idempotency_key':'request','token':'opaque-token','number':'4242424242424242'},
    {'expected_context':KEY,'idempotency_key':'request','token':'opaque-token','cvc':'123'},
    {'expected_context':KEY,'idempotency_key':'request','token':'opaque-token','provider':'stripe_connect'},
    {'expected_context':KEY,'idempotency_key':'request','token':'opaque-token','provider_customer_id':'other'},
    {'expected_context':'stale','idempotency_key':'request','token':'opaque-token'},
    {'expected_context':KEY,'idempotency_key':'bad key','token':'opaque-token'},
    {'expected_context':KEY,'token':'opaque-token'},
    {'expected_context':KEY,'idempotency_key':'request','token':'x'*2049},
])
async def test_invalid_or_raw_card_bodies_never_reach_provider_service(app_context,body):
    c=app_context
    result=await call(c,'POST','/save',json=body)
    assert result.status_code==422
    assert result.json()=={'detail':'Invalid card request. Refresh the form and try again.'}
    c.save.assert_not_awaited();c.prepare.assert_not_awaited()


@pytest.mark.asyncio
async def test_unconfirmed_service_response_is_not_translated_to_success(app_context):
    c=app_context;c.save.side_effect=HTTPException(status_code=409,detail='We could not confirm whether your card was saved.')
    result=await call(c,'POST','/save',json={'expected_context':KEY,'idempotency_key':'request','token':'opaque-token'})
    assert result.status_code==409 and 'could not confirm' in result.json()['detail']


@pytest.mark.asyncio
async def test_default_and_remove_carry_current_context_to_ownership_service(app_context):
    c=app_context
    result=await call(c,'POST','/card_one/default',json={'expected_context':KEY})
    assert result.status_code==204 and not result.content
    c.mutate.assert_awaited_once_with(c.db,c.user,KEY,'card_one',remove=False)
    c.mutate.reset_mock()
    result=await call(c,'DELETE','/card_one',params={'expected_context':KEY})
    assert result.status_code==204 and not result.content
    c.mutate.assert_awaited_once_with(c.db,c.user,KEY,'card_one',remove=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path,kwargs',[
    ('POST','/card_one/default',{'json':{}}),
    ('POST','/card_one/default',{'json':{'expected_context':KEY,'provider':'other'}}),
    ('DELETE','/card_one',{}),
    ('DELETE','/card_one',{'params':{'expected_context':'old'}}),
    ('DELETE','/invalid%3Fid',{'params':{'expected_context':KEY}}),
])
async def test_mutations_require_context_and_safe_card_identity(app_context,method,path,kwargs):
    c=app_context
    result=await call(c,method,path,**kwargs)
    assert result.status_code==422
    c.mutate.assert_not_awaited()


def test_main_router_registers_generic_card_endpoints():
    from app.api.v1.router import api_router
    paths={(route.path,tuple(sorted(getattr(route, 'methods', []) or []))) for route in api_router.routes}
    assert ('/payments/cards/config',('GET',)) in paths
    assert ('/payments/cards/save',('POST',)) in paths
    assert ('/payments/cards/{method_id}',('DELETE',)) in paths
