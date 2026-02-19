from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.quote_access_service as svc


@pytest.mark.asyncio
async def test_generate_quote_portal_enrollment_token(monkeypatch):
    stored = {}

    async def fake_store(token, payload, ttl):
        stored["token"] = token
        stored["payload"] = payload
        stored["ttl"] = ttl

    monkeypatch.setattr(svc, "store_quote_portal_enrollment_token", fake_store)

    tenant_id = uuid4()
    quote = SimpleNamespace(id=uuid4())
    order = SimpleNamespace(id=uuid4(), tenant_id=tenant_id)
    customer = SimpleNamespace(id=uuid4(), email="cust@example.com")

    token = await svc.generate_quote_portal_enrollment_token(quote, order, customer)

    assert len(token) > 20
    assert stored["payload"]["quote_id"] == str(quote.id)
    assert stored["payload"]["purpose"] == "quote_portal_enrollment"
    assert stored["payload"]["email"] == "cust@example.com"
    assert stored["ttl"] == svc.QUOTE_PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS
