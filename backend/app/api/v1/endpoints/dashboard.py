from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, cast, Date, or_, case
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime, timedelta, date, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import aliased, load_only
from app.core.dependencies import get_db, get_current_active_user
from app.core.vehicle_display import vehicle_display_label
from app.core.websocket import (
    broadcast_repair_order_update,
    broadcast_mechanic_attendance_update,
    broadcast_mechanic_break_update,
    broadcast_mechanic_timer_update,
)
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.quote import Quote
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentStatus
from app.db.models.mechanic_time import MechanicSessionType, MechanicTimeSession, MiscWorkCategory
from app.db.models.tenant import Tenant
from app.services.internal_fleet import fleet_display_name
from app.services.pricing import get_order_labor_total, get_order_subtotal
from app.services.mechanic_time_service import (
    ATTENTION_REASON_LABELS,
    clock_in,
    clock_out,
    compute_7day_trend,
    compute_attention_priority,
    compute_day_summary,
    compute_next_action_recommendation,
    delete_session,
    end_break,
    edit_session,
    fetch_tenant_and_mechanic,
    start_break,
    start_session,
    stop_active_session,
)

router = APIRouter()

# The operational dashboard is a triage surface, not a historical repair-order
# browser. Keeping each lane bounded prevents a long-lived tenant from sending
# and rendering its entire work history on every refresh.
ACTION_QUEUE_LANE_LIMIT = 50

# This is the same deliberately narrow tenant-wide repair-workspace boundary as
# the WebSocket channel. Fleet, driver, customer, platform, and unknown roles
# have narrower surfaces and must never inherit access to the shop workset.
DAILY_WORKSET_STAFF_ROLES = frozenset(
    {
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    }
)


def get_effective_total(order: RepairOrder) -> Decimal:
    return get_order_subtotal(order)


def is_pending_zelle_confirmation(invoice_status: InvoiceStatus, submitted_at: Optional[datetime]) -> bool:
    """A customer-submitted Zelle payment needs staff review until the invoice is paid or cleared."""
    return submitted_at is not None and invoice_status != InvoiceStatus.PAID


def require_manager(current_user: User) -> None:
    if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise HTTPException(status_code=403, detail="Shop owner/admin access required")


def require_daily_workset_staff(current_user: User) -> None:
    """Fail closed before loading the tenant-wide operational projection."""
    if (
        current_user.role not in DAILY_WORKSET_STAFF_ROLES
        or current_user.tenant_id is None
        or current_user.deleted_at is not None
    ):
        raise HTTPException(status_code=403, detail="Access denied")


class StatusCount(BaseModel):
    status: str
    count: int


class RecentOrder(BaseModel):
    id: str
    order_number: str
    status: str
    pending_zelle_confirmation: bool = False
    description: Optional[str]
    customer_name: str
    vehicle_info: str
    # vehicle_display_label only falls back to the unit number when make and
    # model are unknown, but the shop floor identifies a truck by its unit, so
    # it travels separately rather than being folded into that label.
    vehicle_unit_number: Optional[str] = None
    total_cost: str
    created_at: datetime
    updated_at: datetime
    mechanic_name: Optional[str] = None
    work_started_at: Optional[datetime] = None
    hold_reason: Optional[str] = None
    held_at: Optional[datetime] = None
    quote_sent: Optional[bool] = None


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


class InternalCostStats(BaseModel):
    today: str
    this_week: str
    this_month: str
    total_internal_invoices: int


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
    internal_costs: InternalCostStats
    mechanic_workload: List[MechanicWorkload]
    # Alerts: overdue approvals (quoted > 3 days)
    overdue_approvals: int = 0
    declined_quotes: int = 0
    # Work queue lanes
    orders_needing_action: List[RecentOrder] = []
    orders_on_floor: List[RecentOrder] = []
    orders_ready_to_close: List[RecentOrder] = []


class DashboardActionQueue(BaseModel):
    orders_needing_action: List[RecentOrder] = []
    orders_needing_action_has_more: bool = False
    orders_on_floor: List[RecentOrder] = []
    orders_on_floor_has_more: bool = False
    orders_ready_to_close: List[RecentOrder] = []
    orders_ready_to_close_has_more: bool = False


class DailyWorkbenchOrder(RecentOrder):
    """A compact queue record with only the paid timestamp added for Close Today."""

    paid_at: Optional[datetime] = None


class DailyWorkbenchQueue(BaseModel):
    items: List[DailyWorkbenchOrder] = Field(default_factory=list)
    has_more: bool = False


class DashboardDailyWorkbench(BaseModel):
    """Tenant-local active workday projection for the shared Repair Orders workspace."""

    timezone: str
    business_date: date
    next_reset_at: datetime
    needs_attention: DailyWorkbenchQueue = Field(default_factory=DailyWorkbenchQueue)
    on_floor: DailyWorkbenchQueue = Field(default_factory=DailyWorkbenchQueue)
    ready_to_close: DailyWorkbenchQueue = Field(default_factory=DailyWorkbenchQueue)
    closed_today: DailyWorkbenchQueue = Field(default_factory=DailyWorkbenchQueue)


class MechanicOption(BaseModel):
    mechanic_id: str
    mechanic_name: str


def _dashboard_order(
    order: RepairOrder,
    customer: Customer,
    vehicle: Vehicle,
    fleet_company_name: Optional[str],
    mechanic: Optional[User] = None,
    *,
    pending_zelle_confirmation: bool = False,
    quote_sent: Optional[bool] = None,
) -> RecentOrder:
    mechanic_name = None
    if mechanic and mechanic.first_name:
        mechanic_name = f"{mechanic.first_name} {mechanic.last_name}".strip()
    return RecentOrder(
        id=str(order.id),
        order_number=order.order_number,
        status=order.status.value if hasattr(order.status, "value") else order.status,
        pending_zelle_confirmation=pending_zelle_confirmation,
        description=order.description,
        customer_name=fleet_display_name(customer, fleet_company_name),
        vehicle_info=vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number),
        vehicle_unit_number=(vehicle.unit_number or None),
        total_cost=str(get_effective_total(order)),
        created_at=order.created_at,
        updated_at=order.updated_at,
        mechanic_name=mechanic_name,
        work_started_at=order.work_started_at,
        hold_reason=order.hold_reason,
        held_at=order.held_at,
        quote_sent=quote_sent,
    )


def _action_queue_load_options(mechanic):
    """Load only the columns rendered by an action-queue card."""
    return (
        load_only(
            RepairOrder.id,
            RepairOrder.order_number,
            RepairOrder.status,
            RepairOrder.description,
            RepairOrder.total_parts_cost,
            RepairOrder.total_labor_cost,
            RepairOrder.created_at,
            RepairOrder.updated_at,
            RepairOrder.work_started_at,
            RepairOrder.hold_reason,
            RepairOrder.held_at,
        ),
        load_only(
            Customer.id,
            Customer.first_name,
            Customer.last_name,
            Customer.is_internal_fleet,
        ),
        load_only(Vehicle.id, Vehicle.year, Vehicle.make, Vehicle.model, Vehicle.unit_number),
        load_only(mechanic.id, mechanic.first_name, mechanic.last_name),
    )


def _resolve_tenant_timezone(timezone_name: Optional[str]) -> tuple[str, ZoneInfo]:
    """Keep the daily boundary deterministic even for a malformed legacy tenant value."""
    configured_timezone = timezone_name or "America/New_York"
    try:
        return configured_timezone, ZoneInfo(configured_timezone)
    except ZoneInfoNotFoundError:
        return "America/New_York", ZoneInfo("America/New_York")


def _daily_workbench_queue(orders: List[RecentOrder], has_more: bool = False) -> DailyWorkbenchQueue:
    return DailyWorkbenchQueue(
        items=[DailyWorkbenchOrder(**order.model_dump()) for order in orders],
        has_more=has_more,
    )


async def _load_dashboard_action_queue(
    db: AsyncSession,
    tenant_id: UUID,
    fleet_company_name: Optional[str],
) -> DashboardActionQueue:
    """Load only the repair-order lanes used by the operational dashboard."""
    mechanic = aliased(User)
    new_order_float_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

    needs_action_priority = case(
        (
            and_(
                RepairOrder.status == RepairOrderStatus.DRAFT,
                RepairOrder.created_at >= new_order_float_cutoff,
            ),
            0,
        ),
        (RepairOrder.status == RepairOrderStatus.PENDING_REVIEW, 1),
        (RepairOrder.status == RepairOrderStatus.QUOTED, 2),
        (RepairOrder.status == RepairOrderStatus.DRAFT, 3),
        (RepairOrder.status == RepairOrderStatus.DECLINED, 4),
        else_=5,
    )
    quote_sent = (
        select(Quote.sent_to_customer)
        .where(Quote.repair_order_id == RepairOrder.id)
        .order_by(Quote.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    needs_action_result = await db.execute(
        select(RepairOrder, Customer, Vehicle, mechanic, quote_sent.label("quote_sent"))
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .outerjoin(mechanic, RepairOrder.assigned_mechanic_id == mechanic.id)
        .options(*_action_queue_load_options(mechanic))
        .where(
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.deleted_at.is_(None),
            RepairOrder.status.in_([
                RepairOrderStatus.DRAFT,
                RepairOrderStatus.QUOTED,
                RepairOrderStatus.DECLINED,
                RepairOrderStatus.PENDING_REVIEW,
            ]),
        )
        .order_by(
            needs_action_priority.asc(),
            RepairOrder.created_at.desc(),
            RepairOrder.updated_at.desc(),
        )
        .limit(ACTION_QUEUE_LANE_LIMIT + 1)
    )
    standard_needs_action = [
        _dashboard_order(order, customer, vehicle, fleet_company_name, assigned_mechanic, quote_sent=sent)
        for order, customer, vehicle, assigned_mechanic, sent in needs_action_result.all()
    ]

    pending_zelle_result = await db.execute(
        select(RepairOrder, Customer, Vehicle, mechanic)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .join(Invoice, Invoice.repair_order_id == RepairOrder.id)
        .outerjoin(mechanic, RepairOrder.assigned_mechanic_id == mechanic.id)
        .options(*_action_queue_load_options(mechanic))
        .where(
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.deleted_at.is_(None),
            Invoice.tenant_id == tenant_id,
            Invoice.zelle_pending_submitted_at.is_not(None),
            Invoice.status.not_in([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
        )
        .order_by(Invoice.zelle_pending_submitted_at.desc())
        .limit(ACTION_QUEUE_LANE_LIMIT + 1)
    )
    pending_zelle_orders = [
        _dashboard_order(order, customer, vehicle, fleet_company_name, assigned_mechanic, pending_zelle_confirmation=True)
        for order, customer, vehicle, assigned_mechanic in pending_zelle_result.all()
    ]
    pending_zelle_order_ids = {order.id for order in pending_zelle_orders}

    on_floor_result = await db.execute(
        select(RepairOrder, Customer, Vehicle, mechanic)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .outerjoin(mechanic, RepairOrder.assigned_mechanic_id == mechanic.id)
        .options(*_action_queue_load_options(mechanic))
        .where(
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.deleted_at.is_(None),
            RepairOrder.status.in_([
                RepairOrderStatus.APPROVED,
                RepairOrderStatus.ASSIGNED,
                RepairOrderStatus.ACKNOWLEDGED,
                RepairOrderStatus.IN_PROGRESS,
            ]),
        )
        .order_by(RepairOrder.updated_at.desc())
        .limit(ACTION_QUEUE_LANE_LIMIT + 1)
    )
    orders_on_floor = [
        _dashboard_order(order, customer, vehicle, fleet_company_name, assigned_mechanic)
        for order, customer, vehicle, assigned_mechanic in on_floor_result.all()
    ]

    pending_zelle = (
        select(Invoice.id)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.repair_order_id == RepairOrder.id,
            Invoice.zelle_pending_submitted_at.is_not(None),
            Invoice.status.not_in([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
        )
        .exists()
    )
    ready_priority = case(
        (RepairOrder.status == RepairOrderStatus.COMPLETED, 0),
        (RepairOrder.status == RepairOrderStatus.INVOICED, 1),
        else_=2,
    )
    ready_result = await db.execute(
        select(RepairOrder, Customer, Vehicle, mechanic)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .outerjoin(mechanic, RepairOrder.assigned_mechanic_id == mechanic.id)
        .options(*_action_queue_load_options(mechanic))
        .where(
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.deleted_at.is_(None),
            RepairOrder.status.in_([RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED]),
            or_(
                RepairOrder.source.is_(None),
                RepairOrder.source != "easy_truck_shop_import",
                RepairOrder.status != RepairOrderStatus.COMPLETED,
                RepairOrder.total_cost > 0,
            ),
            ~pending_zelle,
        )
        .order_by(ready_priority.asc(), RepairOrder.updated_at.desc())
        .limit(ACTION_QUEUE_LANE_LIMIT + 1)
    )
    orders_ready_to_close = [
        _dashboard_order(order, customer, vehicle, fleet_company_name, assigned_mechanic)
        for order, customer, vehicle, assigned_mechanic in ready_result.all()
    ]

    needs_action_orders = pending_zelle_orders + [
        order for order in standard_needs_action if order.id not in pending_zelle_order_ids
    ]

    return DashboardActionQueue(
        orders_needing_action=needs_action_orders[:ACTION_QUEUE_LANE_LIMIT],
        orders_needing_action_has_more=len(needs_action_orders) > ACTION_QUEUE_LANE_LIMIT,
        orders_on_floor=orders_on_floor[:ACTION_QUEUE_LANE_LIMIT],
        orders_on_floor_has_more=len(orders_on_floor) > ACTION_QUEUE_LANE_LIMIT,
        orders_ready_to_close=orders_ready_to_close[:ACTION_QUEUE_LANE_LIMIT],
        orders_ready_to_close_has_more=len(orders_ready_to_close) > ACTION_QUEUE_LANE_LIMIT,
    )


@router.get("/action-queue", response_model=DashboardActionQueue)
async def get_dashboard_action_queue(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not current_user.tenant_id:
        return DashboardActionQueue()

    fleet_company_name = await db.scalar(
        select(Tenant.fleet_company_name).where(Tenant.id == current_user.tenant_id)
    )
    return await _load_dashboard_action_queue(db, current_user.tenant_id, fleet_company_name)


@router.get("/daily-workset", response_model=DashboardDailyWorkbench)
async def get_dashboard_daily_workset(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the tenant's active local-day workset without changing the legacy action queue."""
    require_daily_workset_staff(current_user)

    configured_timezone = "America/New_York"
    fleet_company_name: Optional[str] = None
    tenant_result = await db.execute(
        select(
            Tenant.fleet_company_name,
            Tenant.timezone,
            Tenant.is_active,
            Tenant.deleted_at,
        ).where(Tenant.id == current_user.tenant_id)
    )
    tenant_row = tenant_result.one_or_none()
    if (
        tenant_row is None
        or tenant_row.is_active is not True
        or tenant_row.deleted_at is not None
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    fleet_company_name, configured_timezone, _, _ = tenant_row

    timezone_name, tenant_timezone = _resolve_tenant_timezone(configured_timezone)
    local_now = datetime.now(timezone.utc).astimezone(tenant_timezone)
    local_day_start = datetime.combine(local_now.date(), datetime.min.time(), tzinfo=tenant_timezone)
    next_reset_at = local_day_start + timedelta(days=1)

    action_queue = await _load_dashboard_action_queue(
        db,
        current_user.tenant_id,
        fleet_company_name,
    )
    mechanic = aliased(User)
    closed_today_result = await db.execute(
        select(RepairOrder, Customer, Vehicle, mechanic, Invoice.paid_at)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .join(Invoice, Invoice.repair_order_id == RepairOrder.id)
        .outerjoin(mechanic, RepairOrder.assigned_mechanic_id == mechanic.id)
        .options(*_action_queue_load_options(mechanic))
        .where(
            RepairOrder.tenant_id == current_user.tenant_id,
            RepairOrder.deleted_at.is_(None),
            Invoice.tenant_id == current_user.tenant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.is_not(None),
            Invoice.paid_at >= local_day_start.astimezone(timezone.utc),
            Invoice.paid_at < next_reset_at.astimezone(timezone.utc),
        )
        .order_by(Invoice.paid_at.desc(), RepairOrder.updated_at.desc())
        .limit(ACTION_QUEUE_LANE_LIMIT + 1)
    )
    closed_today_orders = [
        DailyWorkbenchOrder(
            **_dashboard_order(order, customer, vehicle, fleet_company_name, assigned_mechanic).model_dump(),
            paid_at=paid_at,
        )
        for order, customer, vehicle, assigned_mechanic, paid_at in closed_today_result.all()
    ]

    return DashboardDailyWorkbench(
        timezone=timezone_name,
        business_date=local_now.date(),
        next_reset_at=next_reset_at,
        needs_attention=_daily_workbench_queue(
            action_queue.orders_needing_action,
            action_queue.orders_needing_action_has_more,
        ),
        on_floor=_daily_workbench_queue(
            action_queue.orders_on_floor,
            action_queue.orders_on_floor_has_more,
        ),
        ready_to_close=_daily_workbench_queue(
            action_queue.orders_ready_to_close,
            action_queue.orders_ready_to_close_has_more,
        ),
        closed_today=DailyWorkbenchQueue(
            items=closed_today_orders[:ACTION_QUEUE_LANE_LIMIT],
            has_more=len(closed_today_orders) > ACTION_QUEUE_LANE_LIMIT,
        ),
    )


@router.get("/mechanics/options", response_model=List[MechanicOption])
async def get_mechanic_options(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not current_user.tenant_id:
        return []

    result = await db.execute(
        select(User.id, User.first_name, User.last_name)
        .where(
            User.tenant_id == current_user.tenant_id,
            User.role == UserRole.MECHANIC,
            User.is_active.is_(True),
        )
        .order_by(User.first_name, User.last_name)
    )
    return [
        MechanicOption(
            mechanic_id=str(mechanic_id),
            mechanic_name=f"{first_name} {last_name}".strip(),
        )
        for mechanic_id, first_name, last_name in result.all()
    ]


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
            internal_costs=InternalCostStats(today="0.00", this_week="0.00", this_month="0.00", total_internal_invoices=0),
            mechanic_workload=[],
            overdue_approvals=0,
            declined_quotes=0,
            orders_needing_action=[],
            orders_on_floor=[],
            orders_ready_to_close=[],
        )

    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    dashboard_totals = (
        await db.execute(
            select(
                select(Tenant.fleet_company_name)
                .where(Tenant.id == tenant_id)
                .scalar_subquery()
                .label("fleet_company_name"),
                select(func.count(Customer.id))
                .where(Customer.tenant_id == tenant_id)
                .scalar_subquery()
                .label("total_customers"),
                select(func.count(Vehicle.id))
                .where(Vehicle.tenant_id == tenant_id)
                .scalar_subquery()
                .label("total_vehicles"),
                select(func.count(RepairOrder.id))
                .where(
                    RepairOrder.tenant_id == tenant_id,
                    RepairOrder.deleted_at.is_(None),
                )
                .scalar_subquery()
                .label("total_repair_orders"),
                select(func.count(RepairOrder.id))
                .where(
                    RepairOrder.tenant_id == tenant_id,
                    RepairOrder.deleted_at.is_(None),
                    RepairOrder.status == RepairOrderStatus.QUOTED,
                    RepairOrder.updated_at < three_days_ago,
                )
                .scalar_subquery()
                .label("overdue_approvals"),
                select(func.count(RepairOrder.id))
                .where(
                    RepairOrder.tenant_id == tenant_id,
                    RepairOrder.deleted_at.is_(None),
                    RepairOrder.status == RepairOrderStatus.DECLINED,
                )
                .scalar_subquery()
                .label("declined_quotes"),
            )
        )
    ).one()
    fleet_company_name = dashboard_totals.fleet_company_name
    total_customers = dashboard_totals.total_customers or 0
    total_vehicles = dashboard_totals.total_vehicles or 0
    total_repair_orders = dashboard_totals.total_repair_orders or 0
    overdue_approvals = dashboard_totals.overdue_approvals or 0
    declined_quotes = dashboard_totals.declined_quotes or 0

    # Orders by status
    result = await db.execute(
        select(RepairOrder.status, func.count(RepairOrder.id))
        .where(RepairOrder.tenant_id == tenant_id, RepairOrder.deleted_at.is_(None))
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

    # Low stock items (stock_quantity <= reorder_level)
    result = await db.execute(
        select(Inventory)
        .where(
            and_(
                Inventory.tenant_id == tenant_id,
                Inventory.needs_restock(),
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
        .where(RepairOrder.tenant_id == tenant_id, RepairOrder.deleted_at.is_(None))
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
            customer_name=fleet_display_name(customer, fleet_company_name),
            vehicle_info=vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number),
            vehicle_unit_number=(vehicle.unit_number or None),
            total_cost=str(get_effective_total(order)),
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        for order, customer, vehicle in recent_rows
    ]

    # --- Work Queue Lanes ---
    Mechanic = aliased(User)

    def _build_order(order, customer, vehicle, mechanic=None, pending_zelle_confirmation: bool = False, quote_sent: Optional[bool] = None):
        mech_name = None
        if mechanic and mechanic.first_name:
            mech_name = f"{mechanic.first_name} {mechanic.last_name}"
        return RecentOrder(
            id=str(order.id),
            order_number=order.order_number,
            status=order.status.value if hasattr(order.status, "value") else order.status,
            pending_zelle_confirmation=pending_zelle_confirmation,
            description=order.description,
            customer_name=fleet_display_name(customer, fleet_company_name),
            vehicle_info=vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number),
            vehicle_unit_number=(vehicle.unit_number or None),
            total_cost=str(get_effective_total(order)),
            created_at=order.created_at,
            updated_at=order.updated_at,
            mechanic_name=mech_name,
            work_started_at=getattr(order, 'work_started_at', None),
            hold_reason=getattr(order, 'hold_reason', None),
            held_at=getattr(order, 'held_at', None),
            quote_sent=quote_sent,
        )

    # Lane 1: Needs Action (draft, pending_review, quoted, declined)
    needs_action_statuses = [
        RepairOrderStatus.DRAFT,
        RepairOrderStatus.QUOTED,
        RepairOrderStatus.DECLINED,  # Customer declined, needs revision
        RepairOrderStatus.PENDING_REVIEW,
    ]
    # Newly created full/lightning orders are drafts and should float to the top briefly.
    new_order_float_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    needs_action_priority = case(
        (
            and_(
                RepairOrder.status == RepairOrderStatus.DRAFT,
                RepairOrder.created_at >= new_order_float_cutoff,
            ),
            0,
        ),
        (RepairOrder.status == RepairOrderStatus.PENDING_REVIEW, 1),
        (RepairOrder.status == RepairOrderStatus.QUOTED, 2),
        (RepairOrder.status == RepairOrderStatus.DRAFT, 3),
        (RepairOrder.status == RepairOrderStatus.DECLINED, 4),
        else_=5,
    )
    result = await db.execute(
        select(RepairOrder, Customer, Vehicle, Mechanic)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .outerjoin(Mechanic, RepairOrder.assigned_mechanic_id == Mechanic.id)
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.deleted_at.is_(None),
                RepairOrder.status.in_(needs_action_statuses),
            )
        )
        .order_by(
            needs_action_priority.asc(),
            RepairOrder.created_at.desc(),
            RepairOrder.updated_at.desc(),
        )
    )
    needs_action_rows = result.all()
    needs_action_ids = [o.id for o, c, v, m in needs_action_rows]
    quote_sent_result = await db.execute(
        select(Quote.repair_order_id, Quote.sent_to_customer)
        .where(Quote.repair_order_id.in_(needs_action_ids))
        .order_by(Quote.revision.asc())
    ) if needs_action_ids else None
    quote_sent_map = {row[0]: row[1] for row in quote_sent_result.fetchall()} if quote_sent_result else {}
    standard_needs_action = [
        _build_order(o, c, v, m, quote_sent=quote_sent_map.get(o.id))
        for o, c, v, m in needs_action_rows
    ]

    # A customer marking a Zelle transfer as sent is a staff-review task, even
    # though its repair order remains invoiced. Surface it ahead of normal work.
    pending_zelle_result = await db.execute(
        select(RepairOrder, Customer, Vehicle, Mechanic)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .join(Invoice, Invoice.repair_order_id == RepairOrder.id)
        .outerjoin(Mechanic, RepairOrder.assigned_mechanic_id == Mechanic.id)
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.deleted_at.is_(None),
                Invoice.tenant_id == tenant_id,
                Invoice.zelle_pending_submitted_at.is_not(None),
                Invoice.status != InvoiceStatus.PAID,
                Invoice.status != InvoiceStatus.CANCELLED,
            )
        )
        .order_by(Invoice.zelle_pending_submitted_at.desc())
    )
    pending_zelle_orders = [
        _build_order(o, c, v, m, pending_zelle_confirmation=True)
        for o, c, v, m in pending_zelle_result.all()
    ]
    pending_zelle_order_ids = {order.id for order in pending_zelle_orders}
    orders_needing_action = (pending_zelle_orders + [
        order for order in standard_needs_action if order.id not in pending_zelle_order_ids
    ])

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
                RepairOrder.deleted_at.is_(None),
                RepairOrder.status.in_(on_floor_statuses),
            )
        )
        .order_by(RepairOrder.updated_at.desc())
    )
    orders_on_floor = [_build_order(o, c, v, m) for o, c, v, m in result.all()]

    # Lane 3: Ready to Close (completed = needs invoice sent; invoiced = awaiting payment)
    ready_to_close_priority = case(
        (RepairOrder.status == RepairOrderStatus.COMPLETED, 0),
        (RepairOrder.status == RepairOrderStatus.INVOICED, 1),
        else_=2,
    )
    result = await db.execute(
        select(RepairOrder, Customer, Vehicle, Mechanic)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .outerjoin(Mechanic, RepairOrder.assigned_mechanic_id == Mechanic.id)
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.deleted_at.is_(None),
                RepairOrder.status.in_([
                    RepairOrderStatus.COMPLETED,
                    RepairOrderStatus.INVOICED,
                ]),
                # ETS includes closed historical service records as completed
                # $0 orders without a local invoice. They are history, not work
                # that the shop still needs to invoice.
                or_(
                    RepairOrder.source.is_(None),
                    RepairOrder.source != "easy_truck_shop_import",
                    RepairOrder.status != RepairOrderStatus.COMPLETED,
                    RepairOrder.total_cost > 0,
                ),
            )
        )
        .order_by(ready_to_close_priority.asc(), RepairOrder.updated_at.desc())
    )
    ready_rows = result.all()
    ready_order_ids = [o.id for o, _, _, _ in ready_rows]
    pending_zelle_map: Dict = {}
    if ready_order_ids:
        pending_result = await db.execute(
            select(Invoice.repair_order_id, Invoice.status, Invoice.zelle_pending_submitted_at).where(
                and_(
                    Invoice.tenant_id == tenant_id,
                    Invoice.repair_order_id.in_(ready_order_ids),
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
            )
        )
        pending_zelle_map = {
            repair_order_id: is_pending_zelle_confirmation(status, zelle_pending_submitted_at)
            for repair_order_id, status, zelle_pending_submitted_at in pending_result.all()
        }

    orders_ready_to_close = [
        _build_order(
            o,
            c,
            v,
            m,
            pending_zelle_confirmation=pending_zelle_map.get(o.id, False),
        )
        for o, c, v, m in ready_rows
        if not pending_zelle_map.get(o.id, False)
    ]

    # Mechanic-specific stats
    my_assigned_orders = 0
    my_in_progress = 0
    if current_user.role == UserRole.MECHANIC:
        result = await db.execute(
            select(
                func.count(RepairOrder.id).label("assigned_count"),
                func.count(
                    case(
                        (RepairOrder.status == RepairOrderStatus.IN_PROGRESS, RepairOrder.id),
                        else_=None,
                    )
                ).label("in_progress_count"),
            ).where(
                and_(
                    RepairOrder.tenant_id == tenant_id,
                    RepairOrder.deleted_at.is_(None),
                    RepairOrder.assigned_mechanic_id == current_user.id,
                )
            )
        )
        mechanic_counts = result.one()
        my_assigned_orders = mechanic_counts.assigned_count or 0
        my_in_progress = mechanic_counts.in_progress_count or 0

    # Phase 2: Revenue and profitability stats from completed payments
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    revenue_totals = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (cast(Payment.created_at, Date) == today, Payment.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("today"),
                func.coalesce(
                    func.sum(
                        case(
                            (cast(Payment.created_at, Date) >= week_start, Payment.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("week"),
                func.coalesce(
                    func.sum(
                        case(
                            (cast(Payment.created_at, Date) >= month_start, Payment.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("month"),
                select(func.count(RepairOrder.id))
                .where(
                    RepairOrder.tenant_id == tenant_id,
                    RepairOrder.status == RepairOrderStatus.PAID,
                )
                .scalar_subquery()
                .label("total_paid_orders"),
            ).where(
                Payment.tenant_id == tenant_id,
                Payment.status == PaymentStatus.COMPLETED,
            )
        )
    ).one()
    revenue_today = revenue_totals.today or Decimal("0.00")
    revenue_week = revenue_totals.week or Decimal("0.00")
    revenue_month = revenue_totals.month or Decimal("0.00")
    total_paid_orders = revenue_totals.total_paid_orders or 0

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

    # Internal fleet cost stats: at-cost parts + internal labor rate for
    # company-owned trucks, from internal invoices (no customer payment).
    internal_totals = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (cast(Invoice.created_at, Date) == today, Invoice.total_amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("today"),
                func.coalesce(
                    func.sum(
                        case(
                            (cast(Invoice.created_at, Date) >= week_start, Invoice.total_amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("week"),
                func.coalesce(
                    func.sum(
                        case(
                            (cast(Invoice.created_at, Date) >= month_start, Invoice.total_amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("month"),
                func.count(Invoice.id).label("count"),
            ).where(
                Invoice.tenant_id == tenant_id,
                Invoice.is_internal.is_(True),
            )
        )
    ).one()
    internal_cost_today = internal_totals.today or Decimal("0.00")
    internal_cost_week = internal_totals.week or Decimal("0.00")
    internal_cost_month = internal_totals.month or Decimal("0.00")
    total_internal_invoices = internal_totals.count or 0

    internal_costs = InternalCostStats(
        today=str(internal_cost_today),
        this_week=str(internal_cost_week),
        this_month=str(internal_cost_month),
        total_internal_invoices=total_internal_invoices,
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
        internal_costs=internal_costs,
        mechanic_workload=mechanic_workload,
        overdue_approvals=overdue_approvals,
        declined_quotes=declined_quotes,
        orders_needing_action=orders_needing_action,
        orders_on_floor=orders_on_floor,
        orders_ready_to_close=orders_ready_to_close,
    )


class ManagerTimerStartRequest(BaseModel):
    session_type: str = Field(..., description="repair_order or misc")
    repair_order_id: Optional[UUID] = None
    misc_category: Optional[str] = None
    note: Optional[str] = None
    manager_reason: Optional[str] = None


class ManagerTimerStopRequest(BaseModel):
    manager_reason: Optional[str] = None


class ManagerClockActionRequest(BaseModel):
    manager_reason: Optional[str] = None
    note: Optional[str] = None


class ManagerClockInRequest(BaseModel):
    manager_reason: Optional[str] = None
    note: Optional[str] = None


class ManagerBreakActionRequest(BaseModel):
    manager_reason: Optional[str] = None
    note: Optional[str] = None


class SessionEditRequest(BaseModel):
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    note: Optional[str] = None
    misc_category: Optional[str] = None
    manager_reason: str


class SessionDeleteRequest(BaseModel):
    manager_reason: str


class TimerActionResponse(BaseModel):
    success: bool
    session_id: str
    attendance_session_id: Optional[str] = None
    break_session_id: Optional[str] = None
    auto_clocked_in: Optional[bool] = None
    auto_stopped_timer_session_id: Optional[str] = None
    auto_ended_break_session_id: Optional[str] = None
    message: str


class HeldOrderSummary(BaseModel):
    id: str
    order_number: str
    hold_reason: Optional[str] = None
    held_at: Optional[str] = None


class MechanicBoardItem(BaseModel):
    mechanic_id: str
    mechanic_name: str
    date: str
    timezone: str
    shift_start_local: str
    shift_end_local: str
    core_target_minutes: int
    tracked_minutes: int
    ro_minutes: int
    misc_minutes: int
    overtime_minutes: int
    utilization_percent: float
    efficiency_percent: Optional[float] = None
    book_hours: float
    actual_ro_hours: float
    active_session: Optional[dict] = None
    attendance_active: bool = False
    attendance_started_at: Optional[str] = None
    attendance_ended_at: Optional[str] = None
    break_active: bool = False
    break_started_at: Optional[str] = None
    attendance_minutes: int = 0
    break_minutes: int = 0
    idle_minutes: int = 0
    late_arrival_minutes: int = 0
    early_leave_minutes: int = 0
    flex_budget_minutes: int = 0
    flex_used_minutes: int = 0
    flex_remaining_minutes: int = 0
    flex_overrun_minutes: int = 0
    core_gap_minutes: int = 0
    core_countdown_elapsed_minutes: int = 0
    core_countdown_remaining_minutes: int = 0
    tracked_vs_attendance_gap_minutes: int = 0
    work_coverage_percent: Optional[float] = None
    assigned_ready_orders_count: int = 0
    untimed_in_progress_orders_count: int = 0
    held_orders_count: int = 0
    held_orders: List[HeldOrderSummary] = []
    recommended_order_id: Optional[str] = None
    recommended_order_number: Optional[str] = None
    suggested_next_action: str = "start_misc"
    attention_priority: str = "green"
    attention_reasons: List[str] = []
    trend_7_days: List[dict] = []


class TeamMechanicsBoardResponse(BaseModel):
    date: str
    timezone: str
    team_core_target_minutes: int
    team_tracked_minutes: int
    team_overtime_minutes: int
    team_utilization_percent: float
    mechanics: List[MechanicBoardItem]


class MechanicBoardDetailResponse(BaseModel):
    mechanic: MechanicBoardItem
    today_sessions: List[dict]


@router.get("/mechanics/board", response_model=TeamMechanicsBoardResponse)
async def get_team_mechanics_board(
    date_value: Optional[date] = Query(None, alias="date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.MECHANIC,
                User.is_active.is_(True),
            )
        )
    )
    mechanics = result.scalars().all()
    if not mechanics:
        return TeamMechanicsBoardResponse(
            date=(date_value or date.today()).isoformat(),
            timezone="America/New_York",
            team_core_target_minutes=0,
            team_tracked_minutes=0,
            team_overtime_minutes=0,
            team_utilization_percent=0.0,
            mechanics=[],
        )

    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    mechanics_payload: List[MechanicBoardItem] = []
    team_core = 0
    team_tracked = 0
    team_overtime = 0
    tenant_orders_result = await db.execute(
        select(RepairOrder).where(
            and_(
                RepairOrder.tenant_id == tenant.id,
                RepairOrder.deleted_at.is_(None),
                RepairOrder.assigned_mechanic_id.is_not(None),
                RepairOrder.status.in_(
                    [
                        RepairOrderStatus.ASSIGNED,
                        RepairOrderStatus.ACKNOWLEDGED,
                        RepairOrderStatus.IN_PROGRESS,
                    ]
                ),
            )
        )
    )
    tenant_active_orders = tenant_orders_result.scalars().all()
    orders_by_mechanic: Dict[str, List[RepairOrder]] = {}
    for order in tenant_active_orders:
        if not order.assigned_mechanic_id:
            continue
        mechanic_key = str(order.assigned_mechanic_id)
        orders_by_mechanic.setdefault(mechanic_key, []).append(order)

    for mechanic in mechanics:
        summary = await compute_day_summary(
            db,
            tenant=tenant,
            mechanic=mechanic,
            target_date=date_value,
        )
        recommendation = await compute_next_action_recommendation(
            db,
            tenant_id=tenant.id,
            mechanic_id=mechanic.id,
            attendance_active=bool(summary.get("attendance_active")),
            break_active=bool(summary.get("break_active")),
            active_session=summary.get("active_session"),
            core_countdown_remaining_minutes=int(summary.get("core_countdown_remaining_minutes") or 0),
            prefetched_orders=orders_by_mechanic.get(str(mechanic.id), []),
        )
        attention = compute_attention_priority(summary=summary, recommendation=recommendation)
        mechanics_payload.append(
            MechanicBoardItem(
                mechanic_id=str(mechanic.id),
                mechanic_name=f"{mechanic.first_name} {mechanic.last_name}".strip(),
                # Historical trends are rendered only by the per-mechanic
                # detail page. Computing them here multiplies the day-summary
                # queries by seven for every mechanic on the team board.
                trend_7_days=[],
                **summary,
                **recommendation,
                **attention,
            )
        )
        team_core += summary["core_target_minutes"]
        team_tracked += summary["tracked_minutes"]
        team_overtime += summary["overtime_minutes"]

    team_utilization = 0.0
    if team_core > 0:
        team_utilization = min((team_tracked / team_core) * 100.0, 100.0)

    return TeamMechanicsBoardResponse(
        date=mechanics_payload[0].date,
        timezone=mechanics_payload[0].timezone,
        team_core_target_minutes=team_core,
        team_tracked_minutes=team_tracked,
        team_overtime_minutes=team_overtime,
        team_utilization_percent=round(team_utilization, 2),
        mechanics=mechanics_payload,
    )


@router.get("/mechanics/{mechanic_id}/board", response_model=MechanicBoardDetailResponse)
async def get_mechanic_board_detail(
    mechanic_id: UUID,
    date_value: Optional[date] = Query(None, alias="date"),
    trend_end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=mechanic_id,
    )
    summary = await compute_day_summary(
        db,
        tenant=tenant,
        mechanic=mechanic,
        target_date=date_value,
    )
    recommendation = await compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=bool(summary.get("attendance_active")),
        break_active=bool(summary.get("break_active")),
        active_session=summary.get("active_session"),
        core_countdown_remaining_minutes=int(summary.get("core_countdown_remaining_minutes") or 0),
    )
    attention = compute_attention_priority(summary=summary, recommendation=recommendation)
    trend = await compute_7day_trend(
        db,
        tenant=tenant,
        mechanic=mechanic,
        end_date=trend_end_date or date_value,
    )
    item = MechanicBoardItem(
        mechanic_id=str(mechanic.id),
        mechanic_name=f"{mechanic.first_name} {mechanic.last_name}".strip(),
        trend_7_days=trend,
        **summary,
        **recommendation,
        **attention,
    )

    tz = ZoneInfo(tenant.timezone or "America/New_York")
    day_local = datetime.combine(date.fromisoformat(item.date), datetime.min.time(), tzinfo=tz)
    day_start_utc = day_local.astimezone(timezone.utc)
    day_end_utc = (day_local + timedelta(days=1)).astimezone(timezone.utc)
    sessions_result = await db.execute(
        select(MechanicTimeSession).where(
            and_(
                MechanicTimeSession.tenant_id == tenant.id,
                MechanicTimeSession.mechanic_id == mechanic.id,
                MechanicTimeSession.deleted_at.is_(None),
                MechanicTimeSession.started_at < day_end_utc,
                or_(MechanicTimeSession.ended_at.is_(None), MechanicTimeSession.ended_at > day_start_utc),
            )
        ).order_by(MechanicTimeSession.started_at.desc())
    )
    sessions = sessions_result.scalars().all()
    rows = [
        {
            "id": str(s.id),
            "session_type": s.session_type.value if hasattr(s.session_type, "value") else s.session_type,
            "repair_order_id": str(s.repair_order_id) if s.repair_order_id else None,
            "misc_category": s.misc_category.value if getattr(s, "misc_category", None) else None,
            "note": s.note,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "stop_reason": s.stop_reason,
            "timezone": str(tz),
        }
        for s in sessions
    ]
    return MechanicBoardDetailResponse(mechanic=item, today_sessions=rows)


@router.post("/mechanics/{mechanic_id}/timer/start", response_model=TimerActionResponse)
async def manager_start_mechanic_timer(
    mechanic_id: UUID,
    body: ManagerTimerStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    if body.session_type not in (MechanicSessionType.REPAIR_ORDER.value, MechanicSessionType.MISC.value):
        raise HTTPException(status_code=400, detail="Invalid session_type")
    if body.session_type == MechanicSessionType.REPAIR_ORDER.value and not body.repair_order_id:
        raise HTTPException(status_code=400, detail="repair_order_id is required for repair_order session")
    if body.session_type == MechanicSessionType.MISC.value:
        if body.misc_category not in [m.value for m in MiscWorkCategory]:
            raise HTTPException(status_code=400, detail="Invalid misc_category")

    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=mechanic_id,
    )
    repair_order_uuid = body.repair_order_id
    if repair_order_uuid:
        ro_result = await db.execute(
            select(RepairOrder).where(
                and_(
                    RepairOrder.id == repair_order_uuid,
                    RepairOrder.tenant_id == current_user.tenant_id,
                    RepairOrder.deleted_at.is_(None),
                )
            )
        )
        order = ro_result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Repair order not found")

    session, auto_clocked_in, attendance_session_id, auto_held_ro = await start_session(
        db,
        tenant=tenant,
        mechanic=mechanic,
        actor_user=current_user,
        session_type=body.session_type,
        repair_order_id=repair_order_uuid,
        misc_category=body.misc_category,
        note=body.note,
        manager_reason=body.manager_reason,
        stop_previous_reason="manager_control",
    )
    await db.commit()
    await db.refresh(session)
    # Broadcast auto-held RO if one was held
    if auto_held_ro:
        await broadcast_repair_order_update(
            tenant_id=str(auto_held_ro.tenant_id),
            customer_id=str(auto_held_ro.customer_id),
            order_id=str(auto_held_ro.id),
            order_number=auto_held_ro.order_number,
            status=auto_held_ro.status.value,
            updated_at=auto_held_ro.updated_at.isoformat() if auto_held_ro.updated_at else None,
            hold_reason=auto_held_ro.hold_reason,
            held_at=auto_held_ro.held_at.isoformat() if auto_held_ro.held_at else None,
            send_to_customer=False,
        )
    await broadcast_mechanic_timer_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(mechanic.id),
        session_id=str(session.id),
        action="manager_start",
    )
    if auto_clocked_in:
        await broadcast_mechanic_attendance_update(
            tenant_id=str(current_user.tenant_id),
            mechanic_id=str(mechanic.id),
            attendance_session_id=attendance_session_id,
            action="auto_clock_in",
        )
    return TimerActionResponse(
        success=True,
        session_id=str(session.id),
        attendance_session_id=attendance_session_id if auto_clocked_in else None,
        auto_clocked_in=auto_clocked_in,
        message="Timer started",
    )


@router.post("/mechanics/{mechanic_id}/timer/stop", response_model=TimerActionResponse)
async def manager_stop_mechanic_timer(
    mechanic_id: UUID,
    body: ManagerTimerStopRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    _, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=mechanic_id,
    )
    session = await stop_active_session(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=mechanic.id,
        actor_user=current_user,
        stop_reason="manager_control",
        manager_reason=body.manager_reason,
    )
    if not session:
        raise HTTPException(status_code=400, detail="No active timer to stop")
    await db.commit()
    await broadcast_mechanic_timer_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(mechanic.id),
        session_id=str(session.id),
        action="manager_stop",
    )
    return TimerActionResponse(success=True, session_id=str(session.id), message="Timer stopped")


@router.post("/mechanics/{mechanic_id}/attendance/clock-in", response_model=TimerActionResponse)
async def manager_clock_in_mechanic(
    mechanic_id: UUID,
    body: ManagerClockInRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=mechanic_id,
    )
    try:
        attendance = await clock_in(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            note=body.note,
            manager_reason=body.manager_reason,
            start_source="manager_clock_in",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    await broadcast_mechanic_attendance_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(mechanic.id),
        attendance_session_id=str(attendance.id),
        action="manager_clock_in",
    )
    return TimerActionResponse(
        success=True,
        session_id=str(attendance.id),
        attendance_session_id=str(attendance.id),
        message="Mechanic clocked in",
    )


@router.post("/mechanics/{mechanic_id}/attendance/clock-out", response_model=TimerActionResponse)
async def manager_clock_out_mechanic(
    mechanic_id: UUID,
    body: ManagerClockActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=mechanic_id,
    )
    try:
        result = await clock_out(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            note=body.note,
            manager_reason=body.manager_reason,
            end_source="manager_clock_out",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    await broadcast_mechanic_attendance_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(mechanic.id),
        attendance_session_id=str(result.attendance_session.id),
        action="manager_clock_out",
    )
    if result.ended_break_session:
        await broadcast_mechanic_break_update(
            tenant_id=str(current_user.tenant_id),
            mechanic_id=str(mechanic.id),
            break_session_id=str(result.ended_break_session.id),
            action="manager_break_end",
        )
    if result.stopped_timer_session:
        await broadcast_mechanic_timer_update(
            tenant_id=str(current_user.tenant_id),
            mechanic_id=str(mechanic.id),
            session_id=str(result.stopped_timer_session.id),
            action="manager_stop_from_clock_out",
        )
    return TimerActionResponse(
        success=True,
        session_id=str(result.attendance_session.id),
        attendance_session_id=str(result.attendance_session.id),
        auto_stopped_timer_session_id=str(result.stopped_timer_session.id) if result.stopped_timer_session else None,
        auto_ended_break_session_id=str(result.ended_break_session.id) if result.ended_break_session else None,
        message="Mechanic clocked out",
    )


@router.post("/mechanics/{mechanic_id}/break/start", response_model=TimerActionResponse)
async def manager_start_mechanic_break(
    mechanic_id: UUID,
    body: ManagerBreakActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=mechanic_id,
    )
    try:
        result = await start_break(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            note=body.note,
            manager_reason=body.manager_reason,
            start_source="manager_break_start",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    await broadcast_mechanic_break_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(mechanic.id),
        break_session_id=str(result.break_session.id),
        action="manager_break_start",
    )
    if result.stopped_timer_session:
        await broadcast_mechanic_timer_update(
            tenant_id=str(current_user.tenant_id),
            mechanic_id=str(mechanic.id),
            session_id=str(result.stopped_timer_session.id),
            action="manager_stop_from_break_start",
        )
    return TimerActionResponse(
        success=True,
        session_id=str(result.break_session.id),
        break_session_id=str(result.break_session.id),
        auto_stopped_timer_session_id=str(result.stopped_timer_session.id) if result.stopped_timer_session else None,
        message="Break started",
    )


@router.post("/mechanics/{mechanic_id}/break/end", response_model=TimerActionResponse)
async def manager_end_mechanic_break(
    mechanic_id: UUID,
    body: ManagerBreakActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=mechanic_id,
    )
    try:
        break_session = await end_break(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            manager_reason=body.manager_reason,
            note=body.note,
            end_source="manager_break_end",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    await broadcast_mechanic_break_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(mechanic.id),
        break_session_id=str(break_session.id),
        action="manager_break_end",
    )
    return TimerActionResponse(
        success=True,
        session_id=str(break_session.id),
        break_session_id=str(break_session.id),
        message="Break ended",
    )


@router.patch("/mechanics/time-sessions/{session_id}", response_model=TimerActionResponse)
async def manager_edit_time_session(
    session_id: UUID,
    body: SessionEditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    if not body.manager_reason.strip():
        raise HTTPException(status_code=400, detail="manager_reason is required")

    session_result = await db.execute(
        select(MechanicTimeSession).where(
            and_(
                MechanicTimeSession.id == session_id,
                MechanicTimeSession.tenant_id == current_user.tenant_id,
                MechanicTimeSession.deleted_at.is_(None),
            )
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Time session not found")
    try:
        await edit_session(
            db,
            session=session,
            actor_user=current_user,
            started_at=body.started_at,
            ended_at=body.ended_at,
            note=body.note,
            misc_category=body.misc_category,
            manager_reason=body.manager_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    await broadcast_mechanic_timer_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(session.mechanic_id),
        session_id=str(session.id),
        action="manager_edit",
    )
    return TimerActionResponse(success=True, session_id=str(session.id), message="Time session updated")


@router.post("/mechanics/time-sessions/{session_id}/delete", response_model=TimerActionResponse)
async def manager_delete_time_session(
    session_id: UUID,
    body: SessionDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_manager(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    if not body.manager_reason.strip():
        raise HTTPException(status_code=400, detail="manager_reason is required")

    session_result = await db.execute(
        select(MechanicTimeSession).where(
            and_(
                MechanicTimeSession.id == session_id,
                MechanicTimeSession.tenant_id == current_user.tenant_id,
                MechanicTimeSession.deleted_at.is_(None),
            )
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Time session not found")
    await delete_session(
        db,
        session=session,
        actor_user=current_user,
        manager_reason=body.manager_reason,
    )
    await db.commit()
    await broadcast_mechanic_timer_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(session.mechanic_id),
        session_id=str(session.id),
        action="manager_delete",
    )
    return TimerActionResponse(success=True, session_id=str(session.id), message="Time session deleted")
