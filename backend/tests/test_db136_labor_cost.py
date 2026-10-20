"""A1 synthetic calculations and strict metadata contracts; no production rates."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import json

import pytest
from pydantic import ValidationError
from fastapi import HTTPException
from app.schemas.labor_cost import RateRequest, ReviewRequest
from app.services.labor_cost.calculation import derive, labor_projection, discount_allocation, stamp
from app.services.labor_cost.policy import authorize, cursor_encode, cursor_decode
from app.services.labor_cost.report import summary
from app.db.models.user import UserRole

ACTIVATION = datetime(2026, 10, 20, 4, tzinfo=timezone.utc)


def fixture(hours=3):
    tenant, owner, mechanic, order, customer, labor, inventory, part, invoice, session = [str(uuid4()) for _ in range(10)]
    start = ACTIVATION + timedelta(hours=5)
    end = start + timedelta(hours=hours)
    source = {
        "order": {"id": order, "tenant_id": tenant, "customer_id": customer, "order_number": "SYNTHETIC-A1",
                  "status": "invoiced", "source": None, "created_at": start, "work_completed_at": end},
        "customer": {"id": customer, "company_name": "Synthetic fixture", "deleted_at": None},
        "invoices": [{"id": invoice, "tenant_id": tenant, "repair_order_id": order, "billed_customer_id": customer,
            "status": "sent", "subtotal": "500.00", "discount_amount": "0.00", "tax_amount": "0.00",
            "service_fee_amount": "0.00", "shop_supplies_amount": "0.00", "total_amount": "500.00",
            "line_items_snapshot": {"version": 1, "labor": [{"description": "Synthetic operation", "hours": "3.00", "hourly_rate": "116.67", "total_cost": "350.00"}],
                "parts": [{"name": "Synthetic part", "quantity": "1.00", "unit_price": "150.00", "total_price": "150.00"}]}}],
        "labor": [{"id": labor, "tenant_id": tenant, "repair_order_id": order, "description": "Synthetic operation",
                   "hours": "3.00", "hourly_rate": "116.67", "total_cost": "350.00", "line_type": "manual"}],
        "parts": [{"id": part, "tenant_id": tenant, "repair_order_id": order, "inventory_id": inventory,
                   "quantity": "1.00", "unit_price": "150.00", "total_price": "150.00", "unit_cost": "150.00"}],
        "inventory": [{"id": inventory, "sku": "SYN", "name": "Synthetic part"}],
        "sessions": [{"id": session, "tenant_id": tenant, "repair_order_id": order, "mechanic_id": mechanic,
                      "session_type": "repair_order", "started_at": start, "ended_at": end, "stop_reason": "manual"}],
        "mechanics": [{"id": mechanic, "role": "mechanic", "first_name": "Synthetic", "last_name": "Technician"}],
        "attendance": [{"id": str(uuid4()), "mechanic_id": mechanic, "started_at": start, "ended_at": end}],
        "breaks": [], "time_audits": [], "attendance_audits": [], "policies": [], "adjustments": [], "payments": [],
        "credits": [], "overpayments": [], "refunds": [], "disputes": [], "returns": [], "review": None,
        "source_fingerprint": "a" * 64, "policy_heads_digest": "b" * 64,
        "policy_heads": {mechanic: {"id": str(uuid4()), "policy": {"activation_at": stamp(ACTIVATION), "segments": [
            {"effective_from": stamp(ACTIVATION), "effective_to": None, "hourly_cost": "40.0000", "inclusions": "Synthetic loaded direct cost"}]}}}}
    return source


def review(source, **overrides):
    return {"id": str(uuid4()), "version": 1, "source_fingerprint": source["source_fingerprint"],
            "policy_heads_digest": source["policy_heads_digest"], "calculation_version": "db136-v1",
            "business_classification": "real", "time_capture": "complete", "reviewed_exception_ids": [], **overrides}


@pytest.mark.parametrize("hours,contribution,margin", [(3, "230.00", "46.00"), (5, "150.00", "30.00")])
def test_exact_direct_contribution_not_billed_hours(hours, contribution, margin):
    source = fixture(hours)
    source["review"] = review(source)
    row, sessions, allocation, separate = derive(source, ACTIVATION)
    assert row["direct_contribution"] == contribution and row["margin_pct"] == margin
    assert row["revenue"]["net_direct_revenue"] == "500.00"
    assert row["parts"]["known_cost"] == "150.00"
    assert row["labor"]["known_cost"] == str(Decimal(hours * 40).quantize(Decimal(".01")))
    assert row["labor"]["recorded_seconds"] == row["labor"]["costed_seconds"] == hours * 3600
    assert row["cost_status"] == "complete" and not row["hold_reasons"]
    assert separate["cost_status"] == "unavailable"


def test_missing_rate_unknown_scope_no_timers_and_stale_review_are_never_zero_profit():
    source = fixture()
    row = derive(source, ACTIVATION)[0]
    assert row["business_classification"] == "unknown" and row["direct_contribution"] is None
    assert summary([row])["reviewed_complete_contribution"] is None
    source["review"] = review(source)
    source["policy_heads"] = {}
    row = derive(source, ACTIVATION)[0]
    assert row["labor"]["known_cost"] is None and row["labor"]["unrated_seconds"] == 10800
    assert row["direct_contribution"] is None
    source["sessions"] = []
    row = derive(source, ACTIVATION)[0]
    assert row["labor"]["status"] == "unavailable" and row["direct_contribution"] is None
    source["source_fingerprint"] = "c" * 64
    row = derive(source, ACTIVATION)[0]
    assert row["review_status"] == "stale" and row["business_classification"] == "unknown"


def test_rate_boundary_gap_and_pre_activation_decimal_precision():
    source = fixture(4)
    session = source["sessions"][0]
    session["started_at"] = ACTIVATION - timedelta(hours=1)
    session["ended_at"] = ACTIVATION + timedelta(hours=3)
    source["attendance"][0].update(started_at=session["started_at"], ended_at=session["ended_at"])
    policy = next(iter(source["policy_heads"].values()))["policy"]
    policy["segments"] = [
        {"effective_from": stamp(ACTIVATION), "effective_to": stamp(ACTIVATION + timedelta(hours=1)), "hourly_cost": "40.0001"},
        {"effective_from": stamp(ACTIVATION + timedelta(hours=2)), "effective_to": None, "hourly_cost": "50.0001"}]
    labor, _ = labor_projection(source, ACTIVATION, review(source))
    assert labor["known_cost"] == "90.00"
    assert labor["recorded_seconds"] == 14400
    assert labor["costed_seconds"] == 7200 and labor["pre_activation_seconds"] == labor["unrated_seconds"] == 3600
    assert sum(labor[key] for key in ("costed_seconds", "unrated_seconds", "pre_activation_seconds", "held_seconds")) == labor["recorded_seconds"]


def test_malformed_stored_policy_does_not_double_count_pre_activation_exception():
    source = fixture(2)
    session = source["sessions"][0]
    session["started_at"], session["ended_at"] = ACTIVATION - timedelta(hours=1), ACTIVATION + timedelta(hours=1)
    source["attendance"][0].update(started_at=session["started_at"], ended_at=session["ended_at"])
    next(iter(source["policy_heads"].values()))["policy"]["segments"][0]["hourly_cost"] = "NaN"
    labor, _ = labor_projection(source, ACTIVATION, review(source))
    assert labor["recorded_seconds"] == 7200 and labor["held_seconds"] == 3600
    assert labor["pre_activation_seconds"] == 3600 and labor["costed_seconds"] == labor["unrated_seconds"] == 0
    assert labor["known_cost"] is None


@pytest.mark.parametrize("kind", ["ro", "misc", "open", "deleted", "break", "attendance", "foreign-operation"])
def test_nonwaivable_time_conflicts_hold_whole_session(kind):
    source = fixture()
    own = source["sessions"][0]
    if kind in {"ro", "misc", "open", "deleted"}:
        peer = {**own, "id": str(uuid4()), "repair_order_id": str(uuid4())}
        if kind == "misc":
            peer["session_type"] = "misc"
        if kind == "open":
            peer["ended_at"] = None
        if kind == "deleted":
            peer["deleted_at"] = own["started_at"]
        source["sessions"].append(peer)
    elif kind == "break":
        source["breaks"].append({**own, "id": str(uuid4())})
    elif kind == "attendance":
        source["attendance"][0]["ended_at"] -= timedelta(seconds=1)
    else:
        own["labor_id_snapshot"] = str(uuid4())
    labor, _ = labor_projection(source, ACTIVATION, review(source, reviewed_exception_ids=[own["id"]]))
    assert labor["held_seconds"] == labor["recorded_seconds"] == 10800
    assert labor["known_cost"] is None and labor["costed_seconds"] == 0


def test_correction_acknowledgment_does_not_waive_active_overlap():
    source = fixture()
    own = source["sessions"][0]
    own["stop_reason"] = "auto_midnight"
    source["time_audits"] = [{"id": str(uuid4()), "session_id": own["id"], "action": "edit"}]
    assert labor_projection(source, ACTIVATION, review(source))[0]["held_seconds"] == 10800
    assert labor_projection(source, ACTIVATION, review(source, reviewed_exception_ids=[own["id"]]))[0]["known_cost"] == "120.00"
    source["sessions"].append({**own, "id": str(uuid4()), "repair_order_id": str(uuid4())})
    assert labor_projection(source, ACTIVATION, review(source, reviewed_exception_ids=[own["id"]]))[0]["known_cost"] is None


def test_attendance_edit_is_scoped_acknowledgeable_and_old_unrelated_audit_is_not_a_hold():
    source = fixture()
    own = source["sessions"][0]
    audit = {"id": str(uuid4()), "mechanic_id": own["mechanic_id"], "attendance_session_id": source["attendance"][0]["id"],
             "action": "edit", "before_snapshot": {"started_at": stamp(own["started_at"]), "ended_at": stamp(own["ended_at"])},
             "after_snapshot": {"started_at": stamp(own["started_at"]), "ended_at": stamp(own["ended_at"])}}
    source["attendance_audits"] = [audit]
    assert labor_projection(source, ACTIVATION, review(source))[0]["known_cost"] is None
    assert labor_projection(source, ACTIVATION, review(source, reviewed_exception_ids=[own["id"]]))[0]["known_cost"] == "120.00"
    source["attendance_audits"] = [{**audit, "attendance_session_id": str(uuid4()),
        "before_snapshot": {"started_at": stamp(ACTIVATION - timedelta(days=10)), "ended_at": stamp(ACTIVATION - timedelta(days=9))},
        "after_snapshot": {"started_at": stamp(ACTIVATION - timedelta(days=10)), "ended_at": stamp(ACTIVATION - timedelta(days=9))}}]
    assert labor_projection(source, ACTIVATION, review(source))[0]["known_cost"] == "120.00"


def test_refunded_overpayment_without_refund_children_is_unresolved_economics():
    source = fixture()
    source["review"] = review(source)
    source["overpayments"] = [{"invoice_id": source["invoices"][0]["id"], "state": "refunded"}]
    row = derive(source, ACTIVATION)[0]
    assert row["direct_contribution"] is None
    assert "overpayment_review_required" in row["revenue"]["hold_reasons"]


def test_separate_time_is_clipped_to_selected_window_not_attendance_day():
    source = fixture()
    source["review"] = review(source)
    own = source["sessions"][0]
    source["attendance"][0].update(started_at=own["started_at"] - timedelta(hours=1), ended_at=own["ended_at"] + timedelta(hours=5))
    # Unrelated afternoon work is deliberately absent from bounded source;
    # attendance beyond the selected09–12 window cannot become claimed idle.
    separate = derive(source, ACTIVATION)[3]
    assert separate["scope"] == "selected_job_timer_window"
    assert separate["idle_seconds"] == 0
    assert separate["scope_windows"][0]["started_at"] == stamp(own["started_at"])
    assert separate["scope_windows"][0]["ended_at"] == stamp(own["ended_at"])


def test_bundle_keeps_gap_occupancy_for_whole_declared_window_and_ignores_outside_evidence():
    from app.services.labor_cost.source import bundle_for
    source = fixture()
    first = source["sessions"][0]
    first["ended_at"] = first["started_at"] + timedelta(hours=1)
    second = {**first, "id": str(uuid4()), "started_at": first["started_at"] + timedelta(hours=3),
              "ended_at": first["started_at"] + timedelta(hours=4)}
    peer = {**first, "id": str(uuid4()), "repair_order_id": str(uuid4()),
            "started_at": first["ended_at"], "ended_at": second["started_at"]}
    outside = {**first, "id": str(uuid4()), "repair_order_id": str(uuid4()),
               "started_at": second["ended_at"] + timedelta(hours=1), "ended_at": second["ended_at"] + timedelta(hours=3)}
    source["sessions"] = [first, second, peer, outside]
    source["attendance"][0].update(started_at=first["started_at"], ended_at=second["ended_at"])
    mechanic_id = first["mechanic_id"]
    policy = source["policy_heads"][mechanic_id]
    policy["policy"]["shop_timezone"] = "America/New_York"
    data = {**source, "shop_timezone": "America/New_York", "customers": [source["customer"]], "reviews": [],
            "policies": [{**policy, "mechanic_id": mechanic_id, "version": 1}], "attempts": [], "return_lines": []}
    bundle = bundle_for(data, source["order"])
    assert {row["id"] for row in bundle["sessions"]} == {first["id"], second["id"], peer["id"]}
    assert outside["id"] not in {row["id"] for row in bundle["sessions"]}
    bundle["review"] = review(bundle)
    row, _, _, separate = derive(bundle, ACTIVATION)
    assert row["labor"]["known_cost"] == "80.00"
    assert separate["idle_seconds"] == 0 and separate["time_status"] == "complete"
    assert separate["scope_windows"] == [{"mechanic_id": mechanic_id, "started_at": stamp(first["started_at"]), "ended_at": stamp(second["ended_at"])}]
    original_fingerprint = bundle["source_fingerprint"]
    outside["ended_at"] += timedelta(hours=1)
    assert bundle_for(data, source["order"])["source_fingerprint"] == original_fingerprint
    peer["ended_at"] -= timedelta(minutes=30)
    changed = bundle_for(data, source["order"])
    assert changed["source_fingerprint"] != original_fingerprint
    assert derive(changed, ACTIVATION)[3]["idle_seconds"] == 1800


@pytest.mark.asyncio
async def test_imported_order_cannot_create_even_incomplete_review_metadata(monkeypatch):
    from app.services.labor_cost import report as service
    source = fixture()
    source["order"]["source"] = "easy_truck_shop_import"
    async def context(*args, **kwargs):
        return SimpleNamespace(id=uuid4()), None, ACTIVATION
    async def detail(*args, **kwargs):
        return source, ACTIVATION
    monkeypatch.setattr(service, "context", context)
    monkeypatch.setattr(service, "detail", detail)
    class NoMetadata:
        def add(self, *args):
            raise AssertionError("Imported metadata insert forbidden")
        async def execute(self, *args):
            raise AssertionError("Imported metadata replay/insert lookup forbidden")
    body = ReviewRequest.model_validate({"expected_version": 0, "source_fingerprint": "a" * 64, "policy_heads_digest": "b" * 64,
        "business_classification": "real", "time_capture": "incomplete", "reviewed_exception_ids": [], "reason": "Synthetic historical review"})
    with pytest.raises(HTTPException) as error:
        await service.append_review(NoMetadata(), SimpleNamespace(id=uuid4()), uuid4(), body, uuid4())
    assert error.value.status_code == 422


def test_discount_is_issued_net_once_and_cent_allocation_deterministic():
    source = fixture()
    source["review"] = review(source)
    invoice = source["invoices"][0]
    invoice["subtotal"] = invoice["total_amount"] = "450.00"
    source["order"]["discount_amount"] = "50.00"
    row, _, allocations, _ = derive(source, ACTIVATION)
    assert row["direct_contribution"] == "180.00" and row["revenue"]["issued_discount"] == "50.00"
    assert sum(Decimal(item["net"]) for item in allocations) == Decimal("450.00")
    tied = discount_allocation([("parts", 0, Decimal(".01")), ("labor", 0, Decimal(".01"))], Decimal(".01"))
    assert next(row for row in tied if row["kind"] == "labor")["allocated_discount"] == "0.01"


@pytest.mark.parametrize("kind", ["parts-missing", "parts-zero", "changed-line", "duplicate", "refund", "credit", "hold", "ets", "snapshot-negative", "draft", "superseded"])
def test_expense_and_revenue_holds_never_fabricate_final_margin(kind):
    source = fixture()
    source["review"] = review(source)
    if kind == "parts-zero":
        source["parts"][0]["unit_cost"] = "0.00"
        assert derive(source, ACTIVATION)[0]["direct_contribution"] == "380.00"
        return
    if kind == "parts-missing":
        source["parts"][0]["unit_cost"] = None
    elif kind == "changed-line":
        source["parts"][0]["quantity"] = "2.00"
    elif kind == "duplicate":
        source["labor"].append({**source["labor"][0], "id": str(uuid4())})
    elif kind == "refund":
        source["refunds"] = [{"state": "succeeded"}]
    elif kind == "credit":
        source["credit_ambiguity"] = True
    elif kind == "hold":
        source["invoices"][0]["accounting_policy"] = "historical_export_hold"
    elif kind == "ets":
        source["order"]["source"] = "easy_truck_shop_import"
    elif kind == "snapshot-negative":
        source["invoices"][0]["line_items_snapshot"]["labor"][0]["total_cost"] = "-1.00"
    elif kind == "draft":
        source["invoices"][0]["status"] = "draft"
    elif kind == "superseded":
        source["invoices"][0]["supersedes_invoice_id"] = str(uuid4())
    row = derive(source, ACTIVATION)[0]
    assert row["direct_contribution"] is None and row["margin_pct"] is None


def test_real_test_unknown_and_history_summary_does_not_include_excluded_money():
    source = fixture()
    rows = []
    for classification in ("real", "test", "unknown"):
        source["review"] = review(source, business_classification=classification)
        rows.append(derive(source, ACTIVATION)[0])
    source["order"]["source"] = "easy_truck_shop_import"
    rows.append(derive(source, ACTIVATION)[0])
    totals = summary(rows)
    assert totals["order_count"] == 4 and totals["real_count"] == totals["test_count"] == totals["unknown_count"] == totals["history_count"] == 1
    assert totals["reviewed_complete_contribution"] == "230.00" and totals["known_recorded_direct_cost"] == "120.00"


def valid_rate():
    return {"expected_version": 0, "policy_version": 1, "currency": "USD", "basis": "owner_declared_loaded_direct",
            "segments": [{"effective_from": stamp(ACTIVATION), "effective_to": None, "hourly_cost": "40.0000", "inclusions": "Synthetic"}], "reason": "Synthetic initial policy"}


@pytest.mark.parametrize("value", ["0", 40, 40.0, True, "1e2", "NaN", "10000.0001", "0.00001", "-1"])
def test_loaded_rate_rejects_nonliteral_or_invalid_values(value):
    body = valid_rate()
    body["segments"][0]["hourly_cost"] = value
    with pytest.raises(ValidationError):
        RateRequest.model_validate(body)


@pytest.mark.parametrize("role", [role for role in UserRole if role != UserRole.GARAGE_OWNER])
def test_only_owner_has_cost_authority(role):
    with pytest.raises(HTTPException) as error:
        authorize(SimpleNamespace(role=role, tenant_id=uuid4(), is_active=True, deleted_at=None))
    assert error.value.status_code == 403


def test_signed_cursors_cannot_cross_tenant_filter_or_tamper():
    scope = {"tenant": str(uuid4()), "from": "2026-10-20", "scope": "real", "q": ""}
    token = cursor_encode(scope, ["2026-10-20T17:00:00Z", str(uuid4())])
    assert len(cursor_decode(token, scope)) == 2
    for other in ({**scope, "tenant": str(uuid4())}, {**scope, "scope": "test"}):
        with pytest.raises(HTTPException):
            cursor_decode(token, other)
    with pytest.raises(HTTPException):
        cursor_decode(token + "x", scope)


@pytest.mark.asyncio
async def test_every_cost_route_denies_admin_and_platform_without_source_reads(client, monkeypatch):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    from app.api.v1.endpoints import labor_cost
    actor = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), role=UserRole.GARAGE_ADMIN, is_active=True, deleted_at=None)
    async def user():
        return actor
    def forbidden_session(*args, **kwargs):
        raise AssertionError("denied role must not open cost source transaction")
    monkeypatch.setattr(labor_cost, "AsyncSessionLocal", forbidden_session)
    app.dependency_overrides[get_current_active_user] = user
    try:
        identity = str(uuid4())
        paths = [("get", "/technician-costs"), ("get", f"/technician-costs/{identity}"),
                 ("post", f"/technician-costs/{identity}"), ("get", "/job-contribution"),
                 ("get", f"/job-contribution/{identity}"), ("post", f"/job-contribution/{identity}/review"),
                 ("get", "/technician-costs/time-boundaries?local=2026-10-20T09:00")]
        for role in (UserRole.GARAGE_ADMIN, UserRole.MECHANIC, UserRole.RECEPTIONIST, UserRole.SUPER_ADMIN):
            actor.role = role
            for method, path in paths:
                response = await getattr(client, method)(f"/api/v1/reports{path}")
                assert response.status_code == 403
                assert {part.strip() for part in response.headers["cache-control"].split(",")} == {"private", "no-store"}
                assert "cost" not in response.json().get("policy", {})
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.asyncio
async def test_duplicate_json_and_unknown_monetary_outcomes_rejected_without_echo():
    from starlette.requests import Request
    from app.api.v1.endpoints.labor_cost import body_value
    for body in (b'{"expected_version":0,"expected_version":0}',
                 json.dumps({**valid_rate(), "direct_contribution": "999.99"}).encode(),
                 json.dumps({**valid_rate(), "expected_version": True}).encode()):
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        with pytest.raises(HTTPException) as error:
            await body_value(Request({"type": "http"}, receive), RateRequest)
        assert error.value.status_code == 422
        assert "999" not in error.value.detail


@pytest.mark.asyncio
async def test_source_limit_plus_one_raises_instead_of_truncation():
    from app.services.labor_cost.source import read
    from app.db.models.user import User
    class TooMany:
        def mappings(self):
            return [{"id": uuid4(), "tenant_id": uuid4()} for _ in range(3)]
    class FakeDB:
        async def execute(self, query):
            assert query._limit_clause.value == 3
            return TooMany()
    with pytest.raises(HTTPException) as error:
        await read(FakeDB(), User, "id tenant_id", uuid4(), cap=2)
    assert error.value.status_code == 413
