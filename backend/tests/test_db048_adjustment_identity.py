from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from app.services import db048_accounting_reconciliation as service


def envelope(fee="3"):
    tenant, attempt = uuid4(), uuid4()
    return NS(
        connection=NS(tenant_id=tenant, realm_id="realm"),
        attempt=NS(id=attempt, tenant_id=tenant, provider="quickbooks_payments",
                   applied_card_fee_amount=Decimal(fee), applied_card_fee_tax_amount=Decimal("0"),
                   processor_fee_amount=Decimal("0")),
        payment=NS(payment_number="PAY-123"),
        link=NS(tenant_id=tenant, attempt_id=attempt, qbo_realm_snapshot="realm",
                provider_fee_journal_id=None, account_mapping_snapshot={
                    "qbp_clearing_account": "Clearing", "card_fee_income_account": "Income",
                    "sales_tax_liability_account": "Tax"}))


def fixture(monkeypatch, env, existing=None):
    posted = []
    async def resolve(connection, value):
        return {"Clearing": "1", "Income": "2", "Tax": "3"}[value]
    async def query(*args):
        return [existing] if existing is not None else []
    async def request(connection, method, path, **kwargs):
        if method == "GET":
            return {"JournalEntry": existing if existing is not None else posted[0]}
        posted.append(dict(deepcopy(kwargs["json"]), Id="journal-1"))
        return {"JournalEntry": posted[-1]}
    monkeypatch.setattr(service, "_resolve_qbo_account_reference", resolve)
    monkeypatch.setattr(service, "_query", query)
    monkeypatch.setattr(service, "_request", request)
    return posted


@pytest.mark.asyncio
async def test_create_and_retry_preserves_identity(monkeypatch):
    env = envelope()
    posted = fixture(monkeypatch, env)
    await service._sync_db048_adjustment_journals(env)
    await service._sync_db048_adjustment_journals(env)
    assert env.link.provider_fee_journal_id == "journal-1"
    assert len(posted) == 1
    assert posted[0]["Line"][0]["JournalEntryLineDetail"]["AccountRef"]["value"] == "1"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", [None, "amount", "account", "direction", "note", "legacy", "malformed", "currency", "exchange", "nan", "doc", "id"])
async def test_existing_journal_semantics(monkeypatch, mutation):
    env = envelope()
    posted = fixture(monkeypatch, env)
    await service._sync_db048_adjustment_journals(env)
    candidate = deepcopy(posted[0])
    env.link.provider_fee_journal_id = None
    if mutation == "amount": candidate["Line"][0]["Amount"] = 4
    if mutation == "account": candidate["Line"][0]["JournalEntryLineDetail"]["AccountRef"]["value"] = "foreign"
    if mutation == "direction": candidate["Line"][0]["JournalEntryLineDetail"]["PostingType"] = "Credit"
    if mutation == "note": candidate["PrivateNote"] = "unrelated"
    if mutation == "legacy": candidate["PrivateNote"] = "DB-048 customer card fee and fee tax"
    if mutation == "malformed": candidate["Line"] = [None]
    if mutation == "currency": candidate["CurrencyRef"] = {"value": "EUR"}
    if mutation == "exchange": candidate["ExchangeRate"] = 1.2
    if mutation == "nan": candidate["ExchangeRate"] = "NaN"
    if mutation == "doc": candidate["DocNumber"] = "other"
    if mutation == "id":
        env.link.provider_fee_journal_id = "journal-1"
        candidate["Id"] = "different"
    posted = fixture(monkeypatch, env, candidate)
    if mutation:
        with pytest.raises(service.DB048ReconciliationError):
            await service._sync_db048_adjustment_journals(env)
    else:
        await service._sync_db048_adjustment_journals(env)
        assert env.link.provider_fee_journal_id == "journal-1"
    assert posted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["realm", "tenant", "attempt"])
async def test_ownership_prevents_provider_access(monkeypatch, boundary):
    env = envelope()
    if boundary == "realm": env.connection.realm_id = "other"
    if boundary == "tenant": env.connection.tenant_id = uuid4()
    if boundary == "attempt": env.link.attempt_id = uuid4()
    async def forbidden(*args, **kwargs):
        pytest.fail("provider accessed")
    monkeypatch.setattr(service, "_request", forbidden)
    monkeypatch.setattr(service, "_query", forbidden)
    with pytest.raises(service.DB048ReconciliationError):
        await service._sync_db048_adjustment_journals(env)


@pytest.mark.asyncio
async def test_zero_fee_has_no_journal(monkeypatch):
    env = envelope("0")
    posted = fixture(monkeypatch, env)
    await service._sync_db048_adjustment_journals(env)
    assert not posted
    assert env.link.provider_fee_journal_id is None
    env.link.provider_fee_journal_id = "already-recorded"
    with pytest.raises(service.DB048ReconciliationError, match="zero fee"):
        await service._sync_db048_adjustment_journals(env)


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["_sync_db048_adjustment_journals", "sync_db048_payment"])
async def test_zero_customer_fee_with_processor_fee_rejects_stale_identity_before_access(monkeypatch, entrypoint):
    env = envelope("0")
    env.attempt.processor_fee_amount = Decimal("2.99")
    env.link.provider_fee_journal_id = "stale-customer-fee"
    async def forbidden(*args, **kwargs):
        pytest.fail("Provider accessed before rejecting zero customer fee")
    for name in ("_request", "_query", "_ensure_db048_qbo_invoice", "_resolve_qbo_account_reference"):
        monkeypatch.setattr(service, name, forbidden)
    with pytest.raises(service.DB048ReconciliationError, match="zero fee"):
        await getattr(service, entrypoint)(env)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_response", [False, True, "currency", "exchange"])
async def test_fee_tax_and_post_response_validation(monkeypatch, bad_response):
    env = envelope()
    env.attempt.applied_card_fee_tax_amount = Decimal("0.15")
    fixture(monkeypatch, env)
    async def post(connection, method, path, **kwargs):
        payload = deepcopy(kwargs["json"])
        assert [line["Amount"] for line in payload["Line"]] == [3.15, 3, 0.15]
        assert payload["Line"][2]["JournalEntryLineDetail"]["AccountRef"]["value"] == "3"
        if bad_response == "currency":
            payload["CurrencyRef"] = {"value": "EUR"}
        elif bad_response == "exchange":
            payload["ExchangeRate"] = "Infinity"
        elif bad_response:
            payload["Line"][2]["Amount"] = 0.30
        return {"JournalEntry": dict(payload, Id="tax-journal")}
    monkeypatch.setattr(service, "_request", post)
    if bad_response:
        with pytest.raises(service.DB048ReconciliationError, match="conflict"):
            await service._sync_db048_adjustment_journals(env)
        assert env.link.provider_fee_journal_id is None
    else:
        await service._sync_db048_adjustment_journals(env)
        assert env.link.provider_fee_journal_id == "tax-journal"
