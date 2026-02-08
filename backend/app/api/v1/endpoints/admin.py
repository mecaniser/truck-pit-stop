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
from app.core.password_policy import validate_password
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
    # Validate owner password complexity
    validate_password(tenant_data.owner_password)
    
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
    # Admin-created tenants are pre-approved and active
    tenant = Tenant(
        id=uuid4(),
        name=tenant_data.name,
        slug=tenant_data.slug,
        address=tenant_data.address,
        phone=tenant_data.phone,
        email=tenant_data.email,
        is_active=True,
        enrollment_status="approved",  # Admin-created = pre-approved
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


# ============================================================================
# Garage Owner Settings (Zelle, etc.)
# ============================================================================

from pydantic import BaseModel
from typing import Optional


class ZelleSettingsRequest(BaseModel):
    zelle_email: Optional[str] = None
    zelle_phone: Optional[str] = None


class ZelleSettingsResponse(BaseModel):
    zelle_email: Optional[str] = None
    zelle_phone: Optional[str] = None
    zelle_qr_image: Optional[str] = None  # Base64 encoded image


class ZelleQrImageRequest(BaseModel):
    zelle_qr_image: Optional[str] = None  # Base64 encoded image, null to remove


class ReminderSettingsRequest(BaseModel):
    invoice_reminders_enabled: bool
    reminder_frequency_days: int  # 1-14 days
    max_invoice_reminders: int    # 1-10 reminders


class ReminderSettingsResponse(BaseModel):
    invoice_reminders_enabled: bool
    reminder_frequency_days: int
    max_invoice_reminders: int


class TaxFeeSettingsRequest(BaseModel):
    sales_tax_rate: float  # Percentage, e.g., 8.25 for 8.25%
    shop_supplies_rate: float  # Percentage of labor
    service_fee_rate: float  # Percentage of subtotal


class TaxFeeSettingsResponse(BaseModel):
    sales_tax_rate: float
    shop_supplies_rate: float
    service_fee_rate: float


def require_garage_owner():
    """Dependency to ensure only garage owner/admin can access"""
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Garage owner/admin access required",
            )
        return current_user
    return role_checker


@router.get("/zelle-settings", response_model=ZelleSettingsResponse)
async def get_zelle_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Get Zelle payment settings for the garage"""
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    return ZelleSettingsResponse(
        zelle_email=tenant.zelle_email,
        zelle_phone=tenant.zelle_phone,
        zelle_qr_image=tenant.zelle_qr_image,
    )


@router.put("/zelle-settings", response_model=ZelleSettingsResponse)
async def update_zelle_settings(
    body: ZelleSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Update Zelle payment settings for the garage"""
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    tenant.zelle_email = body.zelle_email
    tenant.zelle_phone = body.zelle_phone
    
    await db.commit()
    await db.refresh(tenant)
    
    return ZelleSettingsResponse(
        zelle_email=tenant.zelle_email,
        zelle_phone=tenant.zelle_phone,
        zelle_qr_image=tenant.zelle_qr_image,
    )


@router.put("/zelle-qr-image", response_model=ZelleSettingsResponse)
async def update_zelle_qr_image(
    body: ZelleQrImageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Upload or remove Zelle QR code image"""
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    # Validate base64 if provided
    if body.zelle_qr_image:
        # Basic validation - should start with data:image
        if not body.zelle_qr_image.startswith("data:image"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image format. Must be a base64 data URL.",
            )
        # Limit size (~2MB base64 = ~1.5MB image)
        if len(body.zelle_qr_image) > 2_000_000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image too large. Maximum size is ~1.5MB.",
            )
    
    tenant.zelle_qr_image = body.zelle_qr_image
    
    await db.commit()
    await db.refresh(tenant)
    
    return ZelleSettingsResponse(
        zelle_email=tenant.zelle_email,
        zelle_phone=tenant.zelle_phone,
        zelle_qr_image=tenant.zelle_qr_image,
    )


# ============================================================================
# Invoice Reminder Settings
# ============================================================================

@router.get("/reminder-settings", response_model=ReminderSettingsResponse)
async def get_reminder_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Get invoice reminder settings for the garage"""
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    return ReminderSettingsResponse(
        invoice_reminders_enabled=tenant.invoice_reminders_enabled,
        reminder_frequency_days=tenant.reminder_frequency_days,
        max_invoice_reminders=tenant.max_invoice_reminders,
    )


@router.put("/reminder-settings", response_model=ReminderSettingsResponse)
async def update_reminder_settings(
    body: ReminderSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Update invoice reminder settings for the garage"""
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    # Validate ranges
    if not 1 <= body.reminder_frequency_days <= 14:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reminder_frequency_days must be between 1 and 14"
        )
    if not 1 <= body.max_invoice_reminders <= 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="max_invoice_reminders must be between 1 and 10"
        )
    
    tenant.invoice_reminders_enabled = body.invoice_reminders_enabled
    tenant.reminder_frequency_days = body.reminder_frequency_days
    tenant.max_invoice_reminders = body.max_invoice_reminders
    
    await db.commit()
    await db.refresh(tenant)
    
    return ReminderSettingsResponse(
        invoice_reminders_enabled=tenant.invoice_reminders_enabled,
        reminder_frequency_days=tenant.reminder_frequency_days,
        max_invoice_reminders=tenant.max_invoice_reminders,
    )


# ============================================================================
# Manual Task Triggers (for testing/admin)
# ============================================================================

@router.post("/trigger-invoice-reminders")
async def trigger_invoice_reminders(
    current_user: User = Depends(require_garage_owner()),
):
    """
    Manually trigger invoice reminder processing for this tenant only.
    
    Note: The scheduled Celery task processes all tenants. This endpoint
    is tenant-scoped for garage owners to manually trigger reminders
    for their own customers only.
    """
    from app.tasks.invoice_reminders import _process_invoice_reminders
    
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    
    try:
        # Pass tenant_id to scope reminders to this tenant only
        count = await _process_invoice_reminders(tenant_id=str(current_user.tenant_id))
        return {"status": "success", "reminders_sent": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Tax & Fee Settings
# ============================================================================

@router.get("/tax-fee-settings", response_model=TaxFeeSettingsResponse)
async def get_tax_fee_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Get tax and fee settings for the garage"""
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    return TaxFeeSettingsResponse(
        sales_tax_rate=float(tenant.sales_tax_rate or 0),
        shop_supplies_rate=float(tenant.shop_supplies_rate or 0),
        service_fee_rate=float(tenant.service_fee_rate or 0),
    )


@router.put("/tax-fee-settings", response_model=TaxFeeSettingsResponse)
async def update_tax_fee_settings(
    body: TaxFeeSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Update tax and fee settings for the garage"""
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    # Validate ranges (0-99.999% to fit Numeric(5,3) column)
    if not 0 <= body.sales_tax_rate <= 99.999:
        raise HTTPException(status_code=400, detail="sales_tax_rate must be between 0 and 99.999")
    if not 0 <= body.shop_supplies_rate <= 99.999:
        raise HTTPException(status_code=400, detail="shop_supplies_rate must be between 0 and 99.999")
    if not 0 <= body.service_fee_rate <= 99.999:
        raise HTTPException(status_code=400, detail="service_fee_rate must be between 0 and 99.999")
    
    tenant.sales_tax_rate = body.sales_tax_rate
    tenant.shop_supplies_rate = body.shop_supplies_rate
    tenant.service_fee_rate = body.service_fee_rate
    
    await db.commit()
    await db.refresh(tenant)
    
    return TaxFeeSettingsResponse(
        sales_tax_rate=float(tenant.sales_tax_rate),
        shop_supplies_rate=float(tenant.shop_supplies_rate),
        service_fee_rate=float(tenant.service_fee_rate),
    )


# ============================================================================
# Garage Enrollment Management (Super Admin)
# ============================================================================

from datetime import datetime, timezone


class EnrollmentResponse(BaseModel):
    id: str
    garage_name: str
    slug: str
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    website: Optional[str]
    business_license: Optional[str]
    ein: Optional[str]
    enrollment_status: str
    applied_at: Optional[datetime]
    approved_at: Optional[datetime]
    rejection_reason: Optional[str]
    # Owner info
    owner_id: Optional[str]
    owner_email: Optional[str]
    owner_name: Optional[str]
    owner_phone: Optional[str]


class RejectEnrollmentRequest(BaseModel):
    reason: str


@router.get("/pending-enrollments", response_model=List[EnrollmentResponse])
async def list_pending_enrollments(
    status_filter: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    List garage enrollment applications.
    Only accessible by SUPER_ADMIN.
    """
    query = select(Tenant)
    
    if status_filter:
        query = query.where(Tenant.enrollment_status == status_filter)
    else:
        # Default: show pending enrollments
        query = query.where(Tenant.enrollment_status == "pending")
    
    query = query.order_by(Tenant.applied_at.desc())
    result = await db.execute(query)
    tenants = result.scalars().all()
    
    response_data = []
    for tenant in tenants:
        enrollment = EnrollmentResponse(
            id=str(tenant.id),
            garage_name=tenant.name,
            slug=tenant.slug,
            address=tenant.address,
            phone=tenant.phone,
            email=tenant.email,
            website=tenant.website,
            business_license=tenant.business_license,
            ein=tenant.ein,
            enrollment_status=tenant.enrollment_status,
            applied_at=tenant.applied_at,
            approved_at=tenant.approved_at,
            rejection_reason=tenant.rejection_reason,
            owner_id=str(tenant.owner_id) if tenant.owner_id else None,
            owner_email=None,
            owner_name=None,
            owner_phone=None,
        )
        
        # Get owner details
        if tenant.owner_id:
            owner_result = await db.execute(
                select(User).where(User.id == tenant.owner_id)
            )
            owner = owner_result.scalar_one_or_none()
            if owner:
                enrollment.owner_email = owner.email
                enrollment.owner_name = f"{owner.first_name} {owner.last_name}"
                enrollment.owner_phone = owner.phone
        
        response_data.append(enrollment)
    
    return response_data


@router.get("/enrollment-stats")
async def get_enrollment_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """Get enrollment statistics"""
    # Count by status
    pending_result = await db.execute(
        select(func.count(Tenant.id)).where(Tenant.enrollment_status == "pending")
    )
    pending_count = pending_result.scalar() or 0
    
    approved_result = await db.execute(
        select(func.count(Tenant.id)).where(Tenant.enrollment_status == "approved")
    )
    approved_count = approved_result.scalar() or 0
    
    rejected_result = await db.execute(
        select(func.count(Tenant.id)).where(Tenant.enrollment_status == "rejected")
    )
    rejected_count = rejected_result.scalar() or 0
    
    return {
        "pending": pending_count,
        "approved": approved_count,
        "rejected": rejected_count,
        "total": pending_count + approved_count + rejected_count,
    }


@router.post("/approve-enrollment/{tenant_id}")
async def approve_enrollment(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Approve a garage enrollment application.
    Activates the tenant and owner user account.
    """
    from app.services.email_service import send_enrollment_approved_email
    
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    
    if tenant.enrollment_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve enrollment with status '{tenant.enrollment_status}'",
        )
    
    # Activate tenant
    tenant.enrollment_status = "approved"
    tenant.is_active = True
    tenant.approved_at = datetime.now(timezone.utc)
    tenant.approved_by_id = current_user.id
    
    # Activate owner user
    if tenant.owner_id:
        owner_result = await db.execute(select(User).where(User.id == tenant.owner_id))
        owner = owner_result.scalar_one_or_none()
        if owner:
            owner.is_active = True
            
            # Send approval email
            try:
                await send_enrollment_approved_email(
                    to=owner.email,
                    garage_name=tenant.name,
                    owner_name=f"{owner.first_name} {owner.last_name}",
                )
            except Exception as e:
                print(f"Error sending approval email: {e}")
    
    await db.commit()
    
    return {"status": "success", "message": f"Enrollment for '{tenant.name}' has been approved"}


@router.post("/reject-enrollment/{tenant_id}")
async def reject_enrollment(
    tenant_id: UUID,
    body: RejectEnrollmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Reject a garage enrollment application.
    """
    from app.services.email_service import send_enrollment_rejected_email
    
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    
    if tenant.enrollment_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject enrollment with status '{tenant.enrollment_status}'",
        )
    
    # Update status
    tenant.enrollment_status = "rejected"
    tenant.rejection_reason = body.reason
    
    # Send rejection email
    if tenant.owner_id:
        owner_result = await db.execute(select(User).where(User.id == tenant.owner_id))
        owner = owner_result.scalar_one_or_none()
        if owner:
            try:
                await send_enrollment_rejected_email(
                    to=owner.email,
                    garage_name=tenant.name,
                    owner_name=f"{owner.first_name} {owner.last_name}",
                    reason=body.reason,
                )
            except Exception as e:
                print(f"Error sending rejection email: {e}")
    
    await db.commit()
    
    return {"status": "success", "message": f"Enrollment for '{tenant.name}' has been rejected"}
