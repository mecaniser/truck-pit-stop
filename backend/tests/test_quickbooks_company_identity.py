from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import quickbooks
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.user import UserRole
from app.services import quickbooks_accounting_service as accounting
from tests.test_quickbooks_connection import _owner_with_token


@pytest.mark.asyncio
async def test_company_mapping_is_bounded_allowlist(monkeypatch):
    request = AsyncMock(return_value={"CompanyInfo": {
        "CompanyName": " Truck Pit Stop LLC ", "LegalName": "L" * 300,
        "CompanyAddr": {"Line1": "123 Main", "City": "Charlotte", "CountrySubDivisionCode": "NC", "PostalCode": "28201", "Country": "US", "Lat": "secret"},
        "Email": {"Address": "office@example.com"}, "PrimaryPhone": {"FreeFormNumber": "704-555-0100"},
        "EmployerId": "SECRET-TAX-ID", "CompanyUserAdminEmail": "SECRET-ADMIN",
    }})
    monkeypatch.setattr(accounting, "_request", request)
    connection = QuickBooksConnection(realm_id="123")
    result = await accounting.get_company_identity(connection)
    request.assert_awaited_once_with(connection, "GET", "companyinfo/123")
    assert result == {
        "name": "Truck Pit Stop LLC", "legal_name": "L" * 256,
        "address_lines": ["123 Main", "Charlotte, NC, 28201", "US"],
        "email": "office@example.com", "phone": "704-555-0100",
    }
    assert "SECRET" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"CompanyInfo": None}, {"CompanyInfo": []}, {"CompanyInfo": {}}, {"CompanyInfo": {"CompanyName": 12, "CompanyAddr": []}}])
async def test_invalid_company_identity_is_unavailable(monkeypatch, payload):
    monkeypatch.setattr(accounting, "_request", AsyncMock(return_value=payload))
    with pytest.raises(accounting.QuickBooksAccountingError):
        await accounting.get_company_identity(QuickBooksConnection(realm_id="123"))


@pytest.mark.asyncio
async def test_partial_identity_omits_missing_fields(monkeypatch):
    monkeypatch.setattr(accounting, "_request", AsyncMock(return_value={"CompanyInfo": {"CompanyName": "Shop", "Email": []}}))
    assert await accounting.get_company_identity(QuickBooksConnection(realm_id="123")) == {
        "name": "Shop", "legal_name": None, "address_lines": [], "email": None, "phone": None,
    }


@pytest.mark.asyncio
async def test_identity_endpoint_tenant_bound_read_only(client, db_session, monkeypatch):
    tenant, _, token = await _owner_with_token(db_session)
    other, _, other_token = await _owner_with_token(db_session, suffix="two")
    connections = [QuickBooksConnection(tenant_id=t.id, realm_id=r, status="connected", scopes=quickbooks.QUICKBOOKS_ACCOUNTING_SCOPE, encrypted_access_token="unchanged", encrypted_refresh_token="unchanged") for t, r in [(tenant, "123"), (other, "456")]]
    db_session.add_all(connections)
    await db_session.commit()
    async def identity(connection):
        return {"name": f"Company {connection.realm_id}"}
    provider = AsyncMock(side_effect=identity)
    refresh = AsyncMock(side_effect=AssertionError("No token refresh allowed"))
    monkeypatch.setattr(quickbooks, "get_company_identity", provider)
    monkeypatch.setattr(quickbooks, "refresh_access_token", refresh)
    monkeypatch.setattr(quickbooks.settings, "QUICKBOOKS_ACCOUNTING_ENVIRONMENT", "production")
    for bearer, realm in [(token, "123"), (other_token, "456")]:
        response = await client.get("/api/v1/quickbooks/company-identity?realm_id=attacker&tenant_id=attacker", headers={"Authorization": f"Bearer {bearer}"})
        assert response.status_code == 200
        assert response.json()["realm_id"] == realm
        assert response.json()["company"]["name"] == f"Company {realm}"
        assert response.json()["environment"] == "production"
    refresh.assert_not_awaited()
    for connection in connections:
        await db_session.refresh(connection)
        assert connection.encrypted_access_token == "unchanged"
        assert connection.encrypted_refresh_token == "unchanged"
        assert connection.status == "connected"
        assert connection.last_token_refresh_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("state,scope,expected", [(None, "", "not_connected"), ("disconnected", "", "not_connected"), ("connected", "com.intuit.quickbooks.payment", "unavailable")])
async def test_missing_connection_or_scope_never_calls_provider(client, db_session, monkeypatch, state, scope, expected):
    tenant, _, token = await _owner_with_token(db_session)
    if state:
        db_session.add(QuickBooksConnection(tenant_id=tenant.id, realm_id="123", status=state, scopes=scope))
        await db_session.commit()
    provider = AsyncMock(side_effect=AssertionError("No provider call allowed"))
    monkeypatch.setattr(quickbooks, "get_company_identity", provider)
    response = await client.get("/api/v1/quickbooks/company-identity", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["status"] == expected
    assert response.json()["company"] is None
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_failure_preserves_connection_health(client, db_session, monkeypatch):
    tenant, _, token = await _owner_with_token(db_session)
    db_session.add(QuickBooksConnection(tenant_id=tenant.id, realm_id="123", status="connected", scopes=quickbooks.QUICKBOOKS_ACCOUNTING_SCOPE, last_token_refresh_error="prior-health"))
    await db_session.commit()
    monkeypatch.setattr(quickbooks, "get_company_identity", AsyncMock(side_effect=accounting.QuickBooksAccountingError("SECRET provider failure")))
    response = await client.get("/api/v1/quickbooks/company-identity", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert "SECRET" not in response.text
    connection = (await db_session.execute(select(QuickBooksConnection))).scalar_one()
    assert connection.status == "connected"
    assert connection.last_token_refresh_error == "prior-health"


@pytest.mark.asyncio
async def test_identity_requires_authenticated_shop_administrator(client, db_session, monkeypatch):
    _, user, token = await _owner_with_token(db_session)
    user.role = UserRole.MECHANIC
    await db_session.commit()
    provider = AsyncMock()
    monkeypatch.setattr(quickbooks, "get_company_identity", provider)
    assert (await client.get("/api/v1/quickbooks/company-identity")).status_code == 401
    assert (await client.get("/api/v1/quickbooks/company-identity", headers={"Authorization": f"Bearer {token}"})).status_code == 403
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_requires_explicit_payments_permission(client, db_session, monkeypatch):
    _, user, token = await _owner_with_token(db_session)
    user.role = UserRole.GARAGE_ADMIN
    user.permissions = {}
    await db_session.commit()
    provider = AsyncMock()
    monkeypatch.setattr(quickbooks, "get_company_identity", provider)
    response = await client.get("/api/v1/quickbooks/company-identity", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    provider.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_identity_never_commits_flushes_or_refreshes(monkeypatch, fails):
    connection = QuickBooksConnection(realm_id="123", status="connected", scopes=quickbooks.QUICKBOOKS_ACCOUNTING_SCOPE)
    db = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(quickbooks, "_get_connection", AsyncMock(return_value=connection))
    monkeypatch.setattr(quickbooks, "get_company_identity", AsyncMock(side_effect=accounting.QuickBooksAccountingError("secret") if fails else None, return_value={"name": "Shop"}))
    user = SimpleNamespace(role=UserRole.GARAGE_OWNER, tenant_id="owned")
    result = await quickbooks.quickbooks_company_identity(db, user)
    assert result.status == ("unavailable" if fails else "available")
    db.commit.assert_not_awaited()
    db.flush.assert_not_awaited()
    db.refresh.assert_not_awaited()
