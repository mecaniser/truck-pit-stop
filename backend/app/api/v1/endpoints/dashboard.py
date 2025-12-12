from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, cast, Date
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta, date
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.inventory import Inventory
from app.db.models.payment import Payment, PaymentStatus

router = APIRouter()


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
            total_cost=str(order.total_cost),
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        for order, customer, vehicle in recent_rows
    ]

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

    # Phase 2: Revenue stats from completed payments
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
    )

    # Phase 2: Mechanic workload distribution
    mechanic_workload: List[MechanicWorkload] = []
    if current_user.role in [UserRole.GARAGE_ADMIN, UserRole.SUPER_ADMIN]:
        # Get all mechanics for this tenant with their order counts
        result = await db.execute(
            select(
                User.id,
                User.full_name,
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
            .group_by(User.id, User.full_name, User.email)
        )
        mechanic_rows = result.all()
        
        for row in mechanic_rows:
            mechanic_workload.append(
                MechanicWorkload(
                    mechanic_id=str(row.id),
                    mechanic_name=row.full_name or row.email,
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
    )
