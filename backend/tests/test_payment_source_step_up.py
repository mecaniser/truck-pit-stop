from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from sqlalchemy import select

from app.core.payment_step_up import PaymentStepUpScope
from app.core import redis as redis_store
from app.core.rate_limit import limiter
from app.core.security import create_access_token, get_password_hash
from app.db.models.payment_step_up import PaymentStepUpAuditEvent, PaymentStepUpGrant
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


PASSWORD = "Local-dev-step-up-42!"


async def _owner(db_session, suffix: str, *, local_password: bool = True):
    tenant = Tenant(
        name=f"Step-up Garage {suffix}",
        slug=f"step-up-garage-{suffix}",
        zelle_email=f"before-{suffix}@example.test",
    )
    user = User(
        email=f"step-up-owner-{suffix}@example.test",
        hashed_password=get_password_hash(PASSWORD) if local_password else None,
        first_name="Step-up",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant=tenant,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([tenant, user])
    await db_session.commit()
    return tenant, user, create_access_token({"sub": str(user.id)})


async def _request_grant(client, token: str, scope: PaymentStepUpScope, **extra):
    return await client.post(
        "/api/v1/auth/step-up-grants",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": PASSWORD, "scope": scope.value, **extra},
    )


@pytest.mark.asyncio
async def test_step_up_issuance_stores_only_digest_and_records_audit(
    client, db_session
):
    _tenant, user, token = await _owner(db_session, "issue")

    response = await _request_grant(client, token, PaymentStepUpScope.MANAGE)

    assert response.status_code == 200
    body = response.json()
    raw_grant = body["grant_token"]
    assert body["scope"] == PaymentStepUpScope.MANAGE.value
    assert body["one_time"] is False
    grant = (await db_session.execute(select(PaymentStepUpGrant))).scalar_one()
    assert grant.user_id == user.id
    assert grant.token_digest == sha256(raw_grant.encode("utf-8")).hexdigest()
    assert raw_grant != grant.token_digest
    events = (await db_session.execute(select(PaymentStepUpAuditEvent))).scalars().all()
    assert [(event.event_type, event.scope) for event in events] == [
        ("issued", PaymentStepUpScope.MANAGE.value)
    ]


@pytest.mark.asyncio
async def test_wrong_password_and_workos_only_user_fail_closed(client, db_session):
    _tenant, _user, token = await _owner(db_session, "wrong-password")
    wrong = await client.post(
        "/api/v1/auth/step-up-grants",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "not-the-password", "scope": PaymentStepUpScope.MANAGE.value},
    )
    assert wrong.status_code == 403
    assert wrong.json()["detail"]["code"] == "STEP_UP_VERIFICATION_FAILED"

    _sso_tenant, _sso_user, sso_token = await _owner(
        db_session, "workos-only", local_password=False
    )
    unavailable = await _request_grant(
        client, sso_token, PaymentStepUpScope.MANAGE
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["detail"]["code"] == "STEP_UP_METHOD_UNAVAILABLE"


@pytest.mark.asyncio
async def test_zelle_mutation_requires_grant_and_preserves_state_when_missing(
    client, db_session
):
    tenant, _user, token = await _owner(db_session, "missing")

    response = await client.put(
        "/api/v1/admin/zelle-settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"zelle_email": "changed@example.test", "zelle_phone": None},
    )

    assert response.status_code == 428
    assert response.json()["detail"]["required_scope"] == PaymentStepUpScope.MANAGE.value
    await db_session.refresh(tenant)
    assert tenant.zelle_email == "before-missing@example.test"


@pytest.mark.asyncio
async def test_manage_grant_is_reusable_across_payment_source_changes(
    client, db_session
):
    tenant, _user, token = await _owner(db_session, "manage")
    issued = await _request_grant(client, token, PaymentStepUpScope.MANAGE)
    assert issued.status_code == 200
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Step-Up-Authorization": issued.json()["grant_token"],
    }

    first = await client.put(
        "/api/v1/admin/zelle-settings",
        headers=headers,
        json={"zelle_email": "first@example.test", "zelle_phone": None},
    )
    second = await client.put(
        "/api/v1/admin/zelle-settings",
        headers=headers,
        json={"zelle_email": "second@example.test", "zelle_phone": None},
    )
    disable = await client.put(
        "/api/v1/admin/zelle-settings",
        headers=headers,
        json={"zelle_email": None, "zelle_phone": None},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert disable.status_code == 200
    await db_session.refresh(tenant)
    assert tenant.zelle_email is None
    outcomes = (await db_session.execute(
        select(PaymentStepUpAuditEvent).where(
            PaymentStepUpAuditEvent.event_type == "mutation_succeeded"
        )
    )).scalars().all()
    assert [event.metadata_json for event in outcomes] == [
        {
            "action": "zelle.contacts.update",
            "configured_before": True,
            "configured_after": True,
        },
        {
            "action": "zelle.contacts.update",
            "configured_before": True,
            "configured_after": True,
        },
        {
            "action": "zelle.contacts.update",
            "configured_before": True,
            "configured_after": False,
        },
    ]
    assert "first@example.test" not in str(outcomes)
    assert "second@example.test" not in str(outcomes)


def test_step_up_and_legacy_password_oracle_share_strict_rate_limits():
    expected = {"5 per 15 minute", "20 per 1 hour"}
    for endpoint in (
        "app.api.v1.endpoints.auth.create_payment_step_up_grant",
        "app.api.v1.endpoints.auth.verify_user_password",
    ):
        assert {str(limit.limit) for limit in limiter._route_limits[endpoint]} == expected


@pytest.mark.asyncio
async def test_destructive_grant_is_one_time_and_replay_is_rejected(
    client, db_session
):
    tenant, _user, token = await _owner(db_session, "one-time")
    issued = await _request_grant(client, token, PaymentStepUpScope.ZELLE_DISABLE)
    assert issued.status_code == 200
    assert issued.json()["one_time"] is True
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Step-Up-Authorization": issued.json()["grant_token"],
    }

    first = await client.put(
        "/api/v1/admin/zelle-settings",
        headers=headers,
        json={"zelle_email": None, "zelle_phone": None},
    )
    replay = await client.put(
        "/api/v1/admin/zelle-settings",
        headers=headers,
        json={"zelle_email": None, "zelle_phone": None},
    )

    assert first.status_code == 200
    assert replay.status_code == 428
    await db_session.refresh(tenant)
    assert tenant.zelle_email is None


@pytest.mark.asyncio
async def test_empty_zelle_qr_accepts_manage_or_exact_destructive_grant(
    client, db_session
):
    tenant, _user, token = await _owner(db_session, "qr-empty")
    tenant.zelle_qr_image = "data:image/png;base64,existing"
    await db_session.commit()
    managed = await _request_grant(client, token, PaymentStepUpScope.MANAGE)
    managed_headers = {
        "Authorization": f"Bearer {token}",
        "X-Step-Up-Authorization": managed.json()["grant_token"],
    }

    removed_with_manage = await client.put(
        "/api/v1/admin/zelle-qr-image",
        headers=managed_headers,
        json={"zelle_qr_image": ""},
    )
    assert removed_with_manage.status_code == 200
    await db_session.refresh(tenant)
    assert tenant.zelle_qr_image is None

    tenant.zelle_qr_image = "data:image/png;base64,replaced"
    await db_session.commit()

    destructive = await _request_grant(
        client, token, PaymentStepUpScope.ZELLE_QR_REMOVE
    )
    removed = await client.put(
        "/api/v1/admin/zelle-qr-image",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Step-Up-Authorization": destructive.json()["grant_token"],
        },
        json={"zelle_qr_image": ""},
    )
    assert removed.status_code == 200
    await db_session.refresh(tenant)
    assert tenant.zelle_qr_image is None


@pytest.mark.asyncio
async def test_manage_grant_cannot_cross_into_non_payment_destructive_scope(
    client, db_session
):
    _tenant, _user, token = await _owner(db_session, "manage-scope-boundary")
    issued = await _request_grant(client, token, PaymentStepUpScope.MANAGE)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Step-Up-Authorization": issued.json()["grant_token"],
    }

    response = await client.post(
        "/api/v1/repair-orders/00000000-0000-0000-0000-000000000000/force-void",
        headers=headers,
        json={"reason": "Scope boundary test only"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Step-up grant scope is not allowed for this action"


@pytest.mark.asyncio
async def test_expiry_revocation_and_token_version_change_invalidate_grants(
    client, db_session
):
    tenant, user, token = await _owner(db_session, "invalidation")

    async def issue_and_grant():
        response = await _request_grant(client, token, PaymentStepUpScope.MANAGE)
        raw = response.json()["grant_token"]
        grant = (
            await db_session.execute(
                select(PaymentStepUpGrant).where(
                    PaymentStepUpGrant.token_digest
                    == sha256(raw.encode("utf-8")).hexdigest()
                )
            )
        ).scalar_one()
        return raw, grant

    expired_raw, expired = await issue_and_grant()
    expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    expired_response = await client.put(
        "/api/v1/admin/zelle-settings",
        headers={"Authorization": f"Bearer {token}", "X-Step-Up-Authorization": expired_raw},
        json={"zelle_email": "expired@example.test", "zelle_phone": None},
    )
    assert expired_response.status_code == 428

    revoked_raw, revoked = await issue_and_grant()
    revoked.revoked_at = datetime.now(timezone.utc)
    await db_session.commit()
    revoked_response = await client.put(
        "/api/v1/admin/zelle-settings",
        headers={"Authorization": f"Bearer {token}", "X-Step-Up-Authorization": revoked_raw},
        json={"zelle_email": "revoked@example.test", "zelle_phone": None},
    )
    assert revoked_response.status_code == 428

    version_raw, _version_grant = await issue_and_grant()
    await redis_store.increment_token_version(str(user.id))
    version_response = await client.put(
        "/api/v1/admin/zelle-settings",
        headers={"Authorization": f"Bearer {token}", "X-Step-Up-Authorization": version_raw},
        json={"zelle_email": "version@example.test", "zelle_phone": None},
    )
    # The primary access token is invalidated before the step-up dependency
    # runs, so token-version changes fail even earlier than a 428 grant check.
    assert version_response.status_code == 401
    await db_session.refresh(tenant)
    assert tenant.zelle_email == "before-invalidation@example.test"


@pytest.mark.asyncio
async def test_concurrent_destructive_replay_allows_exactly_one_mutation(
    client, db_session
):
    _tenant, _user, token = await _owner(db_session, "concurrent")
    issued = await _request_grant(client, token, PaymentStepUpScope.ZELLE_DISABLE)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Step-Up-Authorization": issued.json()["grant_token"],
    }

    responses = await asyncio.gather(
        client.put(
            "/api/v1/admin/zelle-settings",
            headers=headers,
            json={"zelle_email": None, "zelle_phone": None},
        ),
        client.put(
            "/api/v1/admin/zelle-settings",
            headers=headers,
            json={"zelle_email": None, "zelle_phone": None},
        ),
    )

    assert sorted(response.status_code for response in responses) == [200, 428]


@pytest.mark.asyncio
async def test_grant_is_bound_to_primary_session_and_user(client, db_session):
    _tenant, _user, original_token = await _owner(db_session, "session")
    issued = await _request_grant(
        client, original_token, PaymentStepUpScope.MANAGE
    )
    raw_grant = issued.json()["grant_token"]

    # A fresh primary login for the same user has another JTI and cannot reuse
    # the older browser session's step-up credential.
    same_user_id = (await db_session.execute(
        select(User.id).where(User.email == "step-up-owner-session@example.test")
    )).scalar_one()
    fresh_token = create_access_token({"sub": str(same_user_id)})
    session_mismatch = await client.put(
        "/api/v1/admin/zelle-settings",
        headers={
            "Authorization": f"Bearer {fresh_token}",
            "X-Step-Up-Authorization": raw_grant,
        },
        json={"zelle_email": "fresh@example.test", "zelle_phone": None},
    )
    assert session_mismatch.status_code == 428

    _other_tenant, _other_user, other_token = await _owner(db_session, "foreign-user")
    foreign_user = await client.put(
        "/api/v1/admin/zelle-settings",
        headers={
            "Authorization": f"Bearer {other_token}",
            "X-Step-Up-Authorization": raw_grant,
        },
        json={"zelle_email": "foreign@example.test", "zelle_phone": None},
    )
    assert foreign_user.status_code == 428


@pytest.mark.asyncio
async def test_cookie_authenticated_step_up_requires_trusted_origin(client, db_session):
    _tenant, _user, token = await _owner(db_session, "csrf")
    client.cookies.set("access_token", token)

    response = await client.post(
        "/api/v1/auth/step-up-grants",
        json={"password": PASSWORD, "scope": PaymentStepUpScope.MANAGE.value},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Trusted browser origin required"


@pytest.mark.asyncio
async def test_cookie_authenticated_step_up_accepts_configured_origin(
    client, db_session
):
    _tenant, _user, token = await _owner(db_session, "trusted-origin")
    client.cookies.set("access_token", token)

    response = await client.post(
        "/api/v1/auth/step-up-grants",
        headers={"Origin": "http://localhost:5173"},
        json={"password": PASSWORD, "scope": PaymentStepUpScope.MANAGE.value},
    )

    assert response.status_code == 200
    assert response.json()["scope"] == PaymentStepUpScope.MANAGE.value
