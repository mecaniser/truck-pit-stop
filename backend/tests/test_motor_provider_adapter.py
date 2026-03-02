from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.labor_provider.base import VehicleContext
from app.services.labor_provider.motor import MotorLaborProvider


@pytest.mark.asyncio
async def test_search_operations_returns_fallback_when_disabled(monkeypatch):
    monkeypatch.setattr("app.services.labor_provider.motor.settings.MOTOR_ENABLED", False)
    provider = MotorLaborProvider()

    candidates, warnings = await provider.search_operations(
        VehicleContext(vin="1XPBDP9X8JD123456", year=2022, make="Peterbilt", model="579"),
        "brake",
    )

    assert candidates
    assert any(c.operation_id == "brake-change" for c in candidates)
    assert warnings
    assert warnings[0].code == "provider_disabled"


@pytest.mark.asyncio
async def test_get_operation_estimate_returns_fallback_when_disabled(monkeypatch):
    monkeypatch.setattr("app.services.labor_provider.motor.settings.MOTOR_ENABLED", False)
    provider = MotorLaborProvider()

    estimate = await provider.get_operation_estimate(
        VehicleContext(vin="1XPBDP9X8JD123456"),
        "egr-replacement",
    )

    assert estimate.operation_id == "egr-replacement"
    assert estimate.estimated_hours >= Decimal("0.00")
    assert estimate.warnings
