"""Fail-closed shared account reservations. Never retries a grant or dispatch."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

from app.core.config import settings

PREFIX = '/integrations/callrail-budget/v1/reservations'
PURPOSES = {'dbn_mms_manifest', 'dbn_mms_image', 'dbn_sms_send', 'dbn_tracker_inspection'}


@dataclass(frozen=True)
class Permit:
    request_id: str
    period_end: datetime


class CallRailBudgetBlocked(Exception):
    """Definitively no provider dispatch. Safe public code, no remote details."""
    def __init__(self, code='callrail_budget_unavailable'):
        self.code = code
        super().__init__(code)


def configuration():
    try:
        base = settings.CALLRAIL_BUDGET_BASE_URL
        parsed = urlsplit(base)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or any(c.isspace() for c in base) or '\\' in base):
            raise ValueError()
        client_id = str(UUID(settings.CALLRAIL_BUDGET_CLIENT_ID))
        secret = settings.CALLRAIL_BUDGET_SIGNING_SECRET
        if len(secret.encode()) < 32:
            raise ValueError()
        return base.rstrip('/'), client_id, secret
    except (ValueError, TypeError, AttributeError):
        raise CallRailBudgetBlocked() from None


def signed_headers(client_id, secret, path, request_id, raw):
    timestamp = str(int(time.time()))
    canonical = b'callrail-budget.v1\n' + timestamp.encode() + b'\nPOST\n' + path.encode() + b'\n' + request_id.encode() + b'\n' + raw
    signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    return {'Content-Type': 'application/json', 'X-CallRail-Budget-Client': client_id,
        'X-CallRail-Budget-Timestamp': timestamp, 'X-CallRail-Budget-Signature': 'sha256=' + signature,
        'Idempotency-Key': request_id}


async def _post(path, request_id, payload):
    base, client_id, secret = configuration()
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5, connect=3), follow_redirects=False, trust_env=False) as client:  # noqa: SIM117
            # Stream and bound the broker reply; never reflect or log its body.
            async with client.stream('POST', base + path, content=raw,
                headers=signed_headers(client_id, secret, path, request_id, raw)) as response:
                if response.status_code == 429:
                    raise CallRailBudgetBlocked('callrail_budget_exceeded')
                if response.status_code != 200:
                    raise CallRailBudgetBlocked()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 8192:
                        raise CallRailBudgetBlocked()
                return json.loads(data)
    except (httpx.HTTPError, ValueError, TypeError):
        raise CallRailBudgetBlocked() from None


async def reserve(tenant_id, account_id, purpose):
    if purpose not in PURPOSES:
        raise CallRailBudgetBlocked()
    request_id = str(uuid4())
    result = await _post(PREFIX, request_id, {'request_id': request_id, 'tenant_id': str(tenant_id),
                                            'account_id': account_id, 'purpose': purpose})
    try:
        if (not isinstance(result, dict) or result.get('request_id') != request_id
            or result.get('dispatch_allowed') is not True
            or type(result.get('remaining')) is not int or result['remaining'] < 0):
            raise ValueError()
        UUID(result['reservation_id'])
        if not isinstance(result.get('period_end'), str):
            raise TypeError()
        period_end = datetime.fromisoformat(result['period_end'])
        if period_end.tzinfo is None or period_end <= datetime.now(UTC) + timedelta(seconds=5):
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CallRailBudgetBlocked() from None
    return Permit(request_id, period_end)


async def complete(request_id, status):
    # Completion never releases spend. If it fails, retain the uncertain unit;
    # do not turn a successful SMS into an unknown result or retry the provider.
    try:
        await asyncio.wait_for(_post(PREFIX + '/' + request_id + '/completion', request_id, {'http_status': status}), timeout=1)
    except (CallRailBudgetBlocked, TimeoutError):
        pass


@asynccontextmanager
async def attempt(tenant_id, account_id, purpose):
    permit = await reserve(tenant_id, account_id, purpose)
    if permit.period_end <= datetime.now(UTC) + timedelta(seconds=5):
        raise CallRailBudgetBlocked()
    status = {'http_status': None}
    try:
        yield status
    finally:
        await complete(permit.request_id, status['http_status'])
