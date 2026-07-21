from __future__ import annotations

import pytest

from app.api.v1.endpoints import stripe_connect
from app.core.security import create_access_token
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


async def _owner(db_session):
    tenant = Tenant(name="Hosted Stripe Garage", slug="hosted-stripe-garage", email="garage@example.com")
    user = User(
        email="stripe-owner@example.com",
        hashed_password="not-used",
        first_name="Stripe",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant=tenant,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([tenant, user])
    await db_session.commit()
    return tenant, create_access_token({"sub": str(user.id)})


def _configure(monkeypatch):
    monkeypatch.setattr(stripe_connect.settings, "STRIPE_SECRET_KEY", "sk_test_platform")
    monkeypatch.setattr(stripe_connect.settings, "STRIPE_PUBLISHABLE_KEY", "pk_test_platform")
    monkeypatch.setattr(stripe_connect.settings, "FRONTEND_URL", "https://app.example.com")


def test_verification_status_distinguishes_review_from_missing_details():
    assert stripe_connect._verification_status(
        {"charges_enabled": False, "payouts_enabled": False, "details_submitted": True, "requirements": {"pending_verification": ["company.verification.document"]}}
    ) == ("under_review", ["company.verification.document"])
    assert stripe_connect._verification_status(
        {"charges_enabled": False, "payouts_enabled": False, "requirements": {"currently_due": ["external_account"]}}
    ) == ("needs_information", ["external_account"])


@pytest.mark.asyncio
async def test_hosted_onboarding_creates_and_reuses_connected_account(client, db_session, monkeypatch):
    _configure(monkeypatch)
    tenant, token = await _owner(db_session)
    created_accounts = []
    account_links = []

    def create_account(**params):
        created_accounts.append(params)
        return {"id": "acct_hosted", "charges_enabled": False, "payouts_enabled": False}

    def retrieve_account(account_id):
        assert account_id == "acct_hosted"
        return {"id": account_id, "charges_enabled": False, "payouts_enabled": False}

    def create_link(**params):
        account_links.append(params)
        return {"url": f"https://connect.stripe.test/{len(account_links)}"}

    monkeypatch.setattr(stripe_connect.stripe.Account, "create", create_account)
    monkeypatch.setattr(stripe_connect.stripe.Account, "retrieve", retrieve_account)
    monkeypatch.setattr(stripe_connect.stripe.AccountLink, "create", create_link)
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.post("/api/v1/stripe/connect/connect", headers=headers)
    second = await client.post("/api/v1/stripe/connect/connect", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(created_accounts) == 1
    assert created_accounts[0]["controller"] == {
        "fees": {"payer": "account"},
        "losses": {"payments": "stripe"},
        "requirement_collection": "stripe",
        "stripe_dashboard": {"type": "full"},
    }
    assert account_links[0] == {
        "account": "acct_hosted",
        "refresh_url": "https://app.example.com/dashboard/settings?stripe=refresh",
        "return_url": "https://app.example.com/dashboard/settings?stripe=return",
        "type": "account_onboarding",
        "collection_options": {"fields": "eventually_due"},
    }
    await db_session.refresh(tenant)
    assert tenant.stripe_account_id == "acct_hosted"
    assert tenant.stripe_connection_type == "stripe_hosted"
    assert tenant.stripe_onboarding_complete is False


@pytest.mark.asyncio
async def test_hosted_onboarding_requires_platform_keys(client, db_session, monkeypatch):
    monkeypatch.setattr(stripe_connect.settings, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(stripe_connect.settings, "STRIPE_PUBLISHABLE_KEY", "")
    _tenant, token = await _owner(db_session)
    response = await client.post(
        "/api/v1/stripe/connect/connect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_hosted_onboarding_reports_unactivated_platform(client, db_session, monkeypatch):
    _configure(monkeypatch)
    _tenant, token = await _owner(db_session)

    def create_account(**_params):
        raise stripe_connect.stripe.error.InvalidRequestError(
            "Your account must be activated in order to create accounts.",
            None,
        )

    monkeypatch.setattr(stripe_connect.stripe.Account, "create", create_account)
    response = await client.post(
        "/api/v1/stripe/connect/connect",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert "platform activation" in response.json()["detail"]
