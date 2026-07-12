"""Owner/admin-facing business reports: revenue, labor/parts/fees/tax
breakdowns, parts profitability, inventory valuation, and service-type
performance, all filterable by date range (This Year/Quarter/Month/Week,
last-period equivalents, or a custom range).
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.date_ranges import REPORT_DATE_PRESETS, DateRange, resolve_date_range
from app.core.dependencies import get_db, get_current_active_user
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.labor import Labor
from app.db.models.repair_order import RepairOrder
from app.db.models.service import Service
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole

router = APIRouter()


def _require_manager(current_user: User) -> None:
    if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shop owner/admin access required")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


async def _get_tenant(db: AsyncSession, tenant_id: UUID) -> Tenant:
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


async def _resolve_range(
    db: AsyncSession,
    tenant_id: UUID,
    preset: str,
    date_from: Optional[date],
    date_to: Optional[date],
) -> DateRange:
    if preset not in REPORT_DATE_PRESETS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid range: {preset!r}")
    tenant = await _get_tenant(db, tenant_id)
    try:
        return resolve_date_range(preset, tenant.timezone, date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Dashboard tab: headline cards + weekly trend series
# ---------------------------------------------------------------------------

class TrendPoint(BaseModel):
    label: str
    value: str


class DashboardMetric(BaseModel):
    value: str
    trend: List[TrendPoint] = []


class ReportsDashboardResponse(BaseModel):
    range_start: date
    range_end: date
    revenue: DashboardMetric
    labor_revenue: DashboardMetric
    part_revenue: DashboardMetric
    fees_revenue: DashboardMetric
    parts_profit: DashboardMetric
    inventory_value: DashboardMetric
    invoiced_hours: DashboardMetric
    part_sales_finalized: DashboardMetric
    services_finalized: DashboardMetric


def _week_buckets(rng: DateRange) -> List[tuple[date, date, str]]:
    """Split the range into calendar weeks (Mon-Sun) for the trend charts.
    Label with the ISO week number plus the week's start date (e.g.
    "W27 · Jul 7") so it's anchorable — a bare week number is meaningless to
    most people and the dashboard shows no dates otherwise."""
    buckets = []
    cursor = rng.start - timedelta(days=rng.start.weekday())
    while cursor <= rng.end:
        week_end = cursor + timedelta(days=6)
        iso_week = cursor.isocalendar()[1]
        label = f"W{iso_week} · {cursor.strftime('%b %-d')}"
        buckets.append((cursor, week_end, label))
        cursor = week_end + timedelta(days=1)
    return buckets


@router.get("/dashboard", response_model=ReportsDashboardResponse)
async def get_reports_dashboard(
    range: str = Query("this_month"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)
    weeks = _week_buckets(rng)

    # Paid invoices in range (cash basis: recognized when paid).
    result = await db.execute(
        select(Invoice, RepairOrder)
        .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.is_internal.is_(False),
            func.date(Invoice.paid_at) >= rng.start,
            func.date(Invoice.paid_at) <= rng.end,
        )
    )
    paid_rows = result.all()

    order_ids = [ro.id for _, ro in paid_rows]
    parts_cost_by_order: Dict[UUID, Decimal] = {}
    if order_ids:
        cost_result = await db.execute(
            select(PartsUsage.repair_order_id, func.coalesce(func.sum(PartsUsage.unit_cost * PartsUsage.quantity), 0))
            .where(PartsUsage.repair_order_id.in_(order_ids))
            .group_by(PartsUsage.repair_order_id)
        )
        parts_cost_by_order = {rid: _money(cost) for rid, cost in cost_result.all()}

    def week_index(d: date) -> Optional[int]:
        for i, (wstart, wend, _label) in enumerate(weeks):
            if wstart <= d <= wend:
                return i
        return None

    revenue_by_week = [Decimal("0.00") for _ in weeks]
    labor_by_week = [Decimal("0.00") for _ in weeks]
    parts_rev_by_week = [Decimal("0.00") for _ in weeks]
    fees_by_week = [Decimal("0.00") for _ in weeks]
    parts_profit_by_week = [Decimal("0.00") for _ in weeks]
    invoiced_hours_by_week = [Decimal("0.00") for _ in weeks]
    part_sales_by_week = [0 for _ in weeks]
    services_by_week = [0 for _ in weeks]

    total_revenue = Decimal("0.00")
    total_labor = Decimal("0.00")
    total_parts_rev = Decimal("0.00")
    total_fees = Decimal("0.00")
    total_parts_profit = Decimal("0.00")

    for invoice, order in paid_rows:
        paid_date = invoice.paid_at.date() if invoice.paid_at else rng.start
        idx = week_index(paid_date)

        net_sales = _money(invoice.total_amount)
        parts_rev = _money(order.total_parts_cost)
        labor_rev = _money(order.total_labor_cost)
        fees = _money(invoice.shop_supplies_amount) + _money(invoice.service_fee_amount)
        parts_cost = parts_cost_by_order.get(order.id, Decimal("0.00"))
        parts_profit = parts_rev - parts_cost

        total_revenue += net_sales
        total_labor += labor_rev
        total_parts_rev += parts_rev
        total_fees += fees
        total_parts_profit += parts_profit

        if idx is not None:
            revenue_by_week[idx] += net_sales
            labor_by_week[idx] += labor_rev
            parts_rev_by_week[idx] += parts_rev
            fees_by_week[idx] += fees
            parts_profit_by_week[idx] += parts_profit
            if order.total_parts_cost and order.total_parts_cost > 0:
                part_sales_by_week[idx] += 1
            services_by_week[idx] += 1

    # Invoiced hours: labor hours on paid orders in range.
    invoiced_hours_total = Decimal("0.00")
    if order_ids:
        labor_result = await db.execute(
            select(Labor.repair_order_id, func.coalesce(func.sum(Labor.hours), 0))
            .where(Labor.repair_order_id.in_(order_ids))
            .group_by(Labor.repair_order_id)
        )
        hours_by_order = dict(labor_result.all())
        order_paid_date = {ro.id: (inv.paid_at.date() if inv.paid_at else rng.start) for inv, ro in paid_rows}
        for oid, hours in hours_by_order.items():
            hours_dec = Decimal(str(hours or 0))
            invoiced_hours_total += hours_dec
            idx = week_index(order_paid_date.get(oid, rng.start))
            if idx is not None:
                invoiced_hours_by_week[idx] += hours_dec

    # Current inventory value (point-in-time, not range-bound — matches ETS,
    # which shows the *current* stock value on every date range).
    inv_result = await db.execute(
        select(func.coalesce(func.sum(Inventory.cost * Inventory.stock_quantity), 0)).where(
            Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None)
        )
    )
    inventory_value = _money(inv_result.scalar())

    def trend(values: List[Decimal]) -> List[TrendPoint]:
        return [TrendPoint(label=weeks[i][2], value=str(v)) for i, v in enumerate(values)]

    def trend_int(values: List[int]) -> List[TrendPoint]:
        return [TrendPoint(label=weeks[i][2], value=str(v)) for i, v in enumerate(values)]

    return ReportsDashboardResponse(
        range_start=rng.start,
        range_end=rng.end,
        revenue=DashboardMetric(value=str(total_revenue), trend=trend(revenue_by_week)),
        labor_revenue=DashboardMetric(value=str(total_labor), trend=trend(labor_by_week)),
        part_revenue=DashboardMetric(value=str(total_parts_rev), trend=trend(parts_rev_by_week)),
        fees_revenue=DashboardMetric(value=str(total_fees), trend=trend(fees_by_week)),
        parts_profit=DashboardMetric(value=str(total_parts_profit), trend=trend(parts_profit_by_week)),
        inventory_value=DashboardMetric(value=str(inventory_value), trend=[]),
        invoiced_hours=DashboardMetric(value=str(invoiced_hours_total), trend=trend(invoiced_hours_by_week)),
        part_sales_finalized=DashboardMetric(value=str(sum(part_sales_by_week)), trend=trend_int(part_sales_by_week)),
        services_finalized=DashboardMetric(value=str(sum(services_by_week)), trend=trend_int(services_by_week)),
    )


# ---------------------------------------------------------------------------
# Sales tab: net sales / labor / parts / discounts / fees / tax, grouped by
# customer (the only grouping our data model supports today — ETS also offers
# customer group / ownership / sale type / vehicle type, which we don't have
# separate fields for yet).
# ---------------------------------------------------------------------------

class SalesSummary(BaseModel):
    net_sales: str
    labor: str
    parts: str
    discounts: str
    fees: str
    sales_tax: str


class SalesGroupRow(BaseModel):
    group_key: str
    group_label: str
    labor: str
    parts: str
    fees: str
    sales_tax: str
    discounts: str
    net_sales: str


class ReportsSalesResponse(BaseModel):
    range_start: date
    range_end: date
    summary: SalesSummary
    rows: List[SalesGroupRow]


@router.get("/sales", response_model=ReportsSalesResponse)
async def get_reports_sales(
    range: str = Query("this_month"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)

    result = await db.execute(
        select(Invoice, RepairOrder, Customer)
        .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.is_internal.is_(False),
            func.date(Invoice.paid_at) >= rng.start,
            func.date(Invoice.paid_at) <= rng.end,
        )
    )
    rows = result.all()

    totals = {"net_sales": Decimal("0"), "labor": Decimal("0"), "parts": Decimal("0"),
              "discounts": Decimal("0"), "fees": Decimal("0"), "sales_tax": Decimal("0")}
    by_customer: Dict[UUID, Dict[str, Decimal]] = {}
    customer_labels: Dict[UUID, str] = {}

    for invoice, order, customer in rows:
        labor = _money(order.total_labor_cost)
        parts = _money(order.total_parts_cost)
        fees = _money(invoice.shop_supplies_amount) + _money(invoice.service_fee_amount)
        tax = _money(invoice.tax_amount)
        discounts = _money(invoice.discount_amount)
        net_sales = _money(invoice.total_amount)

        totals["labor"] += labor
        totals["parts"] += parts
        totals["fees"] += fees
        totals["sales_tax"] += tax
        totals["discounts"] += discounts
        totals["net_sales"] += net_sales

        bucket = by_customer.setdefault(customer.id, {
            "labor": Decimal("0"), "parts": Decimal("0"), "fees": Decimal("0"),
            "sales_tax": Decimal("0"), "discounts": Decimal("0"), "net_sales": Decimal("0"),
        })
        bucket["labor"] += labor
        bucket["parts"] += parts
        bucket["fees"] += fees
        bucket["sales_tax"] += tax
        bucket["discounts"] += discounts
        bucket["net_sales"] += net_sales
        customer_labels[customer.id] = customer.company_name or f"{customer.first_name} {customer.last_name}".strip()

    group_rows = [
        SalesGroupRow(
            group_key=str(cid),
            group_label=customer_labels[cid],
            labor=str(vals["labor"]),
            parts=str(vals["parts"]),
            fees=str(vals["fees"]),
            sales_tax=str(vals["sales_tax"]),
            discounts=str(vals["discounts"]),
            net_sales=str(vals["net_sales"]),
        )
        for cid, vals in by_customer.items()
    ]
    group_rows.sort(key=lambda r: Decimal(r.net_sales), reverse=True)

    return ReportsSalesResponse(
        range_start=rng.start,
        range_end=rng.end,
        summary=SalesSummary(
            net_sales=str(totals["net_sales"]),
            labor=str(totals["labor"]),
            parts=str(totals["parts"]),
            discounts=str(totals["discounts"]),
            fees=str(totals["fees"]),
            sales_tax=str(totals["sales_tax"]),
        ),
        rows=group_rows,
    )


# ---------------------------------------------------------------------------
# Fees tab: our data model only carries two named fee categories on an
# invoice (shop supplies, service fee) rather than a free-form fee catalog
# like ETS — so "fee name" here means one of those two, not an arbitrary list.
# ---------------------------------------------------------------------------

class FeeRow(BaseModel):
    fee_name: str
    times_added: int
    average_charge: str
    total_charged: str


class ReportsFeesResponse(BaseModel):
    range_start: date
    range_end: date
    times_added: int
    average_charge: str
    total_charged: str
    rows: List[FeeRow]


@router.get("/fees", response_model=ReportsFeesResponse)
async def get_reports_fees(
    range: str = Query("this_month"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)

    result = await db.execute(
        select(Invoice.shop_supplies_amount, Invoice.service_fee_amount).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.is_internal.is_(False),
            func.date(Invoice.paid_at) >= rng.start,
            func.date(Invoice.paid_at) <= rng.end,
        )
    )
    rows = result.all()

    categories = {
        "Shop Supplies": [],
        "Service Fee": [],
    }
    for shop_supplies, service_fee in rows:
        if shop_supplies and shop_supplies > 0:
            categories["Shop Supplies"].append(_money(shop_supplies))
        if service_fee and service_fee > 0:
            categories["Service Fee"].append(_money(service_fee))

    fee_rows = []
    grand_total = Decimal("0.00")
    grand_count = 0
    for name, charges in categories.items():
        if not charges:
            continue
        total = sum(charges, Decimal("0.00"))
        count = len(charges)
        grand_total += total
        grand_count += count
        fee_rows.append(FeeRow(
            fee_name=name,
            times_added=count,
            average_charge=str((total / count).quantize(Decimal("0.01"))),
            total_charged=str(total),
        ))
    fee_rows.sort(key=lambda r: Decimal(r.total_charged), reverse=True)

    return ReportsFeesResponse(
        range_start=rng.start,
        range_end=rng.end,
        times_added=grand_count,
        average_charge=str((grand_total / grand_count).quantize(Decimal("0.01"))) if grand_count else "0.00",
        total_charged=str(grand_total),
        rows=fee_rows,
    )


# ---------------------------------------------------------------------------
# Sales Tax tab: a single flat rate per tenant today (not a multi-jurisdiction
# rate table like ETS), so this is one row rather than a per-rate breakdown.
# ---------------------------------------------------------------------------

class TaxRow(BaseModel):
    rate_label: str
    percentage: str
    tax_collected: str


class ReportsTaxResponse(BaseModel):
    range_start: date
    range_end: date
    rows: List[TaxRow]


@router.get("/tax", response_model=ReportsTaxResponse)
async def get_reports_tax(
    range: str = Query("this_month"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)
    tenant = await _get_tenant(db, tenant_id)

    result = await db.execute(
        select(func.coalesce(func.sum(Invoice.tax_amount), 0)).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.is_internal.is_(False),
            func.date(Invoice.paid_at) >= rng.start,
            func.date(Invoice.paid_at) <= rng.end,
        )
    )
    tax_collected = _money(result.scalar())

    rows = []
    if tax_collected > 0:
        rows.append(TaxRow(
            rate_label="Sales Tax",
            percentage=str(tenant.sales_tax_rate or Decimal("0.000")),
            tax_collected=str(tax_collected),
        ))

    return ReportsTaxResponse(range_start=rng.start, range_end=rng.end, rows=rows)


# ---------------------------------------------------------------------------
# Part Revenue tab: revenue / cost / profit / margin, grouped by invoice.
# ---------------------------------------------------------------------------

class PartRevenueRow(BaseModel):
    invoice_number: str
    revenue: str
    cost: str
    profit: str
    margin_pct: str


class ReportsPartsResponse(BaseModel):
    range_start: date
    range_end: date
    revenue: str
    cost: str
    profit: str
    margin_pct: str
    rows: List[PartRevenueRow]


@router.get("/parts", response_model=ReportsPartsResponse)
async def get_reports_parts(
    range: str = Query("this_month"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)

    result = await db.execute(
        select(Invoice, RepairOrder)
        .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.is_internal.is_(False),
            func.date(Invoice.paid_at) >= rng.start,
            func.date(Invoice.paid_at) <= rng.end,
        )
    )
    rows = result.all()
    order_ids = [order.id for _, order in rows]

    parts_cost_by_order: Dict[UUID, Decimal] = {}
    if order_ids:
        cost_result = await db.execute(
            select(PartsUsage.repair_order_id, func.coalesce(func.sum(PartsUsage.unit_cost * PartsUsage.quantity), 0))
            .where(PartsUsage.repair_order_id.in_(order_ids))
            .group_by(PartsUsage.repair_order_id)
        )
        parts_cost_by_order = {rid: _money(cost) for rid, cost in cost_result.all()}

    part_rows = []
    total_revenue = Decimal("0.00")
    total_cost = Decimal("0.00")
    for invoice, order in rows:
        revenue = _money(order.total_parts_cost)
        if revenue <= 0:
            continue
        cost = parts_cost_by_order.get(order.id, Decimal("0.00"))
        profit = revenue - cost
        margin = (profit / revenue * 100).quantize(Decimal("0.01")) if revenue else Decimal("0.00")
        total_revenue += revenue
        total_cost += cost
        part_rows.append(PartRevenueRow(
            invoice_number=invoice.invoice_number,
            revenue=str(revenue),
            cost=str(cost),
            profit=str(profit),
            margin_pct=str(margin),
        ))
    part_rows.sort(key=lambda r: Decimal(r.revenue), reverse=True)

    total_profit = total_revenue - total_cost
    total_margin = (total_profit / total_revenue * 100).quantize(Decimal("0.01")) if total_revenue else Decimal("0.00")

    return ReportsPartsResponse(
        range_start=rng.start,
        range_end=rng.end,
        revenue=str(total_revenue),
        cost=str(total_cost),
        profit=str(total_profit),
        margin_pct=str(total_margin),
        rows=part_rows,
    )


# ---------------------------------------------------------------------------
# Inventory tab: current stock valuation (point-in-time, not date-ranged —
# matches ETS, which shows the *current* value regardless of the date filter).
# ---------------------------------------------------------------------------

class InventoryRow(BaseModel):
    sku: str
    name: str
    quantity: str
    unit_cost: str
    total_value: str


class ReportsInventoryResponse(BaseModel):
    part_value: str
    total_value: str
    rows: List[InventoryRow]


@router.get("/inventory", response_model=ReportsInventoryResponse)
async def get_reports_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id

    result = await db.execute(
        select(Inventory)
        .where(Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None))
        .order_by((Inventory.cost * Inventory.stock_quantity).desc())
    )
    items = result.scalars().all()

    rows = []
    total_value = Decimal("0.00")
    for item in items:
        value = _money(item.cost) * item.stock_quantity
        total_value += value
        rows.append(InventoryRow(
            sku=item.sku,
            name=item.name,
            quantity=str(item.stock_quantity),
            unit_cost=str(_money(item.cost)),
            total_value=str(value),
        ))

    return ReportsInventoryResponse(
        part_value=str(total_value),
        total_value=str(total_value),
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Service Types tab: labor lines grouped by their catalog service (or raw
# description text for older/imported lines with no linked Service).
# ---------------------------------------------------------------------------

class ServiceTypeRow(BaseModel):
    name: str
    quantity: int
    hours_billed: str
    total_charged: str


class ReportsServiceTypesResponse(BaseModel):
    range_start: date
    range_end: date
    service_items: int
    hours_billed: str
    total_charged: str
    rows: List[ServiceTypeRow]


@router.get("/service-types", response_model=ReportsServiceTypesResponse)
async def get_reports_service_types(
    range: str = Query("this_month"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)

    result = await db.execute(
        select(Labor, Service.name)
        .join(RepairOrder, Labor.repair_order_id == RepairOrder.id)
        .join(Invoice, Invoice.repair_order_id == RepairOrder.id)
        .outerjoin(Service, Labor.source_service_id == Service.id)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.is_internal.is_(False),
            func.date(Invoice.paid_at) >= rng.start,
            func.date(Invoice.paid_at) <= rng.end,
        )
    )
    rows = result.all()

    grouped: Dict[str, Dict[str, object]] = {}
    for labor, service_name in rows:
        name = service_name or labor.description or "Other"
        bucket = grouped.setdefault(name, {"quantity": 0, "hours": Decimal("0.00"), "charged": Decimal("0.00")})
        bucket["quantity"] += 1
        bucket["hours"] += Decimal(str(labor.hours or 0))
        bucket["charged"] += _money(labor.total_cost)

    service_rows = [
        ServiceTypeRow(
            name=name,
            quantity=vals["quantity"],
            hours_billed=str(vals["hours"]),
            total_charged=str(vals["charged"]),
        )
        for name, vals in grouped.items()
    ]
    service_rows.sort(key=lambda r: Decimal(r.total_charged), reverse=True)

    total_items = sum(r.quantity for r in service_rows)
    total_hours = sum((Decimal(r.hours_billed) for r in service_rows), Decimal("0.00"))
    total_charged = sum((Decimal(r.total_charged) for r in service_rows), Decimal("0.00"))

    return ReportsServiceTypesResponse(
        range_start=rng.start,
        range_end=rng.end,
        service_items=total_items,
        hours_billed=str(total_hours),
        total_charged=str(total_charged),
        rows=service_rows,
    )


# ===========================================================================
# Analytics charts — the richer visualisations for the Analytics dashboard.
# Only aggregations backed by existing data are implemented here; charts that
# need event tracking we don't yet capture (quote "viewed", historical
# per-mile fleet cost) are deferred.
# ===========================================================================


class ScatterPoint(BaseModel):
    type: str
    subtotal: float
    marginPct: float
    hours: float


class ProfitabilityResponse(BaseModel):
    range_start: date
    range_end: date
    ros: List[ScatterPoint]


def _ro_type(order: RepairOrder) -> str:
    if order.is_internal:
        return "Internal"
    if order.is_pm:
        return "PM"
    if order.is_warranty_repair:
        return "Warranty"
    return "Repair"


@router.get("/analytics/profitability", response_model=ProfitabilityResponse)
async def get_analytics_profitability(
    range: str = Query("this_month"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Per-RO subtotal vs margin %, sized by labor hours — powers the
    labor-vs-parts profitability bubble scatter."""
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)

    # Sum labor hours per RO in one grouped query, then join the orders.
    hours_result = await db.execute(
        select(Labor.repair_order_id, func.coalesce(func.sum(Labor.hours), 0))
        .join(RepairOrder, Labor.repair_order_id == RepairOrder.id)
        .where(RepairOrder.tenant_id == tenant_id)
        .group_by(Labor.repair_order_id)
    )
    hours_by_ro = {rid: Decimal(str(h or 0)) for rid, h in hours_result.all()}

    result = await db.execute(
        select(RepairOrder).where(
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.deleted_at.is_(None),
            func.date(RepairOrder.created_at) >= rng.start,
            func.date(RepairOrder.created_at) <= rng.end,
        )
    )
    orders = result.scalars().all()

    points: List[ScatterPoint] = []
    for o in orders:
        subtotal = _money(o.total_cost)
        cost = _money(o.total_labor_cost) + _money(o.total_parts_cost)
        if subtotal <= 0:
            continue
        margin_pct = float(((subtotal - cost) / subtotal) * 100) if subtotal else 0.0
        points.append(ScatterPoint(
            type=_ro_type(o),
            subtotal=float(subtotal),
            marginPct=round(max(0.0, min(100.0, margin_pct)), 1),
            hours=float(hours_by_ro.get(o.id, Decimal("0"))),
        ))

    return ProfitabilityResponse(range_start=rng.start, range_end=rng.end, ros=points)


class AccountRow(BaseModel):
    name: str
    revenue: float
    marginPct: float
    cumPct: float


class AccountsResponse(BaseModel):
    range_start: date
    range_end: date
    accounts: List[AccountRow]


@router.get("/analytics/accounts", response_model=AccountsResponse)
async def get_analytics_accounts(
    range: str = Query("this_year"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Revenue + margin per customer account, sorted desc with a running
    cumulative % — powers the Pareto chart and the account detail table."""
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)

    result = await db.execute(
        select(Invoice, RepairOrder, Customer)
        .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.is_internal.is_(False),
            func.date(Invoice.paid_at) >= rng.start,
            func.date(Invoice.paid_at) <= rng.end,
        )
    )
    rows = result.all()

    by_customer: Dict[UUID, Dict[str, Decimal]] = {}
    labels: Dict[UUID, str] = {}
    for invoice, order, customer in rows:
        b = by_customer.setdefault(customer.id, {"rev": Decimal("0"), "cost": Decimal("0")})
        b["rev"] += _money(invoice.total_amount)
        b["cost"] += _money(order.total_labor_cost) + _money(order.total_parts_cost)
        labels[customer.id] = customer.company_name or f"{customer.first_name} {customer.last_name}".strip()

    ranked = sorted(by_customer.items(), key=lambda kv: kv[1]["rev"], reverse=True)
    total_rev = sum((v["rev"] for _, v in ranked), Decimal("0")) or Decimal("1")

    accounts: List[AccountRow] = []
    running = Decimal("0")
    for cid, vals in ranked:
        running += vals["rev"]
        margin = float(((vals["rev"] - vals["cost"]) / vals["rev"]) * 100) if vals["rev"] else 0.0
        accounts.append(AccountRow(
            name=labels[cid],
            revenue=float(vals["rev"]),
            marginPct=round(max(0.0, min(100.0, margin)), 1),
            cumPct=round(float(running / total_rev * 100), 1),
        ))

    return AccountsResponse(range_start=rng.start, range_end=rng.end, accounts=accounts)


class FunnelResponse(BaseModel):
    range_start: date
    range_end: date
    sent: int
    approved: int
    invoiced: int


@router.get("/analytics/quote-funnel", response_model=FunnelResponse)
async def get_analytics_quote_funnel(
    range: str = Query("this_month"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Quote sent -> approved -> invoiced counts. NOTE: a "viewed" stage is
    intentionally omitted — the app does not yet record a quote-view event."""
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)

    from app.db.models.quote import Quote

    sent = (await db.execute(
        select(func.count(Quote.id)).where(
            Quote.tenant_id == tenant_id,
            Quote.sent_to_customer.is_(True),
            func.date(Quote.created_at) >= rng.start,
            func.date(Quote.created_at) <= rng.end,
        )
    )).scalar() or 0
    approved = (await db.execute(
        select(func.count(Quote.id)).where(
            Quote.tenant_id == tenant_id,
            Quote.is_approved.is_(True),
            func.date(Quote.created_at) >= rng.start,
            func.date(Quote.created_at) <= rng.end,
        )
    )).scalar() or 0
    invoiced = (await db.execute(
        select(func.count(Invoice.id))
        .join(Quote, Quote.repair_order_id == Invoice.repair_order_id)
        .where(
            Invoice.tenant_id == tenant_id,
            Quote.is_approved.is_(True),
            func.date(Quote.created_at) >= rng.start,
            func.date(Quote.created_at) <= rng.end,
        )
    )).scalar() or 0

    return FunnelResponse(range_start=rng.start, range_end=rng.end, sent=sent, approved=approved, invoiced=invoiced)


class TruckCostRow(BaseModel):
    unit: str
    ytdCost: float


class TruckCostResponse(BaseModel):
    range_start: date
    range_end: date
    trucks: List[TruckCostRow]


@router.get("/analytics/truck-costs", response_model=TruckCostResponse)
async def get_analytics_truck_costs(
    range: str = Query("this_year"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Internal-fleet maintenance cost per truck (top spenders) — powers the
    cost-per-truck ranked bar."""
    _require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id
    rng = await _resolve_range(db, tenant_id, range, from_date, to_date)

    from app.db.models.vehicle import Vehicle

    result = await db.execute(
        select(Vehicle.unit_number, func.coalesce(func.sum(RepairOrder.total_cost), 0))
        .join(RepairOrder, RepairOrder.vehicle_id == Vehicle.id)
        .where(
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.is_internal.is_(True),
            RepairOrder.deleted_at.is_(None),
            func.date(RepairOrder.created_at) >= rng.start,
            func.date(RepairOrder.created_at) <= rng.end,
        )
        .group_by(Vehicle.unit_number)
    )
    rows = [(unit or "—", _money(cost)) for unit, cost in result.all()]
    rows.sort(key=lambda r: r[1], reverse=True)
    trucks = [TruckCostRow(unit=u, ytdCost=float(c)) for u, c in rows[:10]]

    return TruckCostResponse(range_start=rng.start, range_end=rng.end, trucks=trucks)
