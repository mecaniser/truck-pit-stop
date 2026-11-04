from dataclasses import asdict
import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.quickbooks_crypto import QuickBooksTokenEncryptionError
from app.services import quickbooks_vault_client as vault


CARD = {"id": "card_1", "number": "xxxxxxxxxxxx4242", "cardType": "Visa", "expMonth": "12", "expYear": "2034"}


@pytest.fixture
def connection():
    return SimpleNamespace(status="connected", realm_id="realm_1", encrypted_access_token="encrypted",
                           scopes="com.intuit.quickbooks.accounting com.intuit.quickbooks.payment")


@pytest.fixture
def install(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(vault, "decrypt_quickbooks_token", lambda value: "opaque_access_test")
    def use(handler):
        monkeypatch.setattr(vault.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return use


def args(connection, **overrides):
    return {"connection": connection, "environment": "sandbox", "customer_id": "123", "request_id": "request-1", **overrides}


@pytest.mark.asyncio
@pytest.mark.parametrize('environment,host', [('sandbox','sandbox.api.intuit.com'), ('production','api.intuit.com')])
async def test_list_is_account_token_and_explicit_environment_scoped(connection, install, environment, host):
    def handler(request):
        assert request.method == 'GET'
        assert request.url.host == host
        assert request.url.path == '/quickbooks/v4/customers/123/cards'
        assert request.headers['Authorization'] == 'Bearer opaque_access_test'
        assert request.headers['Request-Id'] == 'request-1'
        assert not request.content
        return httpx.Response(200, json=[CARD])
    install(handler)
    cards = await vault.list_cards(**args(connection, environment=environment))
    assert [asdict(card) for card in cards] == [{'id':'card_1','brand':'visa','last4':'4242','exp_month':12,'exp_year':2034}]
    assert 'number' not in asdict(cards[0])


@pytest.mark.asyncio
async def test_create_posts_only_opaque_token_and_reuses_given_request_id(connection, install):
    def handler(request):
        assert request.method == 'POST'
        assert request.url.path == '/quickbooks/v4/customers/123/cards/createFromToken'
        assert request.headers['Request-Id'] == 'request-1'
        assert json.loads(request.content) == {'value':'opaque-token-123'}
        return httpx.Response(201,json={**CARD,'name':'Private Name','cvc':'123','address':{'postalCode':'12345'}})
    install(handler)
    card = await vault.create_card_from_token(**args(connection),token='opaque-token-123')
    assert asdict(card) == {'id':'card_1','brand':'visa','last4':'4242','exp_month':12,'exp_year':2034}
    assert 'Private Name' not in repr(card)


@pytest.mark.asyncio
async def test_get_requires_returned_identity_to_match(connection, install):
    install(lambda request: httpx.Response(200,json=CARD))
    assert (await vault.get_card(**args(connection),card_id='card_1')).id == 'card_1'
    with pytest.raises(vault.VaultError) as exc:
        await vault.get_card(**args(connection),card_id='card_other')
    assert exc.value.outcome_unknown is False


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [204,404])
async def test_delete_exact_customer_card_accepts_confirmed_absence(connection,install,status):
    def handler(request):
        assert request.method=='DELETE'
        assert request.url.path=='/quickbooks/v4/customers/123/cards/card_1'
        assert request.headers['Request-Id']=='request-1'
        return httpx.Response(status)
    install(handler)
    assert await vault.delete_card(**args(connection),card_id='card_1') is None


@pytest.mark.asyncio
async def test_successful_empty_list_is_distinct_from_retrieval_failure(connection,install):
    install(lambda request:httpx.Response(200,json=[]))
    assert await vault.list_cards(**args(connection))==[]
    install(lambda request:httpx.Response(404,json={'error':'sensitive provider body'}))
    with pytest.raises(vault.VaultError) as exc:
        await vault.list_cards(**args(connection))
    assert exc.value.status_code==404
    assert 'sensitive' not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['create','delete'])
@pytest.mark.parametrize('status,unknown', [(400,False),(401,False),(403,False),(408,True),(425,True),(429,True),(500,True),(503,True),(302,True)])
async def test_mutation_errors_are_scrubbed_and_unknown_states_preserved(connection,install,method,status,unknown):
    install(lambda request:httpx.Response(status,json={'error':'secret_token raw PAN provider reply'}))
    with pytest.raises(vault.VaultError) as exc:
        if method=='create':
            await vault.create_card_from_token(**args(connection),token='opaque-token-123')
        else:
            await vault.delete_card(**args(connection),card_id='card_1')
    assert exc.value.outcome_unknown is unknown
    assert exc.value.status_code==status
    assert 'secret_token' not in str(exc.value)
    assert 'PAN' not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('method,unknown',[('list',False),('create',True),('delete',True)])
async def test_transport_failures_do_not_expose_request_or_reclassify_unknown(connection,install,method,unknown):
    def handler(request):
        raise httpx.ReadTimeout('unsafe body text',request=request)
    install(handler)
    with pytest.raises(vault.VaultError) as exc:
        if method=='list': await vault.list_cards(**args(connection))
        elif method=='create': await vault.create_card_from_token(**args(connection),token='opaque-token-123')
        else: await vault.delete_card(**args(connection),card_id='card_1')
    assert exc.value.outcome_unknown is unknown
    assert 'unsafe' not in str(exc.value)
    assert exc.value.__suppress_context__


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [None,{}, {'cards':[CARD]}, [CARD,CARD], [{**CARD,'number':'4242424242424242'}], [{**CARD,'number':'4242'}], [{**CARD,'expMonth':'13'}], [{**CARD,'expYear':True}], [{**CARD,'id':'../other'}]])
async def test_bad_lists_never_become_partial_cards_or_empty_wallet(connection,install,payload):
    install(lambda request:httpx.Response(200,json=payload))
    with pytest.raises(vault.VaultError) as exc:
        await vault.list_cards(**args(connection))
    assert exc.value.outcome_unknown is False
    assert '4242424242424242' not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('number', ['xxxxxxxxxxxx4242','XXXX XXXX XXXX 4242','411111******4242','•••• •••• •••• 4242'])
async def test_masked_number_variants_are_scrubbed_to_last_four(connection,install,number):
    install(lambda request:httpx.Response(200,json=[{**CARD,'number':number}]))
    card=(await vault.list_cards(**args(connection)))[0]
    assert card.last4=='4242'
    assert number not in repr(card)


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [b'not json', b'{}', b'{"id":"x","number":"4242424242424242"}'])
async def test_unreadable_create_success_is_unconfirmed_not_declined(connection,install,body):
    install(lambda request:httpx.Response(200,content=body))
    with pytest.raises(vault.VaultError) as exc:
        await vault.create_card_from_token(**args(connection),token='opaque-token-123')
    assert exc.value.outcome_unknown is True


@pytest.mark.asyncio
async def test_unexpected_delete_success_is_unconfirmed(connection,install):
    install(lambda request:httpx.Response(200,json={'unexpected':True}))
    with pytest.raises(vault.VaultError) as exc:
        await vault.delete_card(**args(connection),card_id='card_1')
    assert exc.value.outcome_unknown


@pytest.mark.asyncio
@pytest.mark.parametrize('override', [{'environment':'live'},{'environment':''},{'customer_id':'../other'},{'customer_id':'x?account=y'},{'request_id':'x\r\ny'},{'request_id':''}])
async def test_invalid_context_never_reaches_provider(connection,install,override):
    install(lambda request:pytest.fail('No provider call permitted'))
    with pytest.raises(vault.VaultError):
        await vault.list_cards(**args(connection,**override))


@pytest.mark.asyncio
@pytest.mark.parametrize('token', ['', '4242424242424242','x'*2049,'opaque\ntoken','a/b'])
async def test_invalid_token_never_reaches_provider(connection,install,token):
    install(lambda request:pytest.fail('No provider call permitted'))
    with pytest.raises(vault.VaultError) as exc:
        await vault.create_card_from_token(**args(connection),token=token)
    assert not exc.value.outcome_unknown


@pytest.mark.asyncio
@pytest.mark.parametrize('override', [{'status':'disconnected'},{'realm_id':None},{'scopes':'com.intuit.quickbooks.accounting'},{'encrypted_access_token':None}])
async def test_missing_connection_admission_never_calls_provider(connection,install,override):
    install(lambda request:pytest.fail('No provider call permitted'))
    for key,value in override.items(): setattr(connection,key,value)
    with pytest.raises(vault.VaultError): await vault.list_cards(**args(connection))


@pytest.mark.asyncio
async def test_credential_decryption_error_is_sanitized(connection,install,monkeypatch):
    install(lambda request:pytest.fail('No provider call permitted'))
    def fail(value): raise QuickBooksTokenEncryptionError('secret unsafe diagnostic')
    monkeypatch.setattr(vault,'decrypt_quickbooks_token',fail)
    with pytest.raises(vault.VaultError) as exc: await vault.list_cards(**args(connection))
    assert 'secret' not in str(exc.value)
    assert not exc.value.outcome_unknown


@pytest.mark.asyncio
@pytest.mark.parametrize('card_id', [None, '', '../other', 'x?customer=other'])
@pytest.mark.parametrize('operation', ['get', 'delete'])
async def test_invalid_card_identity_never_calls_a_collection_endpoint(connection, install, card_id, operation):
    install(lambda request: pytest.fail('No provider call permitted'))
    with pytest.raises(vault.VaultError):
        if operation == 'get': await vault.get_card(**args(connection), card_id=card_id)
        else: await vault.delete_card(**args(connection), card_id=card_id)
