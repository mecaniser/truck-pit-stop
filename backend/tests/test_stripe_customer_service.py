from types import SimpleNamespace

import pytest

from app.services import stripe_customer_service


class FakeDatabase:
    def __init__(self, payer):
        self.commits = 0
        self.payer = payer
        self.query = None

    async def execute(self, query):
        self.query = query
        return SimpleNamespace(scalar_one_or_none=lambda: self.payer)

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
    payer = customer()
    database = FakeDatabase(payer)
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
    payer = customer(stripe_customer_id="cus_existing")
    database = FakeDatabase(payer)
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


@pytest.mark.asyncio
async def test_stale_caller_reloads_the_locked_reference_before_recovery(monkeypatch):
    stale = customer(stripe_customer_id="cus_old")
    recovered = customer(stripe_customer_id="cus_recovered")
    database = FakeDatabase(recovered)
    modified = []
    monkeypatch.setattr(stripe_customer_service.stripe.Customer, "modify", lambda cid, **kw: modified.append(cid))
    monkeypatch.setattr(stripe_customer_service.stripe.Customer, "create", lambda **kw: pytest.fail("must reuse recovery"))
    result = await stripe_customer_service.ensure_connected_stripe_customer(database, stale, "acct_connected")
    assert result == "cus_recovered"
    assert modified == ["cus_recovered"]
    assert database.commits == 0
    assert database.query._for_update_arg is not None
    assert database.query.get_execution_options()["populate_existing"] is True
