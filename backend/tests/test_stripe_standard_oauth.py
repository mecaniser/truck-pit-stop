from __future__ import annotations

from hashlib import sha256
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import stripe_connect
from app.core.security import create_access_token
from app.db.models.stripe_oauth import StripeOAuthState
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


async def _owner(db_session):
    tenant = Tenant(name="Stripe OAuth Garage", slug="stripe-oauth-garage")
    user = User(email="stripe-owner@example.com", hashed_password="not-used", first_name="Stripe", last_name="Owner", role=UserRole.GARAGE_OWNER, tenant=tenant, is_active=True, is_verified=True)
    db_session.add_all([tenant, user])
    await db_session.commit()
    return tenant, create_access_token({"sub": str(user.id)})


def _configure(monkeypatch):
    monkeypatch.setattr(stripe_connect.settings, "STRIPE_SECRET_KEY", "sk_test_platform")
    monkeypatch.setattr(stripe_connect.settings, "STRIPE_CONNECT_CLIENT_ID", "ca_test_platform")
    monkeypatch.setattr(stripe_connect.settings, "STRIPE_CONNECT_REDIRECT_URI", "https://api.example.com/api/v1/stripe/connect/oauth/callback")
    monkeypatch.setattr(stripe_connect.settings, "FRONTEND_URL", "https://app.example.com")


@pytest.mark.asyncio
async def test_stripe_standard_oauth_connects_existing_account_once(client, db_session, monkeypatch):
    _configure(monkeypatch)
    tenant, token = await _owner(db_session)
    start = await client.post("/api/v1/stripe/connect/connect", headers={"Authorization": f"Bearer {token}"})
    assert start.status_code == 200
    query = parse_qs(urlparse(start.json()["url"]).query)
    state = query["state"][0]
    assert query["scope"] == ["read_write"]
    assert query["client_id"] == ["ca_test_platform"]
    record = (await db_session.execute(select(StripeOAuthState).where(StripeOAuthState.state_hash == sha256(state.encode()).hexdigest()))).scalar_one()
    assert record.tenant_id == tenant.id
    assert record.state_hash != state

    monkeypatch.setattr(stripe_connect.stripe.OAuth, "token", lambda **_kwargs: {"stripe_user_id": "acct_existing"})
    monkeypatch.setattr(stripe_connect.stripe.Account, "retrieve", lambda _account_id: {"charges_enabled": True, "payouts_enabled": True})
    callback = await client.get("/api/v1/stripe/connect/oauth/callback", params={"state": state, "code": "authorization-code"})
    assert callback.status_code == 303
    assert callback.headers["location"] == "https://app.example.com/dashboard/settings?stripe=connected"
    await db_session.refresh(tenant)
    assert tenant.stripe_account_id == "acct_existing"
    assert tenant.stripe_connection_type == "standard_oauth"
    assert tenant.stripe_onboarding_complete is True

    replay = await client.get("/api/v1/stripe/connect/oauth/callback", params={"state": state, "code": "authorization-code"})
    assert replay.status_code == 303
    assert replay.headers["location"].endswith("?stripe=error")


@pytest.mark.asyncio
async def test_stripe_standard_oauth_requires_platform_configuration(client, db_session):
    _tenant, token = await _owner(db_session)
    response = await client.post("/api/v1/stripe/connect/connect", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
