from uuid import uuid4

import pytest

from app.api.v1.endpoints.invoices import generate_invoice_number
from app.db.models.tenant import Tenant


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value


@pytest.mark.asyncio
async def test_invoice_number_uses_tenant_shop_prefix() -> None:
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Truck Pit Stop Wisconsin",
        order_number_prefix="TPS",
    )

    class FakeSession:
        calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return _ScalarResult(tenant if self.calls == 1 else None)

    number = await generate_invoice_number(FakeSession(), tenant_id)

    tenant_key = str(tenant_id).replace("-", "").upper()[:8]
    assert number == f"TPS-{tenant_key}-000001"
    assert len(number) <= 21


@pytest.mark.asyncio
async def test_invoice_number_derives_shop_prefix_when_unconfigured() -> None:
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Truck Pit Stop",
        order_number_prefix=None,
    )

    class FakeSession:
        calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return _ScalarResult(tenant if self.calls == 1 else None)

    number = await generate_invoice_number(FakeSession(), tenant_id)

    assert number.startswith("TPS-")
    assert number.endswith("-000001")


@pytest.mark.asyncio
async def test_invoice_number_caps_configured_prefix_for_qbo_doc_number() -> None:
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Long Prefix Repair",
        order_number_prefix="ABCDEFGHIJ",
    )

    class FakeSession:
        calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return _ScalarResult(tenant if self.calls == 1 else None)

    number = await generate_invoice_number(FakeSession(), tenant_id)

    tenant_key = str(tenant_id).replace("-", "").upper()[:8]
    assert number == f"ABCDE-{tenant_key}-000001"
    assert len(number) == 21
