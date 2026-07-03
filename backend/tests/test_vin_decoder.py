from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.api.v1.endpoints import customers as customers_endpoint
from app.core.dependencies import get_current_active_user
from app.db.models.user import UserRole
from app.schemas.customer import CustomerCreate
from app.services.vin_decoder_service import VINDecodeResult, decode_vin


FREIGHTLINER_VIN = "1FUJGLDR5BSAY7890"


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload: dict, calls: list[tuple[str, dict | None]], *args, **kwargs):
        self._payload = payload
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params: dict | None = None):
        self._calls.append((url, params))
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_decode_vin_parses_expected_fields(monkeypatch):
    calls: list[tuple[str, dict | None]] = []
    payload = {
        "Results": [
            {
                "Make": "FREIGHTLINER",
                "Model": "CASCADIA",
                "ModelYear": "2011",
                "VehicleType": "TRUCK",
                "BodyClass": "Truck-Tractor",
                "DriveType": "6x4",
                "FuelTypePrimary": "Diesel",
                "EngineCylinders": "6",
                "DisplacementL": "14.8",
                "EngineHP": "455",
                "TransmissionStyle": "Automatic",
                "GVWR": "Class 8",
                "ErrorCode": "0",
                "ErrorText": "0 - VIN decoded clean.",
            }
        ]
    }

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(payload, calls, *args, **kwargs),
    )

    result = await decode_vin(FREIGHTLINER_VIN, model_year=2011)

    assert isinstance(result, VINDecodeResult)
    assert result.vin == FREIGHTLINER_VIN
    assert result.make == "FREIGHTLINER"
    assert result.model == "CASCADIA"
    assert result.year == 2011
    assert result.engine_cylinders == 6
    assert result.engine_displacement_l == 14.8
    assert result.engine_hp == 455
    assert calls and calls[0][1] == {"format": "json", "modelyear": "2011"}


@pytest.mark.asyncio
async def test_decode_vin_handles_empty_result_set(monkeypatch):
    calls: list[tuple[str, dict | None]] = []
    payload = {"Results": []}

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(payload, calls, *args, **kwargs),
    )

    result = await decode_vin("INVALID123")

    assert result.vin == "INVALID123"
    assert result.error_code == "0"
    assert result.error_text == "No results returned"


def _build_customers_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(customers_endpoint.router, prefix="/api/v1/customers")
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        role=UserRole.GARAGE_ADMIN,
    )
    return app


@pytest.mark.asyncio
async def test_decode_vin_endpoint_success(monkeypatch):
    async def _fake_decode(vin: str, model_year=None):
        return VINDecodeResult(vin=vin, make="FREIGHTLINER", model="CASCADIA", year=2011)

    monkeypatch.setattr(customers_endpoint, "decode_vin", _fake_decode)
    transport = httpx.ASGITransport(app=_build_customers_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/customers/vin/decode/{FREIGHTLINER_VIN}")

    assert response.status_code == 200
    data = response.json()
    assert data["vin"] == FREIGHTLINER_VIN
    assert data["make"] == "FREIGHTLINER"
    assert data["model"] == "CASCADIA"
    assert data["year"] == 2011


@pytest.mark.asyncio
async def test_decode_vin_endpoint_returns_502_on_upstream_failure(monkeypatch):
    async def _fake_decode(_vin: str, _model_year=None):
        raise RuntimeError("upstream timeout")

    monkeypatch.setattr(customers_endpoint, "decode_vin", _fake_decode)
    transport = httpx.ASGITransport(app=_build_customers_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/customers/vin/decode/{FREIGHTLINER_VIN}")

    assert response.status_code == 502
    assert "Failed to decode VIN" in response.json()["detail"]


class _UnusedDB:
    async def execute(self, *args, **kwargs):
        raise AssertionError("execute should not be called for this validation error path")


@pytest.mark.asyncio
async def test_create_customer_requires_vehicle_or_no_vehicle_flag():
    payload = CustomerCreate(
        first_name="Test",
        last_name="Customer",
        company_name="Test Customer LLC",
        email="test@example.com",
    )
    current_user = SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        role=UserRole.GARAGE_ADMIN,
    )

    with pytest.raises(HTTPException) as exc_info:
        await customers_endpoint.create_customer(payload, db=_UnusedDB(), current_user=current_user)

    assert exc_info.value.status_code == 400
    assert "vehicle" in str(exc_info.value.detail).lower()
