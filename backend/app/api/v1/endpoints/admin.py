"""
Super Admin endpoints for platform management.
Only accessible by users with SUPER_ADMIN role.
"""
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from pydantic import BaseModel, EmailStr, Field
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.core.config import settings
from app.core.dependencies import get_db, get_current_active_user
from app.core.phone import normalize_phone
from app.core.pagination import paginated_or_list
from app.core.security import get_password_hash
from app.core.password_policy import validate_password
from app.core.redis import get_redis
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.error_log import ErrorLog, ErrorCategory, ErrorSeverity
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantWithOwnerResponse
from app.services import error_service
from app.services.mechanic_time_service import validate_local_time_str, validate_timezone_name
from app.services.website_logo_service import import_logo_from_website
from app.core.logging import get_logger

router = APIRouter()
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
SMS_PROVISION_COOLDOWN_SECONDS = 15
logger = get_logger(__name__)


class ProvisionSMSNumberRequest(BaseModel):
    area_code: Optional[int] = None
    country_code: str = "US"
    replace_existing: bool = False


class ProvisionSMSNumberResponse(BaseModel):
    tenant_id: UUID
    phone_number: str
    phone_sid: str
    sms_enabled: bool


class AttachSMSNumberRequest(BaseModel):
    phone_sid: str
    phone_number: Optional[str] = None
    enable_sms: bool = True
    configure_webhooks: bool = True
    replace_existing: bool = False


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


async def _release_sms_provision_cooldown(cooldown_key: str) -> None:
    try:
        redis = await get_redis()
        await redis.delete(cooldown_key)
    except Exception:
        # Best effort only; don't fail request path on cooldown cleanup.
        pass


@router.get("/tenants", response_model=List[TenantWithOwnerResponse])
async def list_all_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
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
    
    count_query = select(func.count(Tenant.id))
    if active_only:
        count_query = count_query.where(Tenant.is_active == True)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

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
    
    return paginated_or_list(response_data, total, skip, limit, paginated)


@router.get("/tenants/summary")
async def list_tenants_with_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    List all tenants with user/customer counts for platform overview.
    Only accessible by SUPER_ADMIN.
    """
    # Get all tenants
    result = await db.execute(select(Tenant).order_by(Tenant.name))
    tenants = result.scalars().all()
    
    summaries = []
    for tenant in tenants:
        # Count users by role for this tenant
        users_result = await db.execute(
            select(User.role, func.count(User.id))
            .where(User.tenant_id == tenant.id)
            .group_by(User.role)
        )
        users_by_role = {role.value: count for role, count in users_result.all()}
        
        # Count customers for this tenant
        customers_result = await db.execute(
            select(func.count(Customer.id))
            .where(Customer.tenant_id == tenant.id)
        )
        customer_count = customers_result.scalar() or 0
        
        # Get owner email
        owner_email = None
        if tenant.owner_id:
            owner_result = await db.execute(
                select(User.email).where(User.id == tenant.owner_id)
            )
            owner_email = owner_result.scalar()
        
        summaries.append({
            "id": str(tenant.id),
            "name": tenant.name,
            "is_active": tenant.is_active,
            "owner_email": owner_email,
            "users": {
                "owners": users_by_role.get("garage_owner", 0),
                "admins": users_by_role.get("garage_admin", 0),
                "mechanics": users_by_role.get("mechanic", 0),
                "total": sum(users_by_role.values()),
            },
            "customers": customer_count,
        })
    
    return summaries


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

    # Every garage gets an internal-fleet house account for its own trucks.
    from app.services.internal_fleet import ensure_internal_fleet_customer
    await ensure_internal_fleet_customer(db, tenant.id)

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


@router.post("/tenants/{tenant_id}/provision-sms-number", response_model=ProvisionSMSNumberResponse)
async def provision_tenant_sms_number(
    tenant_id: UUID,
    body: ProvisionSMSNumberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """Purchase and assign a Twilio number for tenant SMS."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    if tenant.sms_phone_sid and not body.replace_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant already has a provisioned SMS number",
        )

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Twilio account credentials are not configured",
        )

    cooldown_key = f"sms_provision_cooldown:{tenant_id}"
    try:
        redis = await get_redis()
        acquired = await redis.set(cooldown_key, "1", ex=SMS_PROVISION_COOLDOWN_SECONDS, nx=True)
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Provisioning SMS is temporarily rate-limited for this garage. "
                    f"Please wait {SMS_PROVISION_COOLDOWN_SECONDS} seconds and try again."
                ),
            )
    except HTTPException:
        raise
    except Exception:
        # Fail open when Redis is unavailable; keep endpoint operational.
        pass

    try:
        country_code = (body.country_code or "US").upper()
        search_params = {"sms_enabled": True, "limit": 20}
        if body.area_code and country_code == "US":
            search_params["area_code"] = body.area_code

        available_numbers = twilio_client.available_phone_numbers(country_code).local.list(**search_params)
        if not available_numbers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No available Twilio phone numbers found for the requested filters",
            )

        selected = available_numbers[0]
        purchased = twilio_client.incoming_phone_numbers.create(phone_number=selected.phone_number)

        base_url = settings.PUBLIC_API_BASE_URL.rstrip("/")
        sms_url = f"{base_url}/api/v1/webhooks/twilio/sms/inbound"
        status_callback = f"{base_url}/api/v1/webhooks/twilio/sms/status"
        twilio_client.incoming_phone_numbers(purchased.sid).update(
            sms_url=sms_url,
            sms_method="POST",
            status_callback=status_callback,
            status_callback_method="POST",
        )

        tenant.sms_phone_number = purchased.phone_number
        tenant.sms_phone_sid = purchased.sid
        tenant.sms_enabled = True
        await db.commit()
        await db.refresh(tenant)

    except HTTPException:
        await _release_sms_provision_cooldown(cooldown_key)
        raise
    except TwilioRestException as exc:
        await _release_sms_provision_cooldown(cooldown_key)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Twilio provisioning failed: {exc.msg}",
        )
    except Exception:
        await _release_sms_provision_cooldown(cooldown_key)
        raise

    return ProvisionSMSNumberResponse(
        tenant_id=tenant.id,
        phone_number=tenant.sms_phone_number or "",
        phone_sid=tenant.sms_phone_sid or "",
        sms_enabled=tenant.sms_enabled,
    )


@router.post("/tenants/{tenant_id}/attach-sms-number", response_model=ProvisionSMSNumberResponse)
async def attach_existing_sms_number(
    tenant_id: UUID,
    body: AttachSMSNumberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """Attach an already-provisioned Twilio number to a tenant."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    phone_sid = (body.phone_sid or "").strip()
    if not phone_sid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="phone_sid is required")

    if tenant.sms_phone_sid and tenant.sms_phone_sid != phone_sid and not body.replace_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant already has an SMS number. Set replace_existing=true to replace it.",
        )

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Twilio account credentials are not configured",
        )

    try:
        twilio_number = twilio_client.incoming_phone_numbers(phone_sid).fetch()
    except TwilioRestException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to fetch Twilio number for SID {phone_sid}: {exc.msg}",
        )

    twilio_phone_number = (getattr(twilio_number, "phone_number", None) or "").strip()
    if not twilio_phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Twilio number lookup succeeded but returned no phone number",
        )

    if body.phone_number:
        input_phone = normalize_phone(body.phone_number)
        twilio_phone = normalize_phone(twilio_phone_number)
        if input_phone and twilio_phone and input_phone != twilio_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provided phone_number does not match the Twilio number for this SID",
            )

    if body.configure_webhooks:
        base_url = (settings.PUBLIC_API_BASE_URL or "").strip().rstrip("/")
        if not base_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PUBLIC_API_BASE_URL must be configured to set Twilio webhooks",
            )

        sms_url = f"{base_url}/api/v1/webhooks/twilio/sms/inbound"
        status_callback = f"{base_url}/api/v1/webhooks/twilio/sms/status"
        try:
            twilio_client.incoming_phone_numbers(phone_sid).update(
                sms_url=sms_url,
                sms_method="POST",
                status_callback=status_callback,
                status_callback_method="POST",
            )
        except TwilioRestException as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to configure Twilio webhooks: {exc.msg}",
            )

    tenant.sms_phone_sid = phone_sid
    tenant.sms_phone_number = twilio_phone_number
    tenant.sms_enabled = body.enable_sms
    await db.commit()
    await db.refresh(tenant)

    return ProvisionSMSNumberResponse(
        tenant_id=tenant.id,
        phone_number=tenant.sms_phone_number or "",
        phone_sid=tenant.sms_phone_sid or "",
        sms_enabled=tenant.sms_enabled,
    )


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


@router.get("/performance/stats")
async def get_performance_stats(
    current_user: User = Depends(require_super_admin()),
):
    """
    Get application performance metrics from Prometheus registry.
    Only accessible by SUPER_ADMIN.
    """
    from app.core.metrics_parser import get_performance_stats
    
    return get_performance_stats()


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
    labor_rate: float  # Default hourly rate
    internal_labor_rate: float = 0.0  # Hourly labor cost for internal fleet repairs


class TaxFeeSettingsResponse(BaseModel):
    sales_tax_rate: float
    shop_supplies_rate: float
    service_fee_rate: float
    labor_rate: float
    internal_labor_rate: float = 0.0


class WorkforceSettingsRequest(BaseModel):
    timezone: str
    default_core_hours_minutes: int
    default_shift_start_local: str
    default_shift_end_local: str


class WorkforceSettingsResponse(BaseModel):
    timezone: str
    default_core_hours_minutes: int
    default_shift_start_local: str
    default_shift_end_local: str


class GarageProfileResponse(BaseModel):
    name: str
    slug: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    partner_summary: Optional[str] = None
    partner_services: Optional[str] = None


class GarageProfileUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    website: Optional[str] = Field(None, max_length=255)
    logo_url: Optional[str] = Field(None, max_length=500)
    partner_summary: Optional[str] = Field(None, max_length=280)
    partner_services: Optional[str] = Field(None, max_length=180)


class GarageLogoImportRequest(BaseModel):
    website: Optional[str] = Field(None, max_length=255)


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


@router.get("/garage-profile", response_model=GarageProfileResponse)
async def get_garage_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Get garage profile settings for the current tenant."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    return GarageProfileResponse(
        name=tenant.name,
        slug=tenant.slug,
        address=tenant.address,
        phone=tenant.phone,
        email=tenant.email,
        website=tenant.website,
        logo_url=tenant.logo_url,
        partner_summary=tenant.partner_summary,
        partner_services=tenant.partner_services,
    )


@router.put("/garage-profile", response_model=GarageProfileResponse)
async def update_garage_profile(
    body: GarageProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Update garage profile settings for the current tenant."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Garage name is required")

    def clean_optional_text(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    tenant.name = name
    tenant.address = clean_optional_text(body.address)
    tenant.phone = normalize_phone(body.phone)
    tenant.email = clean_optional_text(str(body.email)) if body.email else None
    tenant.website = clean_optional_text(body.website)
    tenant.logo_url = clean_optional_text(body.logo_url)
    tenant.partner_summary = clean_optional_text(body.partner_summary)
    tenant.partner_services = clean_optional_text(body.partner_services)

    await db.commit()
    await db.refresh(tenant)

    return GarageProfileResponse(
        name=tenant.name,
        slug=tenant.slug,
        address=tenant.address,
        phone=tenant.phone,
        email=tenant.email,
        website=tenant.website,
        logo_url=tenant.logo_url,
        partner_summary=tenant.partner_summary,
        partner_services=tenant.partner_services,
    )


@router.post("/garage-profile/import-logo", response_model=GarageProfileResponse)
async def import_garage_profile_logo(
    body: GarageLogoImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Import a tenant logo from the garage website and persist it to the tenant profile."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    website = (body.website or tenant.website or "").strip()
    if not website:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Website is required before importing a logo")

    tenant.website = website

    try:
        imported_logo_url = await import_logo_from_website(website, tenant_id=str(tenant.id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning(
            "tenant_logo_import_failed",
            tenant_id=str(tenant.id),
            website=website,
            error=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to import logo from the website right now") from exc

    if not imported_logo_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No logo image was found on that website")

    tenant.logo_url = imported_logo_url

    await db.commit()
    await db.refresh(tenant)

    return GarageProfileResponse(
        name=tenant.name,
        slug=tenant.slug,
        address=tenant.address,
        phone=tenant.phone,
        email=tenant.email,
        website=tenant.website,
        logo_url=tenant.logo_url,
        partner_summary=tenant.partner_summary,
        partner_services=tenant.partner_services,
    )


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
        labor_rate=float(tenant.labor_rate if tenant.labor_rate is not None else 100),
        internal_labor_rate=float(tenant.internal_labor_rate or 0),
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
    if not 0 <= body.labor_rate <= 9999.99:
        raise HTTPException(status_code=400, detail="labor_rate must be between 0 and 9999.99")
    if not 0 <= body.internal_labor_rate <= 9999.99:
        raise HTTPException(status_code=400, detail="internal_labor_rate must be between 0 and 9999.99")

    tenant.sales_tax_rate = body.sales_tax_rate
    tenant.shop_supplies_rate = body.shop_supplies_rate
    tenant.service_fee_rate = body.service_fee_rate
    tenant.labor_rate = body.labor_rate
    tenant.internal_labor_rate = body.internal_labor_rate

    await db.commit()
    await db.refresh(tenant)

    return TaxFeeSettingsResponse(
        sales_tax_rate=float(tenant.sales_tax_rate),
        shop_supplies_rate=float(tenant.shop_supplies_rate),
        service_fee_rate=float(tenant.service_fee_rate),
        labor_rate=float(tenant.labor_rate),
        internal_labor_rate=float(tenant.internal_labor_rate),
    )


# ============================================================================
# Workforce Settings
# ============================================================================

@router.get("/workforce-settings", response_model=WorkforceSettingsResponse)
async def get_workforce_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    return WorkforceSettingsResponse(
        timezone=tenant.timezone or "America/New_York",
        default_core_hours_minutes=int(tenant.default_core_hours_minutes or 480),
        default_shift_start_local=tenant.default_shift_start_local or "08:00",
        default_shift_end_local=tenant.default_shift_end_local or "18:00",
    )


@router.put("/workforce-settings", response_model=WorkforceSettingsResponse)
async def update_workforce_settings(
    body: WorkforceSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    try:
        validate_timezone_name(body.timezone)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid timezone")
    try:
        validate_local_time_str(body.default_shift_start_local)
        validate_local_time_str(body.default_shift_end_local)
    except Exception:
        raise HTTPException(status_code=400, detail="Shift times must be in HH:MM format")

    if body.default_shift_start_local >= body.default_shift_end_local:
        raise HTTPException(status_code=400, detail="default_shift_start_local must be before default_shift_end_local")
    if not 1 <= body.default_core_hours_minutes <= 1440:
        raise HTTPException(status_code=400, detail="default_core_hours_minutes must be between 1 and 1440")

    tenant.timezone = body.timezone
    tenant.default_core_hours_minutes = body.default_core_hours_minutes
    tenant.default_shift_start_local = body.default_shift_start_local
    tenant.default_shift_end_local = body.default_shift_end_local
    await db.commit()
    await db.refresh(tenant)

    return WorkforceSettingsResponse(
        timezone=tenant.timezone,
        default_core_hours_minutes=int(tenant.default_core_hours_minutes),
        default_shift_start_local=tenant.default_shift_start_local,
        default_shift_end_local=tenant.default_shift_end_local,
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
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    List garage enrollment applications.
    Only accessible by SUPER_ADMIN.
    """
    query = select(Tenant)
    count_query = select(func.count(Tenant.id))
    
    if status_filter:
        query = query.where(Tenant.enrollment_status == status_filter)
        count_query = count_query.where(Tenant.enrollment_status == status_filter)
    else:
        # Default: show pending enrollments
        query = query.where(Tenant.enrollment_status == "pending")
        count_query = count_query.where(Tenant.enrollment_status == "pending")

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    query = query.order_by(Tenant.applied_at.desc()).offset(skip).limit(limit)
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
    
    return paginated_or_list(response_data, total, skip, limit, paginated)


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


# ============ Error Management Endpoints ============

class ErrorLogResponse(BaseModel):
    id: UUID
    correlation_id: Optional[str]
    created_at: datetime
    error_type: str
    error_category: str
    severity: str
    endpoint: Optional[str]
    method: Optional[str]
    status_code: Optional[int]
    user_id: Optional[UUID]
    tenant_id: Optional[UUID]
    message: str
    resolved: bool
    resolved_at: Optional[datetime]
    resolved_by_id: Optional[UUID]
    notes: Optional[str]
    
    class Config:
        from_attributes = True


class ErrorLogDetailResponse(ErrorLogResponse):
    stack_trace: Optional[str]
    request_context: Optional[dict]


class ErrorListResponse(BaseModel):
    errors: List[ErrorLogResponse]
    total: int
    skip: int
    limit: int


class ResolveErrorRequest(BaseModel):
    notes: Optional[str] = None


@router.get("/errors", response_model=ErrorListResponse)
async def list_errors(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
    category: Optional[str] = Query(None, description="Filter by category (payment, auth, validation, database, external_api, unhandled)"),
    severity: Optional[str] = Query(None, description="Filter by severity (warning, error, critical)"),
    endpoint: Optional[str] = Query(None, description="Filter by endpoint (partial match)"),
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant ID"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    start_date: Optional[datetime] = Query(None, description="Filter errors after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter errors before this date"),
    search: Optional[str] = Query(None, description="Search in message, error_type, correlation_id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    List application errors with filtering and pagination.
    Only accessible by SUPER_ADMIN.
    """
    # Convert string category/severity to enums if provided
    category_enum = None
    if category:
        try:
            category_enum = ErrorCategory(category)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category. Valid values: {[e.value for e in ErrorCategory]}"
            )
    
    severity_enum = None
    if severity:
        try:
            severity_enum = ErrorSeverity(severity)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity. Valid values: {[e.value for e in ErrorSeverity]}"
            )
    
    errors, total = await error_service.get_errors(
        db=db,
        skip=skip,
        limit=limit,
        error_type=error_type,
        category=category_enum,
        severity=severity_enum,
        endpoint=endpoint,
        user_id=user_id,
        tenant_id=tenant_id,
        resolved=resolved,
        start_date=start_date,
        end_date=end_date,
        search=search,
    )
    
    return ErrorListResponse(
        errors=[
            ErrorLogResponse(
                id=e.id,
                correlation_id=e.correlation_id,
                created_at=e.created_at,
                error_type=e.error_type,
                error_category=str(e.error_category) if e.error_category else "unknown",
                severity=str(e.severity) if e.severity else "error",
                endpoint=e.endpoint,
                method=e.method,
                status_code=e.status_code,
                user_id=e.user_id,
                tenant_id=e.tenant_id,
                message=e.message,
                resolved=e.resolved,
                resolved_at=e.resolved_at,
                resolved_by_id=e.resolved_by_id,
                notes=e.notes,
            )
            for e in errors
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/errors/stats")
async def get_error_stats(
    start_date: Optional[datetime] = Query(None, description="Start of period (default: 24h ago)"),
    end_date: Optional[datetime] = Query(None, description="End of period (default: now)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get aggregated error statistics for the dashboard.
    Only accessible by SUPER_ADMIN.
    """
    return await error_service.get_error_stats(
        db=db,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/errors/types")
async def get_error_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get list of distinct error types for filtering dropdown.
    Only accessible by SUPER_ADMIN.
    """
    types = await error_service.get_distinct_error_types(db)
    return {"types": types}


@router.get("/errors/endpoints")
async def get_error_endpoints(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get list of distinct endpoints for filtering dropdown.
    Only accessible by SUPER_ADMIN.
    """
    endpoints = await error_service.get_distinct_endpoints(db)
    return {"endpoints": endpoints}


@router.get("/errors/{error_id}", response_model=ErrorLogDetailResponse)
async def get_error_detail(
    error_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get full error details including stack trace and request context.
    Only accessible by SUPER_ADMIN.
    """
    error = await error_service.get_error_by_id(db, error_id)
    
    if not error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Error not found")
    
    return ErrorLogDetailResponse(
        id=error.id,
        correlation_id=error.correlation_id,
        created_at=error.created_at,
        error_type=error.error_type,
        error_category=str(error.error_category) if error.error_category else "unknown",
        severity=str(error.severity) if error.severity else "error",
        endpoint=error.endpoint,
        method=error.method,
        status_code=error.status_code,
        user_id=error.user_id,
        tenant_id=error.tenant_id,
        message=error.message,
        stack_trace=error.stack_trace,
        request_context=error.request_context,
        resolved=error.resolved,
        resolved_at=error.resolved_at,
        resolved_by_id=error.resolved_by_id,
        notes=error.notes,
    )


@router.get("/errors/correlation/{correlation_id}", response_model=List[ErrorLogResponse])
async def get_errors_by_correlation(
    correlation_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Find all errors with the same correlation ID (from the same request).
    Only accessible by SUPER_ADMIN.
    """
    errors, total = await error_service.get_errors_by_correlation_id(
        db,
        correlation_id=correlation_id,
        skip=skip,
        limit=limit,
    )
    
    items = [
        ErrorLogResponse(
            id=e.id,
            correlation_id=e.correlation_id,
            created_at=e.created_at,
            error_type=e.error_type,
            error_category=str(e.error_category) if e.error_category else "unknown",
            severity=str(e.severity) if e.severity else "error",
            endpoint=e.endpoint,
            method=e.method,
            status_code=e.status_code,
            user_id=e.user_id,
            tenant_id=e.tenant_id,
            message=e.message,
            resolved=e.resolved,
            resolved_at=e.resolved_at,
            resolved_by_id=e.resolved_by_id,
            notes=e.notes,
        )
        for e in errors
    ]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.patch("/errors/{error_id}/resolve")
async def resolve_error(
    error_id: UUID,
    body: ResolveErrorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Mark an error as resolved.
    Only accessible by SUPER_ADMIN.
    """
    error = await error_service.resolve_error(
        db=db,
        error_id=error_id,
        resolved_by_id=current_user.id,
        notes=body.notes,
    )
    
    if not error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Error not found")
    
    return {"status": "success", "message": "Error marked as resolved"}


@router.patch("/errors/{error_id}/unresolve")
async def unresolve_error(
    error_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    """
    Mark an error as unresolved (reopen).
    Only accessible by SUPER_ADMIN.
    """
    error = await error_service.unresolve_error(db, error_id)
    
    if not error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Error not found")
    
    return {"status": "success", "message": "Error reopened"}


# ============================================================================
# Staff management (garage owner/admin: add team members with a role)
# ============================================================================

# Roles a garage owner/admin can assign when adding a staff member.
ASSIGNABLE_STAFF_ROLES = {
    UserRole.GARAGE_ADMIN,
    UserRole.RECEPTIONIST,
    UserRole.MECHANIC,
    UserRole.FLEET_MANAGER,
}
# Roles shown in the team roster (assignable set + the owner).
STAFF_ROSTER_ROLES = ASSIGNABLE_STAFF_ROLES | {UserRole.GARAGE_OWNER}


class StaffCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    role: UserRole
    phone: Optional[str] = None
    address: Optional[str] = None
    # Technician-only (applied when role == mechanic)
    core_hours_target_minutes_override: Optional[int] = None
    shift_start_local_override: Optional[str] = None
    shift_end_local_override: Optional[str] = None


class StaffUpdate(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: Optional[str] = None  # owner/admin sets a new password (reset)


class StaffMember(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/staff", response_model=List[StaffMember])
async def list_staff(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """List all staff members for the current garage (owner + assignable roles)."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(
        select(User).where(
            User.tenant_id == current_user.tenant_id,
            User.role.in_(list(STAFF_ROSTER_ROLES)),
        ).order_by(User.first_name, User.last_name)
    )
    return [StaffMember.model_validate(u) for u in result.scalars().all()]


@router.post("/staff", response_model=StaffMember, status_code=status.HTTP_201_CREATED)
async def create_staff(
    body: StaffCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Create a staff member with a chosen role (technician, receptionist, fleet manager, admin)."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    if body.role not in ASSIGNABLE_STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be one of: technician, receptionist, fleet manager, garage admin",
        )
    validate_password(body.password)

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=get_password_hash(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone or None,
        address=body.address or None,
        role=body.role,
        tenant_id=current_user.tenant_id,
        is_active=True,
        is_verified=True,
    )
    # Technician-only workforce overrides
    if body.role == UserRole.MECHANIC:
        if body.core_hours_target_minutes_override is not None and not 1 <= body.core_hours_target_minutes_override <= 1440:
            raise HTTPException(status_code=400, detail="core_hours_target_minutes_override must be between 1 and 1440")
        user.core_hours_target_minutes_override = body.core_hours_target_minutes_override
        user.shift_start_local_override = body.shift_start_local_override or None
        user.shift_end_local_override = body.shift_end_local_override or None

    db.add(user)
    await db.commit()
    await db.refresh(user)
    return StaffMember.model_validate(user)


@router.patch("/staff/{user_id}", response_model=StaffMember)
async def update_staff(
    user_id: UUID,
    body: StaffUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner()),
):
    """Edit a staff member's details, role, active status, or password (owner/admin only)."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
    if user.role == UserRole.GARAGE_OWNER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The garage owner cannot be modified here")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot modify your own account here")
    if body.role is not None:
        if body.role not in ASSIGNABLE_STAFF_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.first_name is not None and body.first_name.strip():
        user.first_name = body.first_name.strip()
    if body.last_name is not None and body.last_name.strip():
        user.last_name = body.last_name.strip()
    if body.phone is not None:
        user.phone = body.phone or None
    if body.email is not None and body.email != user.email:
        clash = await db.execute(select(User).where(User.email == body.email, User.id != user.id))
        if clash.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        user.email = body.email
    if body.password:
        validate_password(body.password)
        user.hashed_password = get_password_hash(body.password)
    await db.commit()
    await db.refresh(user)
    return StaffMember.model_validate(user)
