"""DB-100: current line expense evidence never becomes invented job profit."""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.api.v1.endpoints.reports import (
    _component_contribution,
    AccountRow,
    ScatterPoint,
    get_analytics_accounts,
    get_analytics_profitability,
)
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.labor import Labor, LaborLineType
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle

DAY = date(2026, 10, 12)
NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("lines,status,cost,contribution,margin,missing", [
    ([("200", "120")], "complete", "120.00", "80.00", "40.00", 0),
    ([("200", "0")], "complete", "0.00", "200.00", "100.00", 0),
    ([("100", "120")], "complete", "120.00", "-20.00", "-20.00", 0),
    ([("0", "20")], "complete", "20.00", "-20.00", None, 0),
    ([("-10", "20")], "complete", "20.00", "-30.00", None, 0),
    ([("100", None)], "unavailable", "0.00", None, None, 1),
    ([("100", "0"), ("100", None)], "partial", "0.00", None, None, 1),
    ([("100", "60"), ("100", None)], "partial", "60.00", None, None, 1),
    ([("300", "220")], "complete", "220.00", "80.00", "26.67", 0),
    ([("0.10", "0.0165"), ("0.10", "0.0165")], "complete", "0.03", "0.17", "83.50", 0),
    ([], "not_applicable", "0.00", None, None, 0),
])
def test_component_calculations_preserve_missing_zero_loss_and_precision(
    lines, status, cost, contribution, margin, missing,
):
    result = _component_contribution([
        (Decimal(revenue), Decimal(expense) if expense is not None else None)
        for revenue, expense in lines
    ])
    assert result.status == status
    assert result.known_cost == cost
    assert result.contribution == contribution
    assert result.margin_pct == margin
    assert result.missing_cost_line_count == missing
    assert result.line_count == len(lines)


@pytest.mark.parametrize("schema", [ScatterPoint, AccountRow])
def test_legacy_margin_schema_explicitly_accepts_null(schema):
    assert {option["type"] for option in schema.model_json_schema()["properties"]["marginPct"]["anyOf"]} == {"number", "null"}


@pytest_asyncio.fixture
async def shop(db_session):
    suffix = uuid4().hex
    tenant = Tenant(name="Cost evidence", slug=f"cost-{suffix}", timezone="UTC")
    foreign = Tenant(name="Other shop", slug=f"other-{suffix}", timezone="UTC")
    db_session.add_all([tenant, foreign])
    await db_session.flush()
    owner = User(tenant_id=tenant.id, email=f"owner-{suffix}@example.com", hashed_password="test",
                 first_name="Cost", last_name="Owner", role=UserRole.GARAGE_OWNER,
                 is_active=True, is_verified=True)
    customer = Customer(tenant_id=tenant.id, first_name="Cost", last_name="Customer",
                        company_name="Cost account", email=f"customer-{suffix}@example.com")
    foreign_customer = Customer(tenant_id=foreign.id, first_name="FOREIGN", last_name="LABEL",
                                email=f"foreign-{suffix}@example.com")
    db_session.add_all([owner, customer, foreign_customer])
    await db_session.flush()
    vehicle = Vehicle(tenant_id=tenant.id, customer_id=customer.id, make="Volvo", model="VNL", year=2024)
    inventory = Inventory(tenant_id=tenant.id, sku=suffix, name="Snapshot source",
                          cost=Decimal("999.00"), selling_price=Decimal("200.00"))
    db_session.add_all([vehicle, inventory])
    await db_session.flush()

    async def order(**overrides):
        values = dict(tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
                      order_number=f"RO-{uuid4().hex[:12]}", total_cost=Decimal("300.00"),
                      total_labor_cost=Decimal("100.00"), total_parts_cost=Decimal("200.00"),
                      created_at=NOW)
        values.update(overrides)
        row = RepairOrder(**values)
        db_session.add(row)
        await db_session.flush()
        return row

    def part(ro, revenue="200", cost="120", quantity="1", **overrides):
        values = dict(tenant_id=tenant.id, repair_order_id=ro.id, inventory_id=inventory.id,
                      quantity=Decimal(quantity), unit_price=Decimal(revenue), total_price=Decimal(revenue),
                      unit_cost=Decimal(cost) if cost is not None else None)
        values.update(overrides)
        row = PartsUsage(**values)
        db_session.add(row)
        return row

    def labor(ro, revenue="100", cost=None, hours="1", line_type=LaborLineType.MANUAL, **overrides):
        values = dict(tenant_id=tenant.id, repair_order_id=ro.id, description="Recorded line",
                      hours=Decimal(hours), hourly_rate=Decimal("100"), total_cost=Decimal(revenue),
                      vendor_cost=Decimal(cost) if cost is not None else None, line_type=line_type)
        values.update(overrides)
        row = Labor(**values)
        db_session.add(row)
        return row

    def invoice(ro, **overrides):
        values = dict(tenant_id=tenant.id, repair_order_id=ro.id, invoice_number=f"INV-{uuid4().hex[:12]}",
                      status=InvoiceStatus.PAID, is_internal=False, subtotal=Decimal("300"),
                      total_amount=Decimal("300"), paid_at=NOW)
        values.update(overrides)
        row = Invoice(**values)
        db_session.add(row)
        return row

    async def report(endpoint=get_analytics_profitability):
        await db_session.flush()
        return await endpoint(range="custom", from_date=DAY, to_date=DAY, db=db_session, current_user=owner)

    return SimpleNamespace(tenant=tenant, foreign=foreign, owner=owner, customer=customer,
                           foreign_customer=foreign_customer, order=order, part=part, labor=labor,
                           invoice=invoice, report=report)


@pytest.mark.asyncio
async def test_original_retail_as_cost_bug_is_corrected_without_inventing_wages(shop):
    order = await shop.order()
    shop.part(order)
    shop.labor(order)
    shop.invoice(order)
    response = await shop.report()
    assert response.cost_basis == "current_lines_before_order_discounts"
    assert response.labor_cost_status == "unavailable"
    row, = response.ros
    assert row.repair_order_id == str(order.id)
    assert row.order_number == order.order_number
    assert row.subtotal == 300
    assert row.hours == 1
    assert row.marginPct is None  # Previously 0% despite having no wage evidence.
    assert row.parts_contribution.model_dump() == {
        "revenue": "200.00", "known_cost": "120.00", "line_count": 1,
        "missing_cost_line_count": 0, "status": "complete", "contribution": "80.00", "margin_pct": "40.00",
    }
    assert row.sublet_contribution.status == "not_applicable"
    accounts = await shop.report(get_analytics_accounts)
    assert accounts.labor_cost_status == "unavailable"
    assert accounts.accounts[0].model_dump() == {
        "name": "Cost account", "revenue": 300, "marginPct": None, "cumPct": 100,
    }


@pytest.mark.asyncio
async def test_endpoint_preserves_snapshots_discounts_sublet_and_fractional_precision(shop):
    discounted = await shop.order(total_cost=Decimal("240"), total_parts_cost=Decimal("180"))
    shop.part(discounted, revenue="180", cost="120", list_price=Decimal("200"))
    shop.labor(discounted, revenue="100")
    sublet = await shop.order(total_cost=Decimal("250"))
    shop.labor(sublet, revenue="300", cost="220", hours="4", line_type=LaborLineType.SUBLET)
    fractional = await shop.order()
    shop.part(fractional, revenue="0.10", cost="0.05", quantity="0.33")
    shop.part(fractional, revenue="0.10", cost="0.05", quantity="0.33")
    rows = {row.repair_order_id: row for row in (await shop.report()).ros}
    part = rows[str(discounted.id)].parts_contribution
    assert (part.revenue, part.contribution, part.margin_pct) == ("180.00", "60.00", "33.33")
    sub = rows[str(sublet.id)].sublet_contribution
    assert (sub.known_cost, sub.contribution, sub.margin_pct) == ("220.00", "80.00", "26.67")
    assert rows[str(fractional.id)].parts_contribution.known_cost == "0.03"
    assert rows[str(fractional.id)].parts_contribution.margin_pct == "83.50"


@pytest.mark.asyncio
async def test_endpoint_missing_cost_is_not_inventory_cost_zero_or_a_profit(shop):
    unknown = await shop.order()
    shop.part(unknown, cost=None)
    shop.labor(unknown, revenue="300", cost=None, line_type=LaborLineType.SUBLET)
    partial = await shop.order()
    shop.part(partial, cost="0")
    shop.part(partial, cost=None)
    zero = await shop.order()
    shop.part(zero, cost="0")
    loss = await shop.order()
    shop.part(loss, revenue="100", cost="120")
    free = await shop.order()
    shop.part(free, revenue="0", cost="20")
    empty = await shop.order()
    shop.labor(empty)
    rows = {row.repair_order_id: row for row in (await shop.report()).ros}
    assert rows[str(unknown.id)].parts_contribution.status == "unavailable"
    assert rows[str(unknown.id)].parts_contribution.known_cost == "0.00"
    assert rows[str(unknown.id)].sublet_contribution.contribution is None
    assert rows[str(partial.id)].parts_contribution.status == "partial"
    assert rows[str(partial.id)].parts_contribution.contribution is None
    assert rows[str(zero.id)].parts_contribution.margin_pct == "100.00"
    assert rows[str(loss.id)].parts_contribution.contribution == "-20.00"
    assert rows[str(free.id)].parts_contribution.contribution == "-20.00"
    assert rows[str(free.id)].parts_contribution.margin_pct is None
    assert rows[str(empty.id)].parts_contribution.status == "not_applicable"
    assert all(row.marginPct is None for row in rows.values())


@pytest.mark.asyncio
async def test_foreign_deleted_or_orphaned_children_cannot_change_costs_counts_or_hours(shop):
    order = await shop.order()
    shop.part(order)
    shop.labor(order)
    shop.labor(order, revenue="300", cost="220", line_type=LaborLineType.SUBLET)
    for overrides in ({"tenant_id": shop.foreign.id}, {"deleted_at": NOW}, {"repair_order_id": uuid4()}):
        shop.part(order, revenue="999", cost=None, **overrides)
        shop.labor(order, revenue="999", hours="99", line_type=LaborLineType.SUBLET, **overrides)
    foreign_order = await shop.order(tenant_id=shop.foreign.id)
    deleted_order = await shop.order(deleted_at=NOW)
    outside_range = await shop.order(created_at=datetime(2026, 10, 11, 12, tzinfo=timezone.utc))
    zero_order = await shop.order(total_cost=Decimal("0"))
    for excluded in (foreign_order, deleted_order, outside_range, zero_order):
        shop.part(excluded)
        shop.labor(excluded)
    row, = (await shop.report()).ros
    assert row.repair_order_id == str(order.id)
    assert row.parts_contribution.line_count == 1
    assert row.parts_contribution.contribution == "80.00"
    assert row.sublet_contribution.line_count == 1
    assert row.sublet_contribution.contribution == "80.00"
    assert row.hours == 2


@pytest.mark.asyncio
async def test_accounts_preserve_revenue_ranking_and_exclude_foreign_or_deleted_links(shop, db_session):
    valid = await shop.order()
    shop.invoice(valid)
    foreign_order = await shop.order(tenant_id=shop.foreign.id)
    foreign_customer_order = await shop.order(customer_id=shop.foreign_customer.id)
    deleted_order = await shop.order(deleted_at=NOW)
    for invalid in (foreign_order, foreign_customer_order, deleted_order):
        shop.invoice(invalid, total_amount=Decimal("999"))
    foreign_invoice_order = await shop.order()
    deleted_invoice_order = await shop.order()
    shop.invoice(foreign_invoice_order, tenant_id=shop.foreign.id, total_amount=Decimal("999"))
    shop.invoice(deleted_invoice_order, deleted_at=NOW, total_amount=Decimal("999"))
    second_customer = Customer(tenant_id=shop.tenant.id, first_name="Second", last_name="Account",
                               company_name="Larger account", email=f"second-{uuid4().hex}@example.com")
    deleted_customer = Customer(tenant_id=shop.tenant.id, first_name="Deleted", last_name="Account",
                                email=f"deleted-{uuid4().hex}@example.com", deleted_at=NOW)
    db_session.add_all([second_customer, deleted_customer])
    await db_session.flush()
    second_order = await shop.order(customer_id=second_customer.id)
    deleted_customer_order = await shop.order(customer_id=deleted_customer.id)
    shop.invoice(second_order, total_amount=Decimal("900"))
    shop.invoice(deleted_customer_order, total_amount=Decimal("999"))
    result = await shop.report(get_analytics_accounts)
    assert [row.model_dump() for row in result.accounts] == [
        {"name": "Larger account", "revenue": 900, "cumPct": 75, "marginPct": None},
        {"name": "Cost account", "revenue": 300, "cumPct": 100, "marginPct": None},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [get_analytics_profitability, get_analytics_accounts])
async def test_report_permissions_remain_manager_only(shop, db_session, endpoint):
    shop.owner.role = UserRole.MECHANIC
    with pytest.raises(HTTPException) as exc:
        await endpoint(range="custom", from_date=DAY, to_date=DAY, db=db_session, current_user=shop.owner)
    assert exc.value.status_code == 403
    shop.owner.role = UserRole.GARAGE_OWNER
    shop.owner.tenant_id = None
    with pytest.raises(HTTPException) as exc:
        await endpoint(range="custom", from_date=DAY, to_date=DAY, db=db_session, current_user=shop.owner)
    assert exc.value.status_code == 400
