from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.invoice_access_service as svc


def _make_entities():
    tenant_id = uuid4()
    invoice = SimpleNamespace(id=uuid4(), tenant_id=tenant_id)
    order = SimpleNamespace(id=uuid4())
    customer = SimpleNamespace(id=uuid4(), email="test@example.com")
    return invoice, order, customer


@pytest.mark.asyncio
async def test_generate_invoice_access_token_stores_and_returns(monkeypatch):
    stored = {}

    async def fake_store(token, payload, ttl):
        stored["token"] = token
        stored["payload"] = payload
        stored["ttl"] = ttl

    monkeypatch.setattr(svc, "store_invoice_access_token", fake_store)

    invoice, order, customer = _make_entities()
    token = await svc.generate_invoice_access_token(invoice, order, customer)

    assert len(token) > 20
    assert stored["token"] == token
    assert stored["payload"]["invoice_id"] == str(invoice.id)
    assert stored["payload"]["email"] == "test@example.com"
    assert stored["ttl"] == svc.INVOICE_ACCESS_TOKEN_TTL_SECONDS


@pytest.mark.asyncio
async def test_generate_invoice_access_link_without_shop_info(monkeypatch):
    async def fake_store(token, payload, ttl):
        pass

    monkeypatch.setattr(svc, "store_invoice_access_token", fake_store)

    invoice, order, customer = _make_entities()
    link = await svc.generate_invoice_access_link(invoice, order, customer)

    assert link.startswith("http")
    assert "/invoice/" in link
    assert "?" not in link  # no query params


@pytest.mark.asyncio
async def test_generate_invoice_access_link_with_shop_info(monkeypatch):
    async def fake_store(token, payload, ttl):
        pass

    monkeypatch.setattr(svc, "store_invoice_access_token", fake_store)

    invoice, order, customer = _make_entities()
    link = await svc.generate_invoice_access_link(
        invoice, order, customer,
        shop_name="Big Rig Repairs",
        shop_phone="5551234567",
    )

    assert "shop_name=Big" in link
    assert "shop_phone=5551234567" in link


@pytest.mark.asyncio
async def test_generate_portal_enrollment_token(monkeypatch):
    stored = {}

    async def fake_store(token, payload, ttl):
        stored["payload"] = payload
        stored["ttl"] = ttl

    monkeypatch.setattr(svc, "store_portal_enrollment_token", fake_store)

    invoice, order, customer = _make_entities()
    token = await svc.generate_portal_enrollment_token(invoice, order, customer)

    assert len(token) > 20
    assert stored["payload"]["purpose"] == "portal_enrollment"
    assert stored["ttl"] == svc.PORTAL_ENROLLMENT_TOKEN_TTL_SECONDS
