from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import stripe_connect
from app.core.payment_step_up import PaymentStepUpScope
from app.core.security import create_access_token
from app.db.models.tenant import Tenant
from app.db.models.payment_step_up import PaymentStepUpAuditEvent
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
    return tenant, user, create_access_token({"sub": str(user.id)})


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
async def test_connect_alias_and_disconnect_have_no_side_effect_without_step_up(
    client, db_session, monkeypatch
):
    _configure(monkeypatch)
    tenant, _user, token = await _owner(db_session)
    provider_calls = []

    def unexpected_provider_call(**kwargs):
        provider_calls.append(kwargs)
        return {"id": "acct_should_not_exist"}

    monkeypatch.setattr(stripe_connect.stripe.Account, "create", unexpected_provider_call)
    headers = {"Authorization": f"Bearer {token}"}
    connect = await client.post("/api/v1/stripe/connect/connect", headers=headers)
    alias = await client.post("/api/v1/stripe/connect/onboard", headers=headers)

    assert connect.status_code == 428
    assert alias.status_code == 428
    assert provider_calls == []
    await db_session.refresh(tenant)
    assert tenant.stripe_account_id is None

    tenant.stripe_account_id = "acct_preserved"
    tenant.stripe_connection_type = "stripe_hosted"
    tenant.stripe_onboarding_complete = True
    await db_session.commit()
    disconnect = await client.post("/api/v1/stripe/connect/disconnect", headers=headers)
    assert disconnect.status_code == 428
    await db_session.refresh(tenant)
    assert tenant.stripe_account_id == "acct_preserved"
    assert tenant.stripe_onboarding_complete is True


@pytest.mark.asyncio
async def test_hosted_onboarding_creates_and_reuses_connected_account(
    client, db_session, monkeypatch, issue_payment_step_up
):
    _configure(monkeypatch)
    tenant, user, token = await _owner(db_session)
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
    headers = await issue_payment_step_up(
        token=token,
        user=user,
        scope=PaymentStepUpScope.MANAGE,
    )

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
async def test_hosted_onboarding_requires_platform_keys(
    client, db_session, monkeypatch, issue_payment_step_up
):
    monkeypatch.setattr(stripe_connect.settings, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(stripe_connect.settings, "STRIPE_PUBLISHABLE_KEY", "")
    _tenant, user, token = await _owner(db_session)
    headers = await issue_payment_step_up(
        token=token,
        user=user,
        scope=PaymentStepUpScope.MANAGE,
    )
    response = await client.post(
        "/api/v1/stripe/connect/connect",
        headers=headers,
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_hosted_onboarding_reports_unactivated_platform(
    client, db_session, monkeypatch, issue_payment_step_up
):
    _configure(monkeypatch)
    _tenant, user, token = await _owner(db_session)
    headers = await issue_payment_step_up(
        token=token,
        user=user,
        scope=PaymentStepUpScope.MANAGE,
    )

    def create_account(**_params):
        raise stripe_connect.stripe.error.InvalidRequestError(
            "Your account must be activated in order to create accounts.",
            None,
        )

    monkeypatch.setattr(stripe_connect.stripe.Account, "create", create_account)
    response = await client.post(
        "/api/v1/stripe/connect/connect",
        headers=headers,
    )

    assert response.status_code == 409
    assert "platform activation" in response.json()["detail"]
    outcome = (await db_session.execute(
        select(PaymentStepUpAuditEvent).where(
            PaymentStepUpAuditEvent.event_type == "mutation_failed"
        )
    )).scalar_one()
    assert outcome.provider == "stripe"
    assert outcome.metadata_json == {
        "action": "stripe.connect",
        "reason": "provider_rejected",
    }


@pytest.mark.asyncio
async def test_deleted_connected_account_can_be_reset_by_shop(
    client, db_session, monkeypatch, issue_payment_step_up
):
    _configure(monkeypatch)
    tenant, user, token = await _owner(db_session)
    tenant.stripe_account_id = "acct_deleted"
    tenant.stripe_connection_type = "stripe_hosted"
    tenant.stripe_onboarding_complete = True
    await db_session.commit()

    def retrieve_account(_account_id):
        raise stripe_connect.stripe.error.InvalidRequestError(
            "No such account: acct_deleted",
            None,
        )

    monkeypatch.setattr(stripe_connect.stripe.Account, "retrieve", retrieve_account)
    headers = {"Authorization": f"Bearer {token}"}

    status_response = await client.get("/api/v1/stripe/connect/status", headers=headers)
    assert status_response.status_code == 200
    assert status_response.json()["verification_status"] == "unreachable"
    assert status_response.json()["onboarding_complete"] is False

    destructive_headers = await issue_payment_step_up(
        token=token,
        user=user,
        scope=PaymentStepUpScope.STRIPE_DISCONNECT,
    )
    reset_response = await client.post(
        "/api/v1/stripe/connect/disconnect",
        headers=destructive_headers,
    )
    assert reset_response.status_code == 200
    await db_session.refresh(tenant)
    assert tenant.stripe_account_id is None
    assert tenant.stripe_connection_type is None
