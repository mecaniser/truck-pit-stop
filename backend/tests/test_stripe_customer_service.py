from types import SimpleNamespace

import pytest

from app.services import stripe_customer_service


class FakeDatabase:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def customer(**overrides):
    values = {
        "id": "customer-1",
        "tenant_id": "tenant-1",
        "first_name": "Avery",
        "last_name": "Driver",
        "company_name": None,
        "email": "avery@example.com",
        "stripe_customer_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_creates_customer_inside_connected_account(monkeypatch):
    database = FakeDatabase()
    payer = customer()
    created = {}

    def create(**params):
        created.update(params)
        return {"id": "cus_connected"}

    monkeypatch.setattr(stripe_customer_service.stripe.Customer, "create", create)

    customer_id = await stripe_customer_service.ensure_connected_stripe_customer(
        database,
        payer,
        "acct_connected",
    )

    assert customer_id == "cus_connected"
    assert payer.stripe_customer_id == "cus_connected"
    assert database.commits == 1
    assert created["stripe_account"] == "acct_connected"
    assert created["email"] == "avery@example.com"


@pytest.mark.asyncio
async def test_reuses_existing_customer_in_connected_account(monkeypatch):
    database = FakeDatabase()
    payer = customer(stripe_customer_id="cus_existing")
    modified = {}

    def modify(customer_id, **params):
        modified["customer_id"] = customer_id
        modified.update(params)

    monkeypatch.setattr(stripe_customer_service.stripe.Customer, "modify", modify)

    customer_id = await stripe_customer_service.ensure_connected_stripe_customer(
        database,
        payer,
        "acct_connected",
    )

    assert customer_id == "cus_existing"
    assert database.commits == 0
    assert modified["customer_id"] == "cus_existing"
    assert modified["stripe_account"] == "acct_connected"
