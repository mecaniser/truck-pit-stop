from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models.tenant import Tenant
from app.services.stripe_platform_fee import platform_fee_amount_cents, platform_fee_percent_for


def test_uses_platform_default_when_tenant_has_no_override(monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_FEE_PERCENT", 1.5)
    tenant = Tenant(name="Default Fee Garage", slug="default-fee-garage")
    assert platform_fee_percent_for(tenant) == Decimal("1.500")
    assert platform_fee_amount_cents(10_003, Decimal("1.500")) == 150


def test_tenant_fee_override_takes_precedence():
    tenant = Tenant(
        name="Override Fee Garage",
        slug="override-fee-garage",
        stripe_platform_fee_percent=Decimal("2.750"),
    )
    assert platform_fee_percent_for(tenant) == Decimal("2.750")
    assert platform_fee_amount_cents(10_000, platform_fee_percent_for(tenant)) == 275


def test_rejects_unsafe_fee_configuration(monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_FEE_PERCENT", 21)
    tenant = Tenant(name="Unsafe Fee Garage", slug="unsafe-fee-garage")
    with pytest.raises(ValueError, match="between 0 and 20"):
        platform_fee_percent_for(tenant)
