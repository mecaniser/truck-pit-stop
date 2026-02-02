"""
Super Admin endpoints for platform management.
Only accessible by users with SUPER_ADMIN role.
"""
from typing import List
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.core.dependencies import get_db, get_current_active_user
from app.core.security import get_password_hash
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantWithOwnerResponse

router = APIRouter()


def require_super_admin():
    """Dependency to ensure only SUPER_ADMIN can access these endpoints"""
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin access required",
            )
        return current_user
    return role_checker


@router.get("/tenants", response_model=List[TenantWithOwnerResponse])
async def list_all_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    active_only: bool = Query(False, description="Filter to active tenants only"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    List all tenants/garages in the platform.
    Only accessible by SUPER_ADMIN.
    """
    query = select(Tenant)
    
    if active_only:
        query = query.where(Tenant.is_active == True)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    tenants = result.scalars().all()
    
    # Enrich with owner information
    response_data = []
    for tenant in tenants:
        tenant_data = TenantWithOwnerResponse.model_validate(tenant)
        
        # Get owner details if owner_id exists
        if tenant.owner_id:
            owner_result = await db.execute(
                select(User).where(User.id == tenant.owner_id)
            )
            owner = owner_result.scalar_one_or_none()
            if owner:
                tenant_data.owner_email = owner.email
                tenant_data.owner_name = f"{owner.first_name} {owner.last_name}"
                tenant_data.owner_phone = owner.phone
        
        response_data.append(tenant_data)
    
    return response_data


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Create a new tenant/garage with an owner account.
    Only accessible by SUPER_ADMIN.
    """
    # Check if slug already exists
    result = await db.execute(
        select(Tenant).where(Tenant.slug == tenant_data.slug)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A garage with this slug already exists",
        )
    
    # Check if owner email already exists
    result = await db.execute(
        select(User).where(User.email == tenant_data.owner_email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists",
        )
    
    # Create tenant first (without owner_id)
    tenant = Tenant(
        id=uuid4(),
        name=tenant_data.name,
        slug=tenant_data.slug,
        address=tenant_data.address,
        phone=tenant_data.phone,
        email=tenant_data.email,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()
    
    # Create owner user account
    owner = User(
        id=uuid4(),
        email=tenant_data.owner_email,
        hashed_password=get_password_hash(tenant_data.owner_password),
        first_name=tenant_data.owner_first_name,
        last_name=tenant_data.owner_last_name,
        phone=tenant_data.owner_phone,
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db.add(owner)
    await db.flush()
    
    # Update tenant with owner_id
    tenant.owner_id = owner.id
    
    await db.commit()
    await db.refresh(tenant)
    
    return TenantResponse.model_validate(tenant)


@router.get("/tenants/{tenant_id}", response_model=TenantWithOwnerResponse)
async def get_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get detailed information about a specific tenant.
    Only accessible by SUPER_ADMIN.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    tenant_data = TenantWithOwnerResponse.model_validate(tenant)
    
    # Get owner details
    if tenant.owner_id:
        owner_result = await db.execute(
            select(User).where(User.id == tenant.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        if owner:
            tenant_data.owner_email = owner.email
            tenant_data.owner_name = f"{owner.first_name} {owner.last_name}"
            tenant_data.owner_phone = owner.phone
    
    return tenant_data


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    tenant_data: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Update tenant information.
    Only accessible by SUPER_ADMIN.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Update fields
    update_data = tenant_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)
    
    await db.commit()
    await db.refresh(tenant)
    
    return TenantResponse.model_validate(tenant)


@router.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Deactivate a tenant (soft delete).
    Only accessible by SUPER_ADMIN.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    tenant.is_active = False
    await db.commit()


@router.get("/platform/stats")
async def get_platform_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get platform-wide statistics.
    Only accessible by SUPER_ADMIN.
    """
    # Count active tenants
    active_tenants_result = await db.execute(
        select(func.count(Tenant.id)).where(Tenant.is_active == True)
    )
    active_tenants = active_tenants_result.scalar() or 0
    
    # Count total tenants
    total_tenants_result = await db.execute(
        select(func.count(Tenant.id))
    )
    total_tenants = total_tenants_result.scalar() or 0
    
    # Count total users by role
    users_by_role_result = await db.execute(
        select(User.role, func.count(User.id))
        .group_by(User.role)
    )
    users_by_role = {role: count for role, count in users_by_role_result.all()}
    
    # Count total customers
    total_customers_result = await db.execute(
        select(func.count(Customer.id))
    )
    total_customers = total_customers_result.scalar() or 0
    
    # Count repair orders by status
    ro_by_status_result = await db.execute(
        select(RepairOrder.status, func.count(RepairOrder.id))
        .group_by(RepairOrder.status)
    )
    repair_orders_by_status = {status.value: count for status, count in ro_by_status_result.all()}
    
    # Get total revenue (paid repair orders)
    total_revenue_result = await db.execute(
        select(func.sum(RepairOrder.total_cost))
        .where(RepairOrder.status == RepairOrderStatus.PAID)
    )
    total_revenue = total_revenue_result.scalar() or 0
    
    return {
        "tenants": {
            "total": total_tenants,
            "active": active_tenants,
            "inactive": total_tenants - active_tenants,
        },
        "users": {
            "by_role": users_by_role,
            "total": sum(users_by_role.values()),
        },
        "customers": {
            "total": total_customers,
        },
        "repair_orders": {
            "by_status": repair_orders_by_status,
            "total": sum(repair_orders_by_status.values()),
        },
        "revenue": {
            "total": float(total_revenue),
        }
    }


@router.get("/tenants/{tenant_id}/stats")
async def get_tenant_stats(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get comprehensive statistics for a specific tenant with time-series data.
    Only accessible by SUPER_ADMIN.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func, extract, case
    
    # Verify tenant exists
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
    
    # Count users by role
    users_by_role_result = await db.execute(
        select(User.role, func.count(User.id))
        .where(User.tenant_id == tenant_id)
        .group_by(User.role)
    )
    users_by_role = {role.value: count for role, count in users_by_role_result.all()}
    
    # Count customers (total and new this month)
    total_customers_result = await db.execute(
        select(func.count(Customer.id))
        .where(Customer.tenant_id == tenant_id)
    )
    total_customers = total_customers_result.scalar() or 0
    
    new_customers_result = await db.execute(
        select(func.count(Customer.id))
        .where(
            and_(
                Customer.tenant_id == tenant_id,
                Customer.created_at >= this_month_start
            )
        )
    )
    new_customers_this_month = new_customers_result.scalar() or 0
    
    # Repair orders by status
    ro_by_status_result = await db.execute(
        select(RepairOrder.status, func.count(RepairOrder.id))
        .where(RepairOrder.tenant_id == tenant_id)
        .group_by(RepairOrder.status)
    )
    repair_orders_by_status = {status.value: count for status, count in ro_by_status_result.all()}
    
    # Revenue metrics
    total_revenue_result = await db.execute(
        select(func.sum(RepairOrder.total_cost))
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.PAID
            )
        )
    )
    total_revenue = total_revenue_result.scalar() or 0
    
    # This month revenue
    this_month_revenue_result = await db.execute(
        select(func.sum(RepairOrder.total_cost))
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.PAID,
                RepairOrder.updated_at >= this_month_start
            )
        )
    )
    this_month_revenue = this_month_revenue_result.scalar() or 0
    
    # Last month revenue
    last_month_revenue_result = await db.execute(
        select(func.sum(RepairOrder.total_cost))
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.PAID,
                RepairOrder.updated_at >= last_month_start,
                RepairOrder.updated_at < this_month_start
            )
        )
    )
    last_month_revenue = last_month_revenue_result.scalar() or 0
    
    # Average order value
    avg_order_value_result = await db.execute(
        select(func.avg(RepairOrder.total_cost))
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.PAID
            )
        )
    )
    avg_order_value = avg_order_value_result.scalar() or 0
    
    # Last 30 days daily revenue
    daily_revenue_result = await db.execute(
        select(
            func.date(RepairOrder.updated_at).label('date'),
            func.sum(RepairOrder.total_cost).label('revenue')
        )
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.PAID,
                RepairOrder.updated_at >= thirty_days_ago
            )
        )
        .group_by(func.date(RepairOrder.updated_at))
        .order_by(func.date(RepairOrder.updated_at))
    )
    daily_revenue = [
        {"date": str(date), "revenue": float(revenue)}
        for date, revenue in daily_revenue_result.all()
    ]
    
    # Last 30 days daily order count
    daily_orders_result = await db.execute(
        select(
            func.date(RepairOrder.created_at).label('date'),
            func.count(RepairOrder.id).label('count')
        )
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.created_at >= thirty_days_ago
            )
        )
        .group_by(func.date(RepairOrder.created_at))
        .order_by(func.date(RepairOrder.created_at))
    )
    daily_orders = [
        {"date": str(date), "count": count}
        for date, count in daily_orders_result.all()
    ]
    
    # Conversion rate (quoted -> paid)
    quoted_count_result = await db.execute(
        select(func.count(RepairOrder.id))
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status.in_([RepairOrderStatus.QUOTED, RepairOrderStatus.APPROVED, RepairOrderStatus.IN_PROGRESS, RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED, RepairOrderStatus.PAID])
            )
        )
    )
    quoted_count = quoted_count_result.scalar() or 0
    
    paid_count_result = await db.execute(
        select(func.count(RepairOrder.id))
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.status == RepairOrderStatus.PAID
            )
        )
    )
    paid_count = paid_count_result.scalar() or 0
    
    conversion_rate = (paid_count / quoted_count * 100) if quoted_count > 0 else 0
    
    return {
        "tenant_id": str(tenant_id),
        "tenant_name": tenant.name,
        "is_active": tenant.is_active,
        "users": {
            "by_role": users_by_role,
            "total": sum(users_by_role.values()),
        },
        "customers": {
            "total": total_customers,
            "new_this_month": new_customers_this_month,
        },
        "repair_orders": {
            "by_status": repair_orders_by_status,
            "total": sum(repair_orders_by_status.values()),
        },
        "revenue": {
            "total": float(total_revenue),
            "this_month": float(this_month_revenue),
            "last_month": float(last_month_revenue),
            "average_order_value": float(avg_order_value),
            "daily_trend": daily_revenue,
        },
        "performance": {
            "conversion_rate": round(conversion_rate, 2),
            "orders_per_customer": round(sum(repair_orders_by_status.values()) / total_customers, 2) if total_customers > 0 else 0,
        },
        "trends": {
            "daily_orders": daily_orders,
            "revenue_growth": round(((this_month_revenue - last_month_revenue) / last_month_revenue * 100), 2) if last_month_revenue > 0 else 0,
        }
    }
