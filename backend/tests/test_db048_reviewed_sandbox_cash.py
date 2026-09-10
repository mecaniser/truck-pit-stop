from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.payment import Payment
from app.db.models.invoice import Invoice, InvoiceStatus
from app.services import invoice_cash_service as cash
from app.services.historical_export_hold import digest
from app.services.invoice_settlement_service import SettlementDomainError
from scripts.review_sandbox_cash import prepare, apply_review
from tests.test_db048_cash import context, pay
from tests.test_db048_cash_payment_timing import event


async def reviewed(db, monkeypatch, *, legacy_no_dispatch=False, local_void_parent=False):
    ctx = await context(db, monkeypatch)
    ctx[3].accounting_policy = "historical_export_hold"
    queued = event(ctx[3], status="dead", attempts=5, payload={"cash_export_ambiguous": True})
    queued.last_error = "QuickBooksAccountingError HTTP403"
    if legacy_no_dispatch:
        queued.payload = {**queued.payload, "cash_no_dispatch": True}
    db.add(queued)
    parent = None
    if local_void_parent:
        parent = Invoice(tenant_id=ctx[0].id, repair_order_id=ctx[3].repair_order_id,
            invoice_number="PARENT-LOCAL-VOID-000019", subtotal=ctx[3].subtotal, total_amount=ctx[3].total_amount,
            status=InvoiceStatus.CANCELLED, voided_at=datetime.now(timezone.utc),
            quickbooks_sync_status="voided", quickbooks_synced_at=datetime.now(timezone.utc))
        db.add(parent)
        await db.flush()
        ctx[3].supersedes_invoice_id = parent.id
        db.add(event(parent, status="succeeded", attempts=1, payload={"operation": "void"}))
    await db.flush()
    connection = await db.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == ctx[0].id))
    scope = dict(tenant_id=str(ctx[0].id), invoice_id=str(ctx[3].id), event_id=str(queued.id),
        confirmation_realm_id=connection.realm_id, evidence_manifest_sha256="a"*64,
        reviewer="independent-reviewed-evidence", observed_environment="sandbox")
    if parent:
        scope["reviewed_local_void_ancestor_ids"] = [str(parent.id)]
    manifest = await prepare(db, scope)
    await apply_review(db, manifest, digest(manifest))
    # A later payment request eagerly loads these; operator refresh does not.
    await db.refresh(ctx[3], attribute_names=["repair_order"])
    await db.refresh(ctx[3].repair_order, attribute_names=["customer"])
    return ctx, queued, connection, manifest


@pytest.mark.asyncio
async def test_review_is_metadata_only_and_idempotent(db_session, monkeypatch):
    ctx, queued, _, manifest = await reviewed(db_session, monkeypatch)
    reason, _ = await cash.cash_eligibility(db_session, ctx[3], ctx[4])
    assert reason is None
    assert queued.status == "dead" and queued.attempt_count == 5
    assert queued.payload["cash_export_ambiguous"] is True
    assert queued.last_error == "QuickBooksAccountingError HTTP403"
    assert ctx[3].accounting_policy == "historical_export_hold"
    assert (await apply_review(db_session, manifest, digest(manifest)))["changed_fields"] == []
    assert await db_session.scalar(select(Payment.id)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["tenant", "invoice", "event", "environment", "count", "payload", "provider", "lease", "digest", "schema"])
async def test_review_drift_rejected(db_session, monkeypatch, defect):
    ctx, queued, _, _ = await reviewed(db_session, monkeypatch)
    marker = dict(queued.payload[cash.CASH_REVIEW_KEY])
    if defect in {"tenant", "invoice", "event"}: marker[f"{defect}_id"] = str(uuid4())
    if defect == "environment": marker["observed_environment"] = "production"
    if defect == "digest": marker["original_history_sha256"] = "b"*64
    if defect == "schema": marker["schema"] = "unknown"
    queued.payload = {**queued.payload, cash.CASH_REVIEW_KEY: marker}
    if defect == "count": queued.attempt_count += 1
    if defect == "payload": queued.payload = {**queued.payload, "new_history": True}
    if defect == "provider": queued.provider_message_id = "external"
    if defect == "lease": queued.lock_token = "active"
    await db_session.flush()
    assert not cash.valid_sandbox_cash_review(queued, ctx[3])
    assert (await cash.cash_eligibility(db_session, ctx[3], ctx[4]))[0] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["absent", "no_dispatch", "match", "malformed", "error", "realm", "sandbox"])
async def test_confirmation_fresh_production_absence_or_no_receipt(db_session, monkeypatch, outcome):
    from app.services import quickbooks_accounting_service as accounting
    ctx, queued, connection, _ = await reviewed(db_session, monkeypatch, legacy_no_dispatch=outcome == "no_dispatch")
    monkeypatch.setattr(settings, "QUICKBOOKS_ACCOUNTING_ENVIRONMENT", "production" if outcome != "sandbox" else "sandbox")
    if outcome == "realm": connection.realm_id = "changed"
    requests = []
    async def lookup(_connection, method, resource, **kwargs):
        requests.append(kwargs["params"]["query"])
        assert settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT == "production" and method == "GET"
        if outcome == "error": raise RuntimeError("unavailable")
        if outcome == "malformed": return {}
        if outcome == "match": return {"QueryResponse": {"Invoice": [{"Id": "123"}]}}
        return {"QueryResponse": {}}
    monkeypatch.setattr(accounting, "_request", lookup)
    if outcome in {"absent", "no_dispatch"}:
        await pay(db_session, ctx)
        assert ctx[3].accounting_policy == "local_cash_only"
        assert len(requests) == len({ctx[3].invoice_number, ctx[3].invoice_number[:21]})
    else:
        with pytest.raises(SettlementDomainError): await pay(db_session, ctx)
        assert ctx[3].accounting_policy == "historical_export_hold"
        assert await db_session.scalar(select(Payment.id)) is None


@pytest.mark.asyncio
async def test_operator_rejects_ancestry_payment_and_manifest_drift(db_session, monkeypatch):
    from decimal import Decimal
    ctx, queued, _, manifest = await reviewed(db_session, monkeypatch)
    queued.last_error = "changed history"
    await db_session.flush()
    with pytest.raises(ValueError): await apply_review(db_session, manifest, digest(manifest))
    # Ancestry is rechecked independently of the review marker.
    parent = await context(db_session, monkeypatch)
    parent[3].tenant_id = ctx[0].id
    parent[4].tenant_id = ctx[0].id
    parent[4].active_pending_principal = Decimal("10")
    ctx[3].supersedes_invoice_id = parent[3].id
    await db_session.flush()
    assert await cash.reviewed_cash_ancestry_reason(db_session, ctx[3]) is not None


@pytest.mark.asyncio
async def test_reviewed_confirmation_rechecks_parent_reservation(db_session, monkeypatch):
    from decimal import Decimal
    from app.services import quickbooks_accounting_service as accounting
    ctx, _, _, _ = await reviewed(db_session, monkeypatch)
    parent = await context(db_session, monkeypatch)
    parent[3].tenant_id = ctx[0].id
    parent[4].tenant_id = ctx[0].id
    parent[4].active_pending_principal = Decimal("232.48")
    ctx[3].supersedes_invoice_id = parent[3].id
    await db_session.flush()
    provider = AsyncMock(side_effect=AssertionError("parent reservation must block before lookup"))
    monkeypatch.setattr(accounting, "_request", provider)
    with pytest.raises(SettlementDomainError, match="replaced invoice has payment activity"):
        await pay(db_session, ctx)
    provider.assert_not_awaited()
    assert ctx[3].accounting_policy == "historical_export_hold"


@pytest.mark.asyncio
async def test_operator_digest_and_conflict_rejected(db_session, monkeypatch):
    ctx, queued, _, manifest = await reviewed(db_session, monkeypatch)
    with pytest.raises(ValueError, match="digest"):
        await apply_review(db_session, manifest, "0"*64)
    marker = {**queued.payload[cash.CASH_REVIEW_KEY], "reviewer": "different"}
    queued.payload = {**queued.payload, cash.CASH_REVIEW_KEY: marker}
    await db_session.flush()
    with pytest.raises(ValueError, match="Conflicting"):
        await apply_review(db_session, manifest, digest(manifest))


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["none", "provider_id", "chain_unlinked", "history"])
async def test_reviewed_local_void_parent_requires_parent_absence_and_no_drift(db_session, monkeypatch, defect):
    from app.services import quickbooks_accounting_service as accounting
    ctx, _, _, _ = await reviewed(db_session, monkeypatch, local_void_parent=True)
    parent = await db_session.get(Invoice, ctx[3].supersedes_invoice_id)
    original_timestamp = parent.quickbooks_synced_at
    if defect == "provider_id": parent.quickbooks_invoice_id = "genuine-provider-id"
    if defect == "chain_unlinked": ctx[3].supersedes_invoice_id = None
    if defect == "history": parent.quickbooks_sync_error = "changed"
    await db_session.flush()
    monkeypatch.setattr(settings, "QUICKBOOKS_ACCOUNTING_ENVIRONMENT", "production")
    lookup = AsyncMock(return_value={"QueryResponse": {}})
    monkeypatch.setattr(accounting, "_request", lookup)
    if defect == "none":
        await pay(db_session, ctx)
        queries = [call.kwargs["params"]["query"] for call in lookup.await_args_list]
        assert any(parent.invoice_number in query for query in queries)
        assert any(parent.invoice_number[:21] in query for query in queries)
        assert parent.quickbooks_synced_at == original_timestamp
    else:
        with pytest.raises(SettlementDomainError): await pay(db_session, ctx)
        lookup.assert_not_awaited()
