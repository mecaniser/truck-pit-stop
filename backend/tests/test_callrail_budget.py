"""Offline shared-budget protocol and predispatch fail-closed proofs."""
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from app.core.config import settings
from app.services import callrail_budget as budget


@pytest.fixture
def broker(monkeypatch):
    monkeypatch.setattr(settings, 'CALLRAIL_BUDGET_BASE_URL', 'https://elis.synthetic.example')
    monkeypatch.setattr(settings, 'CALLRAIL_BUDGET_CLIENT_ID', str(uuid4()))
    monkeypatch.setattr(settings, 'CALLRAIL_BUDGET_SIGNING_SECRET', 'synthetic-only-shared-secret-123456789')
    original = httpx.AsyncClient
    requests = []
    def install(handler):
        def wrapped(request):
            requests.append(request)
            return handler(request)
        monkeypatch.setattr(budget.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(wrapped), **kwargs))
    return requests, install


@pytest.mark.asyncio
async def test_signed_first_grant_and_completion(broker):
    requests, install = broker
    def handler(request):
        raw = request.content
        timestamp = request.headers['X-CallRail-Budget-Timestamp']
        request_id = request.headers['Idempotency-Key']
        path = request.url.path
        canonical = b'callrail-budget.v1\n' + timestamp.encode() + b'\nPOST\n' + path.encode() + b'\n' + request_id.encode() + b'\n' + raw
        assert request.headers['X-CallRail-Budget-Signature'] == 'sha256=' + hmac.new(
            settings.CALLRAIL_BUDGET_SIGNING_SECRET.encode(), canonical, hashlib.sha256).hexdigest()
        if path.endswith('/completion'):
            assert path == budget.PREFIX + '/' + request_id + '/completion'
            assert json.loads(raw) == {'http_status': 200}
            return httpx.Response(200, json={'ok': True})
        payload = json.loads(raw)
        return httpx.Response(200, json={'request_id': payload['request_id'], 'reservation_id': str(uuid4()),
            'dispatch_allowed': True, 'period_end': (datetime.now(UTC) + timedelta(days=1)).isoformat(), 'remaining': 9})
    install(handler)
    async with budget.attempt(uuid4(), 'ACCsynthetic', 'dbn_mms_image') as usage:
        usage['http_status'] = 200
    assert len(requests) == 2
    assert all(request.url.host == 'elis.synthetic.example' for request in requests)
    assert all('Authorization' not in request.headers for request in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [301, 302, 401, 409, 429, 500, 503])
async def test_any_denial_never_yields_provider_permit(broker, status):
    requests, install = broker
    install(lambda request: httpx.Response(status, headers={'Location': 'https://other.invalid/'}, json={'dispatch_allowed': True}))
    entered = False
    with pytest.raises(budget.CallRailBudgetBlocked):
        async with budget.attempt(uuid4(), 'ACCsynthetic', 'dbn_sms_send'):
            entered = True
    assert not entered and len(requests) == 1


@pytest.mark.asyncio
async def test_replayed_permit_or_uncertain_grant_is_not_retried(broker):
    requests, install = broker
    install(lambda request: httpx.Response(200, json={'request_id': request.headers['Idempotency-Key'],
        'reservation_id': str(uuid4()), 'dispatch_allowed': False, 'period_end': '2026-10-28', 'remaining': 9}))
    with pytest.raises(budget.CallRailBudgetBlocked):
        await budget.reserve(uuid4(), 'ACCsynthetic', 'dbn_sms_send')
    assert len(requests) == 1
    def timeout(request):
        raise httpx.ReadTimeout('synthetic-secret-must-not-surface')
    install(timeout)
    with pytest.raises(budget.CallRailBudgetBlocked) as error:
        await budget.reserve(uuid4(), 'ACCsynthetic', 'dbn_sms_send')
    assert 'synthetic-secret' not in str(error.value)
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_missing_configuration_blocks_before_network(monkeypatch):
    monkeypatch.setattr(settings, 'CALLRAIL_BUDGET_BASE_URL', '')
    with pytest.raises(budget.CallRailBudgetBlocked):
        await budget.reserve(uuid4(), 'ACCsynthetic', 'dbn_sms_send')


@pytest.mark.asyncio
async def test_sms_budget_failure_makes_no_provider_call(monkeypatch):
    from app.services import callrail_service as service
    context = service.CallRailContext(uuid4(), uuid4(), uuid4(), uuid4(), 'ACCsynthetic', 'COMsynthetic',
        'TRKsynthetic', '+15005550001', '+15005550002', 'CALLRAIL_SYNTHETIC')
    monkeypatch.setenv('CALLRAIL_SYNTHETIC', 'synthetic')
    async def reject(*args):
        raise budget.CallRailBudgetBlocked('callrail_budget_exceeded')
    monkeypatch.setattr(budget, 'reserve', reject)
    monkeypatch.setattr(service.httpx, 'AsyncClient', lambda **kwargs: pytest.fail('provider client must not be created'))
    with pytest.raises(budget.CallRailBudgetBlocked):
        await service.send(context, 'Synthetic', context.customer_phone)


@pytest.mark.asyncio
@pytest.mark.parametrize('end', ['invalid', '2020-01-01T00:00:00Z', '2099-01-01T00:00:00'])
async def test_old_naive_or_invalid_period_never_grants(broker, end):
    requests, install = broker
    install(lambda request: httpx.Response(200, json={'request_id': request.headers['Idempotency-Key'],
        'reservation_id': str(uuid4()), 'dispatch_allowed': True, 'period_end': end, 'remaining': 9}))
    with pytest.raises(budget.CallRailBudgetBlocked):
        async with budget.attempt(uuid4(), 'ACCsynthetic', 'dbn_sms_send'):
            pytest.fail('expired grant must not dispatch')
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_delayed_permit_is_checked_again_immediately_before_dispatch(monkeypatch):
    async def late(*args):
        return budget.Permit(str(uuid4()), datetime.now(UTC) + timedelta(seconds=4))
    monkeypatch.setattr(budget, 'reserve', late)
    with pytest.raises(budget.CallRailBudgetBlocked):
        async with budget.attempt(uuid4(), 'ACCsynthetic', 'dbn_sms_send'):
            pytest.fail('late permit must never dispatch')
