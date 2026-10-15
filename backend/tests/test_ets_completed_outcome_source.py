from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import ets_completed_outcome_source as source

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def fixture():
    tenant = uuid4()
    order = SimpleNamespace(id=uuid4(), tenant_id=tenant, source=source.SOURCE, deleted_at=None,
        order_number="ETS-123-456", customer_id=uuid4(), vehicle_id=uuid4(), elis_opportunity_id=None, callrail_call_id=None)
    money = lambda value: {"amount": value, "currency": "USD"}
    evidence = {"source": "easy_truck_shop", "ets_shop_id": "sh_test", "service_id": "123",
        "service_internal_id": "456", "invoice_service_id": "456", "invoice_id": "789", "invoice_number": "100",
        "imported_invoice_uuid": str(uuid4()), "completed": True, "service_status": 60,
        "completed_at_source": "2026-10-15T10:00:00Z", "invoice_status": "10", "currency": "USD",
        "total": money("10.30"), "balance": money("0.00"), "payment_lines_truncated": False,
        "payment_lines": [{"id": "line1", "amount": money("10.30"), "payment": {"id": "pay1",
             "status": "20", "type": "0", "provider": "1", "canceled": False, "credit_total": money("0.00"), "unapplied_amount": money("0.00"),
             "total": money("999.00"), "date_source": "2000-01-01T00:00:00"}}]}
    return dict(tenant_id=tenant, order=order, evidence=[evidence], ets_shop_id="sh_test",
                manifest={"complete": True, "invoice_ids": ["789"], "evidence_kind": "verified_source_service_invoice_manifest"}, observed_at=NOW)


def test_exact_allocations_completion_time_not_payment_time_or_full_payment_total():
    args = fixture()
    result = source.completed_snapshot(**args)
    assert result["invoices"][0]["total"] == "10.30"
    assert result["completed_at"] == "2026-10-15T10:00:00+00:00"
    assert "settled" not in str(result)
    assert "999" not in str(result)
    assert result["source_job_id"] == "ets-service:123"


@pytest.mark.parametrize("field,value", [("completed", None), ("completed", False), ("service_status", 40),
    ("invoice_status", "90"), ("completed_at_source", "2026-10-15"),
    ("completed_at_source", "2026-10-15T10:00:00"), ("completed_at_source", "2026-10-16T10:00:00Z"),
    ("ets_shop_id", "other"), ("invoice_service_id", "other"), ("currency", "EUR"),
    ("payment_lines_truncated", True), ("payment_lines", [])])
def test_source_negative_fields_hold(field, value):
    args = fixture()
    args["evidence"][0][field] = value
    with pytest.raises(source.ETSCompletionHold):
        source.completed_snapshot(**args)


@pytest.mark.parametrize("field,value", [("status", "30"), ("type", "99"), ("provider", None), ("canceled", None), ("canceled", True),
    ("credit_total", {"amount": "1.00", "currency": "USD"}), ("unapplied_amount", None)])
def test_payment_negative_fields_hold(field, value):
    args = fixture()
    args["evidence"][0]["payment_lines"][0]["payment"][field] = value
    with pytest.raises(source.ETSCompletionHold):
        source.completed_snapshot(**args)


@pytest.mark.parametrize("value", [None, {}, {"complete": False}, {"complete": True, "invoice_ids": ["unknown"], "evidence_kind": "verified_source_service_invoice_manifest"}])
def test_missing_or_mismatched_manifest_never_assumes_single_invoice(value):
    args = fixture()
    args["manifest"] = value
    with pytest.raises(source.ETSCompletionHold):
        source.completed_snapshot(**args)


def test_duplicate_allocations_and_partial_amount_hold():
    args = fixture()
    args["evidence"][0]["payment_lines"] *= 2
    with pytest.raises(source.ETSCompletionHold, match="duplicate_allocation"):
        source.completed_snapshot(**args)
    args = fixture()
    args["evidence"][0]["payment_lines"][0]["amount"]["amount"] = "10.29"
    with pytest.raises(source.ETSCompletionHold, match="allocation_total_mismatch"):
        source.completed_snapshot(**args)


def test_shared_payment_only_each_invoice_allocation_counts():
    args = fixture()
    second = deepcopy(args["evidence"][0])
    second.update(invoice_id="790", imported_invoice_uuid=str(uuid4()))
    args["evidence"].append(second)
    args["manifest"]["invoice_ids"].append("790")
    result = source.completed_snapshot(**args)
    assert len(result["invoices"]) == 2
    assert [row["total"] for row in result["invoices"]] == ["10.30", "10.30"]


@pytest.mark.asyncio
@pytest.mark.parametrize("hold", [False, True])
async def test_durable_event_and_same_revision_replay(hold):
    args = fixture()
    order = args.pop("order")
    args["order_id"] = order.id
    if hold:
        args["manifest"] = None
    events = []
    class DB:
        def __init__(self):
            self.scalar = AsyncMock(side_effect=[SimpleNamespace(id=args["tenant_id"]), order, None])
            self.scalars = AsyncMock(side_effect=[[order], [order.id]])
            self.flush = AsyncMock()
        def add(self, event):
            events.append(event)
    db = DB()
    event = await source.persist_completed_observation(db, **args)
    assert event.payload["event_type"] == (source.ETS_HOLD_EVENT if hold else source.ETS_COMPLETED_EVENT)
    assert len(event.idempotency_key) < 255
    assert event.payload["source_observation"] == 1
    db.scalar.side_effect = [SimpleNamespace(id=args["tenant_id"]), order, event]
    db.scalars.side_effect = [[order], [order.id]]
    assert await source.persist_completed_observation(db, **args) is event
    assert len(events) == 1


def test_default_delivery_disabled():
    assert source.configured_shops() == {}


@pytest.mark.asyncio
async def test_transport_is_paused_without_explicit_verified_shop_configuration():
    from app.services.paid_invoice_webhook_service import _deliver_within_budget, ConversionDeliveryPaused
    event = SimpleNamespace(event_type=source.ETS_COMPLETED_EVENT, payload={"snapshot": {"ets_shop_id": "sh_test"}})
    with pytest.raises(ConversionDeliveryPaused):
        await _deliver_within_budget(SimpleNamespace(id=uuid4()), event)


@pytest.mark.asyncio
async def test_later_missing_manifest_emits_hold_in_same_service_stream():
    args = fixture()
    order = args.pop("order")
    args["order_id"] = order.id
    class DB:
        def __init__(self):
            self.scalar = AsyncMock(side_effect=[SimpleNamespace(id=args["tenant_id"]), order, None])
            self.scalars = AsyncMock(side_effect=[[order], [order.id]])
            self.flush = AsyncMock()
        def add(self, event):
            pass
    db = DB()
    complete = await source.persist_completed_observation(db, **args)
    args["manifest"] = None
    db.scalar.side_effect = [SimpleNamespace(id=args["tenant_id"]), order, complete]
    db.scalars.side_effect = [[order], [order.id]]
    hold = await source.persist_completed_observation(db, **args)
    assert hold.event_type == source.ETS_HOLD_EVENT
    assert hold.payload["source_observation"] == 2
    assert hold.payload["snapshot"]["hold_reason"] == "invoice_manifest_incomplete"
    assert hold.idempotency_key.split(":")[:2] == complete.idempotency_key.split(":")[:2]


@pytest.mark.asyncio
async def test_stream_orders_by_sequence_and_hold_uses_diagnostic_time():
    args = fixture()
    order = args.pop("order")
    args["order_id"] = order.id
    args["manifest"] = None
    # Simulate a prior positive with the same source timestamp as a later hold.
    prior = SimpleNamespace(payload={"snapshot": {"repair_order_uuid": str(order.id)},
        "source_observation": 7, "source_revision": "old", "observed_at": args["observed_at"].isoformat()})
    queries = []
    results = iter([SimpleNamespace(id=args["tenant_id"]), order, prior])
    class DB:
        async def scalar(self, query):
            queries.append(query)
            return next(results)
        scalars = AsyncMock(side_effect=[[order], [order.id]])
        flush = AsyncMock()
        def add(self, event):
            pass
    event = await source.persist_completed_observation(DB(), **args)
    assert event.payload["source_observation"] == 8
    assert event.payload["observed_at"] == event.created_at.isoformat()
    from sqlalchemy.dialects import postgresql
    sql = str(queries[-1].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "source_observation" in sql.split("ORDER BY")[1]
    assert "created_at" not in sql.split("ORDER BY")[1]


@pytest.mark.asyncio
async def test_late_old_positive_cannot_reverse_a_newer_hold():
    args = fixture()
    order = args.pop("order")
    args["order_id"] = order.id
    prior = SimpleNamespace(payload={"snapshot": {"repair_order_uuid": str(order.id)},
        "source_observation": 8, "source_revision": "held", "observed_at": "2026-10-15T13:00:00+00:00"})
    db = SimpleNamespace(scalar=AsyncMock(side_effect=[SimpleNamespace(id=args["tenant_id"]), order, prior]),
                         scalars=AsyncMock(side_effect=[[order], [order.id]]), add=AsyncMock())
    assert await source.persist_completed_observation(db, **args) is prior
    db.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["deleted_sibling", "split_root", "changed_root_alias"])
async def test_known_grouping_conflict_immediately_invalidates_original_identity(conflict):
    args = fixture()
    order = args.pop("order")
    args["order_id"] = order.id
    positive_snapshot = source.completed_snapshot(order=order, **{k:v for k,v in args.items() if k != "order_id"})
    original_id = uuid4() if conflict == "changed_root_alias" else order.id
    positive_snapshot["repair_order_uuid"] = str(original_id)
    prior = SimpleNamespace(payload={"snapshot": positive_snapshot, "source_observation": 4,
        "source_revision": "old", "observed_at": args["observed_at"].isoformat()})
    siblings = [order]
    if conflict == "deleted_sibling":
        sibling = deepcopy(order)
        sibling.id, sibling.deleted_at = uuid4(), NOW
        siblings.append(sibling)
    roots = [order.id, uuid4()] if conflict == "split_root" else [order.id]
    db = SimpleNamespace(scalar=AsyncMock(side_effect=[SimpleNamespace(id=args["tenant_id"]), order, prior]),
                         scalars=AsyncMock(side_effect=[siblings, roots]), add=lambda _: None, flush=AsyncMock())
    event = await source.persist_completed_observation(db, **args)
    assert event.event_type == source.ETS_HOLD_EVENT
    assert event.payload["source_observation"] == 5
    assert event.payload["snapshot"]["hold_reason"] == "source_identity_conflict"
    assert event.aggregate_id == original_id
    assert event.payload["snapshot"]["repair_order_uuid"] == str(original_id)


def legacy_fixture():
    from decimal import Decimal
    args = fixture()
    order = args['order']
    snapshot = source.completed_snapshot(**args)
    canonical = SimpleNamespace(id=args['evidence'][0]['imported_invoice_uuid'],
        repair_order_id=order.id, tenant_id=order.tenant_id, source=source.SOURCE,
        invoice_number='ETSINV-100', status='paid', deleted_at=None,
        total_amount=Decimal('10.30'), billed_customer_id=order.customer_id)
    sibling = deepcopy(order)
    sibling.id = uuid4()
    sibling.order_number += '-2'
    duplicate = deepcopy(canonical)
    duplicate.id = uuid4()
    duplicate.repair_order_id = sibling.id
    duplicate.invoice_number += '-' + sibling.order_number
    duplicate.status = 'cancelled'
    return args, snapshot, canonical, sibling, duplicate


@pytest.mark.asyncio
@pytest.mark.parametrize("soft_deleted", [False, True])
async def test_verified_cancelled_operation_copy_does_not_duplicate_revenue(soft_deleted):
    args, snapshot, canonical, sibling, duplicate = legacy_fixture()
    order = args.pop('order')
    if soft_deleted:
        duplicate.deleted_at = NOW
    db = SimpleNamespace(scalar=AsyncMock(side_effect=[SimpleNamespace(id=order.tenant_id), order, None]),
        scalars=AsyncMock(side_effect=[[order, sibling], [order.id, sibling.id], [canonical, duplicate]]),
        add=Mock(), flush=AsyncMock())
    before = deepcopy(vars(duplicate))
    event = await source.persist_completed_observation(db, order_id=order.id, **args)
    assert event.event_type == source.ETS_COMPLETED_EVENT
    assert event.payload['snapshot'] == snapshot
    assert len(event.payload['snapshot']['invoices']) == 1
    assert vars(duplicate) == before
    db.scalar.side_effect = [SimpleNamespace(id=order.tenant_id), order, event]
    db.scalars.side_effect = [[order, sibling], [order.id, sibling.id], [canonical, duplicate]]
    assert await source.persist_completed_observation(db, order_id=order.id, **args) is event
    assert db.flush.await_count == 1
    assert db.add.call_count == 1


@pytest.mark.parametrize('target,field,value', [
    ('duplicate', 'status', 'paid'), ('duplicate', 'status', None),
    ('duplicate', 'invoice_number', 'ETSINV-100-unknown'),
    ('duplicate', 'total_amount', 99), ('canonical', 'deleted_at', NOW),
    ('duplicate', 'tenant_id', uuid4()), ('duplicate', 'billed_customer_id', uuid4()),
    ('duplicate', 'source', 'native'), ('sibling', 'customer_id', uuid4()),
    ('sibling', 'vehicle_id', uuid4()), ('sibling', 'tenant_id', uuid4()),
    ('sibling', 'deleted_at', NOW), ('sibling', 'order_number', 'ETS-999-456-2'),
    ('canonical', 'status', 'cancelled'), ('canonical', 'id', uuid4()),
    ('canonical', 'invoice_number', 'ETSINV-other'), ('canonical', 'total_amount', 99),
])
def test_unverified_cancelled_roots_remain_conflicts(target, field, value):
    args, snapshot, canonical, sibling, duplicate = legacy_fixture()
    setattr({'duplicate': duplicate, 'sibling': sibling, 'canonical': canonical}[target], field, value)
    roots = source._verified_legacy_duplicate_roots(order=args['order'],
        siblings=[args['order'], sibling], invoices=[canonical, duplicate], snapshot=snapshot)
    assert duplicate.repair_order_id in roots


@pytest.mark.parametrize('manifest', [None, {'complete': False}])
def test_duplicate_exemption_requires_verified_positive_snapshot(manifest):
    args, snapshot, canonical, sibling, duplicate = legacy_fixture()
    snapshot['invoice_manifest'] = manifest or {}
    assert source._verified_legacy_duplicate_roots(order=args['order'], siblings=[args['order'], sibling],
        invoices=[canonical, duplicate], snapshot=snapshot) == {canonical.repair_order_id, duplicate.repair_order_id}


@pytest.mark.asyncio
async def test_active_extra_operation_invoice_still_holds():
    args, _, canonical, sibling, duplicate = legacy_fixture()
    order = args.pop('order')
    duplicate.status = 'paid'
    db = SimpleNamespace(scalar=AsyncMock(side_effect=[SimpleNamespace(id=order.tenant_id), order, None]),
        scalars=AsyncMock(side_effect=[[order, sibling], [order.id, sibling.id], [canonical, duplicate]]),
        add=AsyncMock(), flush=AsyncMock())
    with pytest.raises(source.ETSCompletionHold, match='canonical_source_root_conflict'):
        await source.persist_completed_observation(db, order_id=order.id, **args)
    db.add.assert_not_called()


def test_multiple_source_invoices_cannot_exempt_legacy_roots():
    args, snapshot, canonical, sibling, duplicate = legacy_fixture()
    snapshot['invoices'].append(deepcopy(snapshot['invoices'][0]))
    assert source._verified_legacy_duplicate_roots(order=args['order'], siblings=[args['order'], sibling],
        invoices=[canonical, duplicate], snapshot=snapshot) == {canonical.repair_order_id, duplicate.repair_order_id}


@pytest.mark.parametrize('field,value', [('status', 'paid'), ('status', None),
    ('invoice_number', 'unrecognized-copy'), ('total_amount', 99)])
def test_deleted_unverified_invoice_still_conflicts(field, value):
    args, snapshot, canonical, sibling, duplicate = legacy_fixture()
    duplicate.deleted_at = NOW
    setattr(duplicate, field, value)
    assert duplicate.repair_order_id in source._verified_legacy_duplicate_roots(
        order=args['order'], siblings=[args['order'], sibling],
        invoices=[canonical, duplicate], snapshot=snapshot)
