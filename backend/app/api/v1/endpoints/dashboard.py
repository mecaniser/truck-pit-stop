from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, cast, Date
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime, timedelta, date, timezone
from decimal import Decimal

from sqlalchemy.orm import aliased
from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment, PaymentStatus
from app.services.pricing import get_order_labor_total, get_order_subtotal

router = APIRouter()


def get_effective_total(order: RepairOrder) -> Decimal:
    return get_order_subtotal(order)


class StatusCount(BaseModel):
    status: str
    count: int


class RecentOrder(BaseModel):
    id: str
    order_number: str
    status: str
    description: Optional[str]
    customer_name: str
    vehicle_info: str
    total_cost: str
    created_at: datetime
    updated_at: datetime
    mechanic_name: Optional[str] = None
    work_started_at: Optional[datetime] = None


class LowStockItem(BaseModel):
    id: str
    sku: str
    name: str
    stock_quantity: int
    reorder_level: int


class MechanicWorkload(BaseModel):
    mechanic_id: str
    mechanic_name: str
    assigned_count: int
    in_progress_count: int


class RevenueStats(BaseModel):
    today: str
    this_week: str
    this_month: str
    total_paid_orders: int
    today_parts_margin: str = "0.00"
    this_week_parts_margin: str = "0.00"
    this_month_parts_margin: str = "0.00"
    today_gross_profit: str = "0.00"
    this_week_gross_profit: str = "0.00"
    this_month_gross_profit: str = "0.00"
    today_ppi: str = "0.00"
    this_week_ppi: str = "0.00"
    this_month_ppi: str = "0.00"


class DashboardStats(BaseModel):
    total_customers: int
    total_vehicles: int
    total_repair_orders: int
    orders_by_status: List[StatusCount]
    active_orders: int  # in_progress
    awaiting_approval: int  # quoted
    pending_invoices: int  # completed
    low_stock_count: int
    low_stock_items: List[LowStockItem]
    recent_orders: List[RecentOrder]
    # For mechanics: their assigned orders
    my_assigned_orders: int
    my_in_progress: int
    # Phase 2: Revenue and workload
    revenue: RevenueStats
    mechanic_workload: List[MechanicWorkload]
    # Alerts: overdue approvals (quoted > 3 days)
    overdue_approvals: int = 0
    declined_quotes: int = 0
    # Work queue lanes
    orders_needing_action: List[RecentOrder] = []
    orders_on_floor: List[RecentOrder] = []
    orders_ready_to_close: List[RecentOrder] = []


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        return DashboardStats(
            total_customers=0,
            total_vehicles=0,
            total_repair_orders=0,
            orders_by_status=[],
            active_orders=0,
            awaiting_approval=0,
            pending_invoices=0,
            low_stock_count=0,
            low_stock_items=[],
            recent_orders=[],
            my_assigned_orders=0,
            my_in_progress=0,
            revenue=RevenueStats(today="0.00", this_week="0.00", this_month="0.00", total_paid_orders=0),
            mechanic_workload=[],
            overdue_approvals=0,
            declined_quotes=0,
            orders_needing_action=[],
            orders_on_floor=[],
            orders_ready_to_close=[],
        )

    # Total customers
    result = await db.execute(
        select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)
    )
    total_customers = result.scalar() or 0

    # Total vehicles
    result = await db.execute(
        select(func.count(Vehicle.id)).where(Vehicle.tenant_id == tenant_id)
    )
    total_vehicles = result.scalar() or 0

    # Total repair orders
    result = await db.execute(
        select(func.count(RepairOrder.id)).where(RepairOrder.tenant_id == tenant_id)
    )
    total_repair_orders = result.scalar() or 0

    # Orders by status
    result = await db.execute(
        select(RepairOrder.status, func.count(RepairOrder.id))
        .where(RepairOrder.tenant_id == tenant_id)
        .group_by(RepairOrder.status)
    )
    status_counts = result.all()
    orders_by_status = [
        StatusCount(status=s.value if hasattr(s, "value") else s, count=c)
        for s, c in status_counts
    ]

    # Count specific statuses
    status_map = {sc.status: sc.count for sc in orders_by_status}
    active_orders = status_map.get("in_progress", 0)
    awaiting_approval = status_map.get("quoted", 0)
    pending_invoices = status_map.get("completed", 0)

    # Overdue approvals: quoted orders older than 3 days
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    result = await db.execute(
        select(func.count(RepairOrder.id)).where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.QUOTED,
                RepairOrder.updated_at < three_days_ago,
            )
        )
    )
    overdue_approvals = result.scalar() or 0

    # Declined quotes count
    result = await db.execute(
        select(func.count(RepairOrder.id)).where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.DECLINED,
            )
        )
    )
    declined_quotes = result.scalar() or 0

    # Low stock items (stock_quantity <= reorder_level)
    result = await db.execute(
        select(Inventory)
        .where(
            and_(
                Inventory.tenant_id == tenant_id,
                Inventory.stock_quantity <= Inventory.reorder_level,
            )
        )
        .limit(10)
    )
    low_stock = result.scalars().all()
    low_stock_items = [
        LowStockItem(
            id=str(item.id),
            sku=item.sku,
            name=item.name,
            stock_quantity=item.stock_quantity,
            reorder_level=item.reorder_level,
        )
        for item in low_stock
    ]
    low_stock_count = len(low_stock_items)

    # Recent orders with customer and vehicle info
    result = await db.execute(
        select(RepairOrder, Customer, Vehicle)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .where(RepairOrder.tenant_id == tenant_id)
        .order_by(RepairOrder.updated_at.desc())
        .limit(10)
    )
    recent_rows = result.all()
    recent_orders = [
        RecentOrder(
            id=str(order.id),
            order_number=order.order_number,
            status=order.status.value if hasattr(order.status, "value") else order.status,
            description=order.description,
            customer_name=f"{customer.first_name} {customer.last_name}",
            vehicle_info=f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip(),
            total_cost=str(get_effective_total(order)),
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        for order, customer, vehicle in recent_rows
    ]

    # --- Work Queue Lanes ---
    Mechanic = aliased(User)

    def _build_order(order, customer, vehicle, mechanic=None):
        mech_name = None
        if mechanic and mechanic.first_name:
            mech_name = f"{mechanic.first_name} {mechanic.last_name}"
        return RecentOrder(
            id=str(order.id),
            order_number=order.order_number,
            status=order.status.value if hasattr(order.status, "value") else order.status,
            description=order.description,
            customer_name=f"{customer.first_name} {customer.last_name}",
            vehicle_info=f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip(),
            total_cost=str(get_effective_total(order)),
            created_at=order.created_at,
            updated_at=order.updated_at,
            mechanic_name=mech_name,
            work_started_at=getattr(order, 'work_started_at', None),
        )

    # Lane 1: Needs Action (draft, pending_review, completed, or overdue quoted)
    needs_action_statuses = [
        RepairOrderStatus.DRAFT,
        RepairOrderStatus.QUOTED,
        RepairOrderStatus.DECLINED,  # Customer declined, needs revision
        RepairOrderStatus.PENDING_REVIEW,
        RepairOrderStatus.COMPLETED,
    ]
    result = await db.execute(
        select(RepairOrder, Customer, Vehicle, Mechanic)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .outerjoin(Mechanic, RepairOrder.assigned_mechanic_id == Mechanic.id)
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status.in_(needs_action_statuses),
            )
        )
        .order_by(RepairOrder.updated_at.asc())  # oldest first = most urgent
        .limit(10)
    )
    orders_needing_action = [_build_order(o, c, v, m) for o, c, v, m in result.all()]

    # Lane 2: On the Floor (approved, assigned, acknowledged, in_progress)
    on_floor_statuses = [
        RepairOrderStatus.APPROVED,
        RepairOrderStatus.ASSIGNED,
        RepairOrderStatus.ACKNOWLEDGED,
        RepairOrderStatus.IN_PROGRESS,
    ]
    result = await db.execute(
        select(RepairOrder, Customer, Vehicle, Mechanic)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .outerjoin(Mechanic, RepairOrder.assigned_mechanic_id == Mechanic.id)
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status.in_(on_floor_statuses),
            )
        )
        .order_by(RepairOrder.updated_at.desc())
        .limit(10)
    )
    orders_on_floor = [_build_order(o, c, v, m) for o, c, v, m in result.all()]

    # Lane 3: Ready to Close (invoiced)
    result = await db.execute(
        select(RepairOrder, Customer, Vehicle, Mechanic)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .outerjoin(Mechanic, RepairOrder.assigned_mechanic_id == Mechanic.id)
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.INVOICED,
            )
        )
        .order_by(RepairOrder.updated_at.desc())
        .limit(10)
    )
    orders_ready_to_close = [_build_order(o, c, v, m) for o, c, v, m in result.all()]

    # Mechanic-specific stats
    my_assigned_orders = 0
    my_in_progress = 0
    if current_user.role == UserRole.MECHANIC:
        result = await db.execute(
            select(func.count(RepairOrder.id)).where(
                and_(
                    RepairOrder.tenant_id == tenant_id,
                    RepairOrder.assigned_mechanic_id == current_user.id,
                )
            )
        )
        my_assigned_orders = result.scalar() or 0

        result = await db.execute(
            select(func.count(RepairOrder.id)).where(
                and_(
                    RepairOrder.tenant_id == tenant_id,
                    RepairOrder.assigned_mechanic_id == current_user.id,
                    RepairOrder.status == RepairOrderStatus.IN_PROGRESS,
                )
            )
        )
        my_in_progress = result.scalar() or 0

    # Phase 2: Revenue and profitability stats from completed payments
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # Today's revenue
    result = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            and_(
                Payment.tenant_id == tenant_id,
                Payment.status == PaymentStatus.COMPLETED,
                cast(Payment.created_at, Date) == today,
            )
        )
    )
    revenue_today = result.scalar() or Decimal("0.00")

    # This week's revenue
    result = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            and_(
                Payment.tenant_id == tenant_id,
                Payment.status == PaymentStatus.COMPLETED,
                cast(Payment.created_at, Date) >= week_start,
            )
        )
    )
    revenue_week = result.scalar() or Decimal("0.00")

    # This month's revenue
    result = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            and_(
                Payment.tenant_id == tenant_id,
                Payment.status == PaymentStatus.COMPLETED,
                cast(Payment.created_at, Date) >= month_start,
            )
        )
    )
    revenue_month = result.scalar() or Decimal("0.00")

    # Profitability metrics by period:
    # - Parts margin = billed parts total - parts cost basis
    # - Gross profit = labor/services revenue + parts margin
    # - PPI = gross profit per paid invoice
    calc_start = min(week_start, month_start)
    result = await db.execute(
        select(
            Payment.created_at,
            Payment.invoice_id,
            RepairOrder.id.label("order_id"),
            RepairOrder.total_parts_cost,
            RepairOrder.total_labor_cost,
            RepairOrder.internal_notes,
            Invoice.subtotal,
        )
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .join(RepairOrder, RepairOrder.id == Invoice.repair_order_id)
        .where(
            and_(
                Payment.tenant_id == tenant_id,
                Payment.status == PaymentStatus.COMPLETED,
                cast(Payment.created_at, Date) >= calc_start,
            )
        )
    )
    paid_rows = result.all()

    order_ids = [row.order_id for row in paid_rows]
    parts_cost_by_order: Dict = {}
    if order_ids:
        result = await db.execute(
            select(
                PartsUsage.repair_order_id,
                func.coalesce(
                    func.sum(
                        PartsUsage.quantity
                        * func.coalesce(PartsUsage.unit_cost, Inventory.cost, 0)
                    ),
                    0,
                ),
            )
            .outerjoin(Inventory, Inventory.id == PartsUsage.inventory_id)
            .where(PartsUsage.repair_order_id.in_(order_ids))
            .group_by(PartsUsage.repair_order_id)
        )
        parts_cost_by_order = {order_id: cost for order_id, cost in result.all()}

    def _bucket_for(payment_date: date) -> List[str]:
        buckets: List[str] = []
        if payment_date >= month_start:
            buckets.append("month")
        if payment_date >= week_start:
            buckets.append("week")
        if payment_date == today:
            buckets.append("today")
        return buckets

    profitability = {
        "today": {"parts_margin": Decimal("0.00"), "gross_profit": Decimal("0.00"), "invoices": set()},
        "week": {"parts_margin": Decimal("0.00"), "gross_profit": Decimal("0.00"), "invoices": set()},
        "month": {"parts_margin": Decimal("0.00"), "gross_profit": Decimal("0.00"), "invoices": set()},
    }

    for row in paid_rows:
        payment_date = row.created_at.date()
        parts_revenue = Decimal(str(row.total_parts_cost or 0))
        parts_cost = Decimal(str(parts_cost_by_order.get(row.order_id, 0) or 0))
        parts_margin = parts_revenue - parts_cost

        labor_revenue = get_order_labor_total(row)
        if labor_revenue <= Decimal("0.00"):
            subtotal = Decimal(str(row.subtotal or 0))
            labor_revenue = max(subtotal - parts_revenue, Decimal("0.00"))

        gross_profit = labor_revenue + parts_margin

        for bucket in _bucket_for(payment_date):
            profitability[bucket]["parts_margin"] += parts_margin
            profitability[bucket]["gross_profit"] += gross_profit
            profitability[bucket]["invoices"].add(row.invoice_id)

    def _ppi_for(bucket: str) -> Decimal:
        invoice_count = len(profitability[bucket]["invoices"])
        if invoice_count == 0:
            return Decimal("0.00")
        return (profitability[bucket]["gross_profit"] / Decimal(invoice_count)).quantize(Decimal("0.01"))

    # Total paid orders count
    result = await db.execute(
        select(func.count(RepairOrder.id)).where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.PAID,
            )
        )
    )
    total_paid_orders = result.scalar() or 0

    revenue = RevenueStats(
        today=str(revenue_today),
        this_week=str(revenue_week),
        this_month=str(revenue_month),
        total_paid_orders=total_paid_orders,
        today_parts_margin=str(profitability["today"]["parts_margin"]),
        this_week_parts_margin=str(profitability["week"]["parts_margin"]),
        this_month_parts_margin=str(profitability["month"]["parts_margin"]),
        today_gross_profit=str(profitability["today"]["gross_profit"]),
        this_week_gross_profit=str(profitability["week"]["gross_profit"]),
        this_month_gross_profit=str(profitability["month"]["gross_profit"]),
        today_ppi=str(_ppi_for("today")),
        this_week_ppi=str(_ppi_for("week")),
        this_month_ppi=str(_ppi_for("month")),
    )

    # Phase 2: Mechanic workload distribution
    mechanic_workload: List[MechanicWorkload] = []
    if current_user.role in [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]:
        # Get all mechanics for this tenant with their order counts
        result = await db.execute(
            select(
                User.id,
                User.first_name,
                User.last_name,
                User.email,
                func.count(RepairOrder.id).label("assigned_count"),
                func.count(
                    func.nullif(RepairOrder.status != RepairOrderStatus.IN_PROGRESS, True)
                ).label("in_progress_count"),
            )
            .outerjoin(RepairOrder, RepairOrder.assigned_mechanic_id == User.id)
            .where(
                and_(
                    User.tenant_id == tenant_id,
                    User.role == UserRole.MECHANIC,
                    User.is_active == True,
                )
            )
            .group_by(User.id, User.first_name, User.last_name, User.email)
        )
        mechanic_rows = result.all()
        
        for row in mechanic_rows:
            mechanic_workload.append(
                MechanicWorkload(
                    mechanic_id=str(row.id),
                    mechanic_name=f"{row.first_name} {row.last_name}",
                    assigned_count=row.assigned_count or 0,
                    in_progress_count=row.in_progress_count or 0,
                )
            )

    return DashboardStats(
        total_customers=total_customers,
        total_vehicles=total_vehicles,
        total_repair_orders=total_repair_orders,
        orders_by_status=orders_by_status,
        active_orders=active_orders,
        awaiting_approval=awaiting_approval,
        pending_invoices=pending_invoices,
        low_stock_count=low_stock_count,
        low_stock_items=low_stock_items,
        recent_orders=recent_orders,
        my_assigned_orders=my_assigned_orders,
        my_in_progress=my_in_progress,
        revenue=revenue,
        mechanic_workload=mechanic_workload,
        overdue_approvals=overdue_approvals,
        declined_quotes=declined_quotes,
        orders_needing_action=orders_needing_action,
        orders_on_floor=orders_on_floor,
        orders_ready_to_close=orders_ready_to_close,
    )
