import math
import re
import traceback
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, literal_column
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.vehicle_display import vehicle_display_label
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.tenant import Tenant
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor, LaborLineType
from app.db.models.recommended_service import RecommendedService, RecommendedServicePriority
from app.db.models.quote import Quote
from app.db.models.mechanic_points import MechanicPoints, MechanicPointsBalance, PointsTransactionType
from app.db.models.description_library import DescriptionLibraryEntry
from app.tasks.description_library_refresh import process_on_demand_library_regenerate
from app.services.email_service import send_email
from app.services.twilio_service import send_sms
from app.services.price_build_service import (
    PriceBuildLockedError,
    PriceBuildNotFoundError,
    PriceBuildService,
    PriceBuildValidationError,
)
from app.core.config import settings
from app.core.metrics import record_repair_order_created
from app.core.logging import get_logger
from app.core.phone import normalize_phone
from app.core.websocket import broadcast_repair_order_update
from app.core.websocket import broadcast_mechanic_timer_update
from app.core.websocket import broadcast_mechanic_attendance_update
from app.services.mechanic_time_service import fetch_tenant_and_mechanic, get_active_session, start_session, stop_active_session
from app.db.models.mechanic_time import MechanicSessionType, MechanicTimeSession
from app.schemas.repair_order import (
    RepairOrderCreate,
    RepairOrderUpdate,
    RepairOrderResponse,
    RepairOrderDetailResponse,
    PartsUsageCreate,
    PartsUsageUpdate,
    PartsPricingModeRequest,
    DiscountUpdate,
    PartsUsageResponse,
    LaborCreate,
    LaborUpdate,
    LaborResponse,
    QuickRepairOrderCreate,
    RepairOrderStartWorkResponse,
    PriceBuildFlatServiceRequest,
    PriceBuildLineUpdateRequest,
    PriceBuildRepairOpsApplyRequest,
    PriceBuildRepairOpsSearchRequest,
    PriceBuildSearchResponse,
    PriceBuildSubletRequest,
    PriceBuildSummaryResponse,
    PriceBuildWarning,
    RepairOperationCandidate,
    RecommendedServiceCreate,
    RecommendedServiceUpdate,
    RecommendedServiceResponse,
    PartSuggestion,
    PartSuggestionsResponse,
)

logger = get_logger(__name__)

router = APIRouter()
price_build_service = PriceBuildService()

# Only draft and quoted ROs can have parts/labor modified
EDITABLE_RO_STATUSES = (RepairOrderStatus.DRAFT, RepairOrderStatus.QUOTED)
DANGER_ACTION_RO_STATUSES = (RepairOrderStatus.DRAFT, RepairOrderStatus.QUOTED)
# Deleting is also allowed once an order is cancelled — cancelling doesn't
# clean anything up, so customers need a way to remove cancelled clutter.
DELETABLE_RO_STATUSES = DANGER_ACTION_RO_STATUSES + (RepairOrderStatus.CANCELLED,)
# Once a customer has been invoiced or paid, the order is a financial record and
# must stay in history — it can't be cancelled or deleted. Every other status
# (approved, in_progress, completed, …) can be moved to cancelled/deleted so the
# owner can clear stuck or wrong orders from the cockpit.
FINANCIALLY_PROTECTED_STATUSES = (RepairOrderStatus.INVOICED, RepairOrderStatus.PAID)
# Internal fleet WOs log labor/parts as work happens, so they stay editable
# through the whole active flow — only terminal states freeze them.
INTERNAL_FROZEN_RO_STATUSES = (
    RepairOrderStatus.COMPLETED,
    RepairOrderStatus.INVOICED,
    RepairOrderStatus.CANCELLED,
)
PRICE_BUILD_EDIT_ROLES = (
    UserRole.GARAGE_OWNER,
    UserRole.GARAGE_ADMIN,
    UserRole.RECEPTIONIST,
    UserRole.FLEET_MANAGER,
)
# Staff who can manage repair orders and their parts/labor. Fleet managers are
# further scoped to internal-fleet ROs by _check_ro_access / create guards.
RO_MANAGE_ROLES = (
    UserRole.GARAGE_OWNER,
    UserRole.GARAGE_ADMIN,
    UserRole.RECEPTIONIST,
    UserRole.MECHANIC,
    UserRole.FLEET_MANAGER,
)


def require_role(*allowed_roles: UserRole):
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker


def _to_price_build_summary(
    order: RepairOrder,
    *,
    warnings: Optional[list[PriceBuildWarning]] = None,
) -> PriceBuildSummaryResponse:
    labor_resp = [LaborResponse.model_validate(li) for li in order.labor_items]
    pricing_locked = _is_pricing_locked_for_edits(order)
    return PriceBuildSummaryResponse(
        order_id=order.id,
        labor_total=order.total_labor_cost,
        parts_total=order.total_parts_cost,
        labor_discount_amount=order.labor_discount_amount or Decimal("0.00"),
        order_discount_amount=order.order_discount_amount or Decimal("0.00"),
        total_cost=order.total_cost,
        pricing_locked=pricing_locked,
        pricing_locked_at=order.pricing_locked_at,
        pricing_lock_reason=order.pricing_lock_reason,
        lines=labor_resp,
        warnings=warnings or [],
    )


def _is_pricing_locked_for_edits(order: RepairOrder) -> bool:
    if order.pricing_locked_at is None:
        return False
    if order.pricing_lock_reason == "quote_sent" and order.status == RepairOrderStatus.QUOTED:
        return False
    return True


def _packages_consumed(quantity: Decimal) -> int:
    """Whole packages/jugs a part quantity draws down from stock.

    stock_quantity tracks whole packages on hand (e.g. 5-gal jugs), not
    fractional volume. A fluid quantity of 1.25 gal still opens (and is
    billed against) one jug, so any quantity > 0 rounds up to at least 1
    package; a delta of 0.25 more on an existing line also rounds up to 1
    additional package. We deliberately don't track partial-jug remainders.
    """
    return max(1, math.ceil(quantity)) if quantity > 0 else 0


def _build_parts_usage_response(pu: "PartsUsage", inv=None) -> "PartsUsageResponse":
    inv = inv if inv is not None else pu.inventory_item
    list_price = pu.list_price if pu.list_price is not None else pu.unit_price
    savings = (list_price - pu.unit_price) * pu.quantity if list_price > pu.unit_price else Decimal("0")
    return PartsUsageResponse(
        id=pu.id,
        repair_order_id=pu.repair_order_id,
        inventory_id=pu.inventory_id,
        inventory_sku=inv.sku if inv else "",
        inventory_name=inv.name if inv else "",
        quantity=pu.quantity,
        unit_type=inv.unit_type if inv else "each",
        unit_price=pu.unit_price,
        unit_cost=pu.unit_cost,
        list_price=list_price,
        savings=savings,
        total_price=pu.total_price,
        source_service_id=pu.source_service_id,
        created_at=pu.created_at,
    )


def _map_price_build_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, PriceBuildNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PriceBuildLockedError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, PriceBuildValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Price build operation failed")


async def generate_order_number(db: AsyncSession, tenant_id: UUID) -> str:
    """Generate unique order number using MAX approach."""
    from app.core.unique_id import derive_order_number_prefix, generate_unique_number

    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    prefix = (tenant.order_number_prefix if tenant else None) or derive_order_number_prefix(tenant.name if tenant else "")

    return await generate_unique_number(
        db=db,
        model_class=RepairOrder,
        number_column=RepairOrder.order_number,
        tenant_id=tenant_id,
        prefix=f"{prefix}-",
    )


@router.post("", response_model=RepairOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_repair_order(
    order_data: RepairOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )

    # Verify customer exists and belongs to tenant
    result = await db.execute(
        select(Customer).where(
            and_(
                Customer.id == order_data.customer_id,
                Customer.tenant_id == current_user.tenant_id,
            )
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Fleet managers may only open repair orders against the internal fleet.
    if current_user.role == UserRole.FLEET_MANAGER and not customer.is_internal_fleet:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Fleet managers can only create internal fleet repair orders",
        )

    # Verify vehicle exists and belongs to customer
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == order_data.vehicle_id,
                Vehicle.customer_id == order_data.customer_id,
                Vehicle.tenant_id == current_user.tenant_id,
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found or does not belong to customer",
        )
    
    # Use retry wrapper to handle rare race conditions on order number
    from app.core.unique_id import create_with_retry
    
    async def create_order_with_number(order_number: str) -> RepairOrder:
        repair_order = RepairOrder(
            tenant_id=current_user.tenant_id,
            order_number=order_number,
            status=RepairOrderStatus.DRAFT,
            # Repairs on the garage's own fleet are internal-cost (no markup/invoice).
            is_internal=customer.is_internal_fleet,
            **order_data.model_dump(),
        )
        db.add(repair_order)
        # Don't commit here - create_with_retry uses savepoints and handles commit
        return repair_order
    
    repair_order = await create_with_retry(
        db=db,
        create_fn=create_order_with_number,
        generate_number_fn=lambda: generate_order_number(db, current_user.tenant_id),
        entity_name="repair_order",
    )
    await db.refresh(repair_order)
    record_repair_order_created(str(current_user.tenant_id))
    
    return RepairOrderResponse.model_validate(repair_order)


@router.post("/quick", response_model=RepairOrderResponse, status_code=status.HTTP_201_CREATED)
async def quick_create_repair_order(
    data: QuickRepairOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    """Quick-create a repair order with minimal info. Auto-creates walk-in customer and vehicle."""
    try:
        tenant_id = current_user.tenant_id
        if not tenant_id:
            raise HTTPException(status_code=400, detail="User must be associated with a tenant")

        # Quick-create always spins up an external walk-in customer, which is outside
        # a fleet manager's internal-fleet scope.
        if current_user.role == UserRole.FLEET_MANAGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Fleet managers can only create internal fleet repair orders",
            )

        raw_phone = (data.phone or "").strip()
        # Normalize phone for consistent storage and lookup
        phone = normalize_phone(raw_phone) or ""

        # Find or create customer
        if phone:
            # Look for existing customer by phone in this tenant
            result = await db.execute(
                select(Customer).where(
                    and_(
                        Customer.tenant_id == tenant_id,
                        Customer.phone == phone,
                    )
                )
            )
            customer = result.scalar_one_or_none()
            if not customer:
                customer = Customer(
                    tenant_id=tenant_id,
                    first_name="Walk-in",
                    last_name=raw_phone or "Customer",  # Keep original format for display
                    email=f"walkin+{phone}@placeholder.dieselbridge.network",
                    phone=phone,  # Store normalized
                    source="walk_in",
                )
                db.add(customer)
                await db.flush()
        else:
            # Use or create a generic walk-in customer for this tenant
            # Use scalars().first() instead of scalar_one_or_none() to handle potential duplicates
            # from race conditions (no unique constraint on email+tenant_id)
            result = await db.execute(
                select(Customer).where(
                    and_(
                        Customer.tenant_id == tenant_id,
                        Customer.email == "walkin@placeholder.dieselbridge.network",
                    )
                ).limit(1)
            )
            customer = result.scalars().first()
            if not customer:
                customer = Customer(
                    tenant_id=tenant_id,
                    first_name="Walk-in",
                    last_name="Customer",
                    email="walkin@placeholder.dieselbridge.network",
                    source="walk_in",
                )
                db.add(customer)
                await db.flush()

        # Parse vehicle_description best-effort: "2019 Peterbilt 579" -> year=2019 make=Peterbilt model=579
        desc = data.vehicle_description.strip() if data.vehicle_description else ""
        parts = desc.split(None, 2) if desc else []
        year = None
        make = desc if desc else "Unknown"
        model = "N/A"

        if len(parts) >= 1 and parts[0].isdigit() and len(parts[0]) == 4:
            year = int(parts[0])
            if len(parts) >= 3:
                make = parts[1]
                model = parts[2]
            elif len(parts) == 2:
                make = parts[1]
                model = "N/A"
            else:
                make = "Unknown"
        elif len(parts) >= 2:
            make = parts[0]
            model = " ".join(parts[1:])

        vehicle = Vehicle(
            tenant_id=tenant_id,
            customer_id=customer.id,
            make=make,
            model=model,
            year=year,
        )
        db.add(vehicle)
        await db.flush()

        # Use retry wrapper to handle rare race conditions on order number
        from app.core.unique_id import create_with_retry
        
        async def create_order_with_number(order_number: str) -> RepairOrder:
            repair_order = RepairOrder(
                tenant_id=tenant_id,
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                order_number=order_number,
                status=RepairOrderStatus.DRAFT,
                description=data.complaint or None,
            )
            db.add(repair_order)
            # Don't commit here - create_with_retry uses savepoints and handles commit
            return repair_order
        
        repair_order = await create_with_retry(
            db=db,
            create_fn=create_order_with_number,
            generate_number_fn=lambda: generate_order_number(db, tenant_id),
            entity_name="repair_order",
        )
        await db.refresh(repair_order)
        record_repair_order_created(str(tenant_id))

        return RepairOrderResponse.model_validate(repair_order)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "quick_order_failed",
            error_type=type(e).__name__,
            error_message=str(e),
            traceback=traceback.format_exc(),
            phone=data.phone,
            vehicle_description=data.vehicle_description,
            complaint=data.complaint,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create order: {type(e).__name__}: {str(e)}"
        )


class DescriptionSuggestion(BaseModel):
    text: str
    times_used: int


@router.get("/description-suggestions", response_model=List[DescriptionSuggestion])
async def get_description_suggestions(
    q: str = Query(..., min_length=1, max_length=200, description="What the user has typed so far"),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Autocomplete for repair order complaint/work-performed text.

    Queries the AI-canonicalized description library first (clean, deduped,
    typo-fixed service names — see app/services/description_library_service.py)
    and falls back to raw repair_orders.description history for any tenant
    that hasn't regenerated a library yet. Both paths use the same
    pg_trgm word_similarity fuzzy match, ranked by how often the shop has
    used that wording and how recently.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    tenant_id = current_user.tenant_id

    term = q.strip()
    if not term:
        return []

    library_result = await db.execute(
        select(
            DescriptionLibraryEntry.canonical_text,
            DescriptionLibraryEntry.source_count,
            func.word_similarity(term, DescriptionLibraryEntry.canonical_text).label("score"),
        )
        .where(
            DescriptionLibraryEntry.tenant_id == tenant_id,
            DescriptionLibraryEntry.library_type == "ro_description",
            func.word_similarity(term, DescriptionLibraryEntry.canonical_text) > 0.2,
        )
        .order_by(
            func.word_similarity(term, DescriptionLibraryEntry.canonical_text).desc(),
            DescriptionLibraryEntry.source_count.desc(),
        )
        .limit(limit)
    )
    library_rows = library_result.all()
    if library_rows:
        return [
            DescriptionSuggestion(text=text, times_used=source_count)
            for text, source_count, _score in library_rows
        ]

    # No canonical library yet for this tenant — fall back to raw history.
    # word_similarity matches a short typed fragment against any substring of
    # a longer stored description (plain trigram similarity() penalizes
    # length differences too heavily for "brake" to match "Air leak on front
    # brake chamber"). Threshold set loosely since this is a suggestion list,
    # not a hard filter — worst matches just sort last.
    result = await db.execute(
        select(
            RepairOrder.description,
            func.max(RepairOrder.created_at).label("last_used"),
            func.count(RepairOrder.id).label("times_used"),
            func.max(func.word_similarity(term, RepairOrder.description)).label("score"),
        )
        .where(
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.description.isnot(None),
            RepairOrder.description != "",
            func.word_similarity(term, RepairOrder.description) > 0.2,
        )
        .group_by(RepairOrder.description)
        .order_by(
            func.max(func.word_similarity(term, RepairOrder.description)).desc(),
            func.count(RepairOrder.id).desc(),
            func.max(RepairOrder.created_at).desc(),
        )
        .limit(limit)
    )
    rows = result.all()
    return [DescriptionSuggestion(text=desc, times_used=times_used) for desc, _last_used, times_used, _score in rows]


class DescriptionLibraryRegenerateResponse(BaseModel):
    queued: bool = True


@router.post(
    "/description-library/regenerate",
    response_model=DescriptionLibraryRegenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_description_library_endpoint(
    current_user: User = Depends(get_current_active_user),
):
    """Owner/admin-triggered rebuild of this tenant's canonical description
    library — sends distinct historical RO descriptions to Claude to split
    compound entries, fix typos, and dedupe into clean service names.

    Runs as a background Celery task (the Claude call can take minutes for a
    shop with a lot of history) — this endpoint enqueues the work and returns
    immediately rather than blocking the request.
    """
    if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shop owner/admin access required")
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ANTHROPIC_API_KEY is not configured")

    process_on_demand_library_regenerate.delay(str(current_user.tenant_id), "ro_description")
    return DescriptionLibraryRegenerateResponse()


@router.get("", response_model=List[RepairOrderResponse])
async def list_repair_orders(
    customer_id: Optional[UUID] = Query(None),
    vehicle_id: Optional[UUID] = Query(None),
    status: Optional[RepairOrderStatus] = Query(None),
    search: Optional[str] = Query(None, description="Filter by order number or description"),
    deleted: bool = Query(False, description="Show only soft-deleted orders (owner/admin only)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if deleted and current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise HTTPException(status_code=403, detail="Access denied")

    query = select(RepairOrder)
    count_query = select(func.count(RepairOrder.id))
    query = query.where(RepairOrder.deleted_at.isnot(None) if deleted else RepairOrder.deleted_at.is_(None))
    count_query = count_query.where(RepairOrder.deleted_at.isnot(None) if deleted else RepairOrder.deleted_at.is_(None))

    if current_user.role == UserRole.CUSTOMER:
        # Customers can only see their own repair orders
        if not current_user.customer_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        query = query.where(RepairOrder.customer_id == current_user.customer_id)
        count_query = count_query.where(RepairOrder.customer_id == current_user.customer_id)
    else:
        # Staff can filter by customer/vehicle/status or see all in tenant
        if not current_user.tenant_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        query = query.where(RepairOrder.tenant_id == current_user.tenant_id)
        count_query = count_query.where(RepairOrder.tenant_id == current_user.tenant_id)
        # Fleet managers only see the garage's own internal-fleet repairs.
        if current_user.role == UserRole.FLEET_MANAGER:
            query = query.where(RepairOrder.is_internal.is_(True))
            count_query = count_query.where(RepairOrder.is_internal.is_(True))
        if customer_id:
            query = query.where(RepairOrder.customer_id == customer_id)
            count_query = count_query.where(RepairOrder.customer_id == customer_id)
    
    if vehicle_id:
        query = query.where(RepairOrder.vehicle_id == vehicle_id)
        count_query = count_query.where(RepairOrder.vehicle_id == vehicle_id)
    if status:
        query = query.where(RepairOrder.status == status)
        count_query = count_query.where(RepairOrder.status == status)
    # Search across the order plus its customer and vehicle: order number,
    # description, customer name/company/DOT/MC/phone, and vehicle VIN/unit/
    # make/model. The Customer/Vehicle joins are added only when a term is
    # present so the common (no-search) list path stays a single-table query.
    # Coerce defensively: `search` is a str|None over HTTP, but is safe here even
    # if a caller (e.g. a direct-function test) leaves it as the Query default.
    search_term = (search if isinstance(search, str) else "").strip()
    if search_term:
        like = f"%{search_term}%"
        # Phone matching only kicks in when the term itself looks like a phone
        # number (all digits after stripping common phone punctuation) — a
        # term with real letters in it (e.g. "77 cargo") is a name/company
        # search, and matching its incidental digits ("77") against every
        # phone number on file would swamp the results with false positives.
        stripped = re.sub(r"[\s().+-]", "", search_term)
        phone_digits = stripped if stripped and stripped.isdigit() else None
        query = query.join(Customer, RepairOrder.customer_id == Customer.id).join(
            Vehicle, RepairOrder.vehicle_id == Vehicle.id
        )
        count_query = count_query.join(Customer, RepairOrder.customer_id == Customer.id).join(
            Vehicle, RepairOrder.vehicle_id == Vehicle.id
        )
        clauses = [
            RepairOrder.order_number.ilike(like),
            RepairOrder.description.ilike(like),
            Customer.first_name.ilike(like),
            Customer.last_name.ilike(like),
            (Customer.first_name + literal_column("' '") + Customer.last_name).ilike(like),
            Customer.company_name.ilike(like),
            Customer.usdot_number.ilike(like),
            Customer.mc_number.ilike(like),
            Vehicle.vin.ilike(like),
            Vehicle.unit_number.ilike(like),
            Vehicle.make.ilike(like),
            Vehicle.model.ilike(like),
        ]
        if phone_digits:
            clauses.append(
                func.regexp_replace(func.coalesce(Customer.phone, ""), r"\D", "", "g").ilike(f"%{phone_digits}%")
            )
        search_clause = or_(*clauses)
        query = query.where(search_clause)
        count_query = count_query.where(search_clause)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(RepairOrder.created_at.desc())
        .options(selectinload(RepairOrder.vehicle), selectinload(RepairOrder.customer))
    )
    orders = result.scalars().all()
    
    # Get quote_sent status for all orders
    order_ids = [o.id for o in orders]
    if order_ids:
        quote_result = await db.execute(
            select(Quote.repair_order_id, Quote.sent_to_customer)
            .where(Quote.repair_order_id.in_(order_ids))
        )
        quote_sent_map = {row[0]: row[1] for row in quote_result.fetchall()}

        invoice_result = await db.execute(
            select(Invoice.repair_order_id, Invoice.status, Invoice.zelle_pending_submitted_at)
            .where(Invoice.repair_order_id.in_(order_ids))
        )
        pending_zelle_map = {
            row[0]: (row[2] is not None and row[1] != InvoiceStatus.PAID)
            for row in invoice_result.fetchall()
        }
    else:
        quote_sent_map = {}
        pending_zelle_map = {}

    # The Deleted view needs "who did this" — resolve actor names in bulk
    # rather than joining on every normal (non-deleted) list request.
    actor_name_map: dict = {}
    if deleted and orders:
        actor_ids = {o.deleted_by_user_id for o in orders if o.deleted_by_user_id}
        actor_ids |= {o.cancelled_by_user_id for o in orders if o.cancelled_by_user_id}
        if actor_ids:
            actor_result = await db.execute(
                select(User.id, User.first_name, User.last_name).where(User.id.in_(actor_ids))
            )
            actor_name_map = {row[0]: f"{row[1]} {row[2]}".strip() for row in actor_result.fetchall()}

    def _vehicle_fields(v) -> dict:
        if not v:
            return {"vehicle_make": "", "vehicle_model": "", "vehicle_year": None, "vehicle_unit_number": None, "vehicle_vin": None}
        return {"vehicle_make": v.make or "", "vehicle_model": v.model or "", "vehicle_year": v.year, "vehicle_unit_number": v.unit_number, "vehicle_vin": v.vin}

    def _customer_fields(c) -> dict:
        if not c:
            return {"customer_first_name": "", "customer_last_name": "", "customer_company_name": None, "customer_email": None, "customer_phone": None}
        return {"customer_first_name": c.first_name or "", "customer_last_name": c.last_name or "", "customer_company_name": c.company_name, "customer_email": c.email, "customer_phone": c.phone}

    _vf_exclude = {
        'quote_sent', 'pending_zelle_confirmation', 'vehicle_make', 'vehicle_model', 'vehicle_year',
        'vehicle_unit_number', 'vehicle_vin', 'cancelled_by_name', 'deleted_by_name',
        'customer_first_name', 'customer_last_name', 'customer_company_name', 'customer_email', 'customer_phone',
    }
    items = [
        RepairOrderResponse(
            **RepairOrderResponse.model_validate(o).model_dump(exclude=_vf_exclude),
            **_vehicle_fields(o.vehicle),
            **_customer_fields(o.customer),
            quote_sent=quote_sent_map.get(o.id),
            pending_zelle_confirmation=pending_zelle_map.get(o.id, False),
            cancelled_by_name=actor_name_map.get(o.cancelled_by_user_id),
            deleted_by_name=actor_name_map.get(o.deleted_by_user_id),
        )
        for o in orders
    ]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.get("/{order_id}/detail", response_model=RepairOrderDetailResponse)
async def get_repair_order_detail(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Owner/admin can open a soft-deleted order's detail (e.g. from the
    # Deleted view, to review before restoring); everyone else gets a 404
    # for a deleted order, same as if it never existed.
    can_see_deleted = current_user.role in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
    deleted_filter = () if can_see_deleted else (RepairOrder.deleted_at.is_(None),)
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, *deleted_filter)
        .options(
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
            selectinload(RepairOrder.labor_items),
            selectinload(RepairOrder.vehicle),
            selectinload(RepairOrder.cancelled_by_user),
            selectinload(RepairOrder.deleted_by_user),
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    parts_resp = [_build_parts_usage_response(pu) for pu in order.parts_usage]
    labor_resp = [LaborResponse.model_validate(li) for li in order.labor_items]

    # Selected PM services (fleet PM work orders). Ordered as chosen.
    from app.db.models.fleet import RepairOrderPMService
    from app.db.models.service import Service as ServiceModel
    from app.schemas.repair_order import RepairOrderPMServiceEntry
    pm_svc_rows = await db.execute(
        select(RepairOrderPMService.service_id, ServiceModel.name, ServiceModel.duration_minutes)
        .join(ServiceModel, ServiceModel.id == RepairOrderPMService.service_id)
        .where(RepairOrderPMService.repair_order_id == order.id)
        .order_by(RepairOrderPMService.sort_order)
    )
    pm_services_resp = [
        RepairOrderPMServiceEntry(service_id=sid, name=name, duration_minutes=dur or 0)
        for sid, name, dur in pm_svc_rows.all()
    ]

    invoice_result = await db.execute(
        select(Invoice).where(Invoice.repair_order_id == order.id).limit(1)
    )
    invoice = invoice_result.scalar_one_or_none()
    pending_zelle_confirmation = bool(
        invoice and invoice.zelle_pending_submitted_at is not None and invoice.status != InvoiceStatus.PAID
    )
    _detail_vf_exclude = {
        'pending_zelle_confirmation', 'vehicle_make', 'vehicle_model', 'vehicle_year',
        'vehicle_unit_number', 'vehicle_vin', 'cancelled_by_name', 'deleted_by_name',
    }
    v = order.vehicle

    def _user_name(u: Optional[User]) -> Optional[str]:
        return f"{u.first_name} {u.last_name}".strip() if u else None

    return RepairOrderDetailResponse(
        **RepairOrderResponse.model_validate(order).model_dump(exclude=_detail_vf_exclude),
        vehicle_make=v.make or "" if v else "",
        vehicle_model=v.model or "" if v else "",
        vehicle_year=v.year if v else None,
        vehicle_unit_number=v.unit_number if v else None,
        vehicle_vin=v.vin if v else None,
        pending_zelle_confirmation=pending_zelle_confirmation,
        cancelled_by_name=_user_name(order.cancelled_by_user),
        deleted_by_name=_user_name(order.deleted_by_user),
        parts_usage=parts_resp,
        labor_items=labor_resp,
        pm_services=pm_services_resp,
    )


@router.get("/{order_id}", response_model=RepairOrderResponse)
async def get_repair_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != order.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != order.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    invoice_result = await db.execute(
        select(Invoice).where(Invoice.repair_order_id == order.id).limit(1)
    )
    invoice = invoice_result.scalar_one_or_none()
    pending_zelle_confirmation = bool(
        invoice and invoice.zelle_pending_submitted_at is not None and invoice.status != InvoiceStatus.PAID
    )

    return RepairOrderResponse(
        **RepairOrderResponse.model_validate(order).model_dump(exclude={'pending_zelle_confirmation'}),
        pending_zelle_confirmation=pending_zelle_confirmation,
    )


@router.put("/{order_id}", response_model=RepairOrderResponse)
async def update_repair_order(
    order_id: UUID,
    order_data: RepairOrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    
    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    cancelling_now = (
        order_data.status == RepairOrderStatus.CANCELLED
        and order.status != RepairOrderStatus.CANCELLED
    )
    if cancelling_now:
        _require_cancelable_ro(order)
        # Cancelling an *early* order (draft/quoted) means the work never happened,
        # so give the parts' stock back and drop the part rows. But once the order
        # is past quoting (approved / in_progress / completed) the parts were
        # really consumed and are part of the job's history — cancelling just marks
        # it cancelled and leaves parts + stock untouched.
        work_never_started = order.status in DANGER_ACTION_RO_STATUSES
        order.cancelled_at = datetime.now(timezone.utc)
        order.cancelled_by_user_id = current_user.id
        if work_never_started:
            parts_result = await db.execute(
                select(PartsUsage)
                .where(PartsUsage.repair_order_id == order_id)
                .options(selectinload(PartsUsage.inventory_item))
            )
            for pu in parts_result.scalars().all():
                if pu.inventory_item is not None:
                    # Restore the same whole-package count that was deducted on add.
                    pu.inventory_item.stock_quantity = (pu.inventory_item.stock_quantity or 0) + _packages_consumed(pu.quantity)
                await db.delete(pu)

    # Update fields
    update_data = order_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(order, field, value)

    # Auto-populate estimated_labor_minutes from selected_services in internal_notes
    if "internal_notes" in update_data and order.internal_notes:
        try:
            import json
            parsed = json.loads(order.internal_notes)
            selected_services = parsed.get("selected_services", [])
            total_est = sum(svc.get("duration_minutes", 0) for svc in selected_services)
            order.estimated_labor_minutes = total_est if total_est > 0 else None
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    
    await db.commit()
    await db.refresh(order)

    # Keep real-time clients in sync for status/workflow edits from the side panel.
    if "status" in update_data or "assigned_mechanic_id" in update_data:
        await broadcast_repair_order_update(
            tenant_id=str(order.tenant_id),
            customer_id=str(order.customer_id),
            order_id=str(order.id),
            order_number=order.order_number,
            status=order.status.value,
            updated_at=order.updated_at.isoformat() if order.updated_at else None,
        )
    
    return RepairOrderResponse.model_validate(order)


class AssignMechanicRequest(BaseModel):
    mechanic_id: UUID


@router.post("/{order_id}/assign-mechanic", response_model=RepairOrderResponse)
async def assign_mechanic(
    order_id: UUID,
    body: AssignMechanicRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.FLEET_MANAGER,
    )),
):
    """Assign/reassign mechanic, set status to assigned when needed, and notify mechanic."""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    # Check if this is a reassignment (mechanic already assigned)
    is_reassignment = order.assigned_mechanic_id is not None
    
    if is_reassignment:
        # Only admins can reassign
        if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop managers can reassign mechanics. Please contact your manager.",
            )
    else:
        # First assignment - customer ROs must be approved. Internal fleet WOs
        # skip the approval flow (draft → in_progress), so allow assigning a
        # mechanic any time before they're frozen.
        if order.is_internal:
            if order.status in INTERNAL_FROZEN_RO_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Can't assign a mechanic after the work order is completed",
                )
        elif order.status != RepairOrderStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only assign mechanic to approved repair orders",
            )
    
    # Verify mechanic exists and belongs to tenant
    result = await db.execute(
        select(User).where(
            and_(
                User.id == body.mechanic_id,
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.MECHANIC,
            )
        )
    )
    mechanic = result.scalar_one_or_none()
    if not mechanic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic not found")
    
    # Assign mechanic and update status
    order.assigned_mechanic_id = body.mechanic_id
    order.assigned_at = datetime.now(timezone.utc)
    # Set status to ASSIGNED if still APPROVED (handles edge cases where previous assignment didn't update status)
    if order.status == RepairOrderStatus.APPROVED:
        order.status = RepairOrderStatus.ASSIGNED
    
    await db.commit()
    await db.refresh(order)
    
    # Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
    )
    
    # Send email notification to MECHANIC (not customer - customer notified when work starts)
    vehicle = order.vehicle
    vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "Vehicle"
    portal_url = f"{settings.FRONTEND_URL.rstrip('/')}/mechanic"
    
    # Parse services from internal_notes
    services_html = ""
    if order.internal_notes:
        try:
            import json
            notes_data = json.loads(order.internal_notes)
            selected_services = notes_data.get("selected_services", [])
            if selected_services:
                services_html = '<ul style="margin: 10px 0; padding-left: 20px;">'
                for svc in selected_services:
                    services_html += f'<li>{svc.get("name", "Service")}</li>'
                services_html += '</ul>'
        except:
            pass
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #d97706; margin: 0;">🔧 DieselBridge Network</h1>
        </div>
        
        <h2 style="color: #333;">New Job Assigned</h2>
        <p>Hi {mechanic.first_name},</p>
        <p>You have been assigned a new repair job. Please acknowledge and start when ready.</p>
        
        <div style="background: #fef3c7; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #fcd34d;">
            <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
            <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
            <p style="margin: 0 0 10px 0;"><strong>Description:</strong> {order.description or 'See services below'}</p>
            {f'<p style="margin: 0;"><strong>Services:</strong>{services_html}</p>' if services_html else ''}
        </div>
        
        <p style="margin: 30px 0; text-align: center;">
            <a href="{portal_url}" 
               style="background-color: #d97706; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                View in Mechanic Portal
            </a>
        </p>
    </body>
    </html>
    """
    
    if mechanic.email:
        await send_email(
            db=db,
            tenant_id=str(current_user.tenant_id),
            to=mechanic.email,
            subject=f"New Job Assigned: {order.order_number} - DieselBridge Network",
            body=html_body,
            template_name="job_assigned",
        )

    if mechanic.phone:
        try:
            await send_sms(
                db=db,
                tenant_id=str(current_user.tenant_id),
                to=mechanic.phone,
                body=(
                    f"New job assigned: Order #{order.order_number} for {vehicle_info}. "
                    f"Portal: {portal_url} - DieselBridge Network"
                ),
                template_name="job_assigned_sms",
            )
        except Exception:
            pass

    return RepairOrderResponse.model_validate(order)


# ============ Mechanic Workflow Endpoints ============

@router.post("/{order_id}/acknowledge", response_model=RepairOrderResponse)
async def acknowledge_job(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic acknowledges job assignment"""
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    
    if order.status != RepairOrderStatus.ASSIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot acknowledge job in '{order.status.value}' status",
        )
    
    order.status = RepairOrderStatus.ACKNOWLEDGED
    order.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)
    
    # Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
    )
    
    return RepairOrderResponse.model_validate(order)


@router.post("/{order_id}/start-work", response_model=RepairOrderStartWorkResponse)
async def start_work(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic starts work - notifies customer"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    
    resume_existing = False
    if order.status in (RepairOrderStatus.ASSIGNED, RepairOrderStatus.ACKNOWLEDGED):
        order.status = RepairOrderStatus.IN_PROGRESS
        order.work_started_at = datetime.now(timezone.utc)
    elif order.status == RepairOrderStatus.IN_PROGRESS:
        resume_existing = True
        if order.work_started_at is None:
            order.work_started_at = datetime.now(timezone.utc)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start work on job in '{order.status.value}' status",
        )

    # Auto-start mechanic repair-order timer (single active timer policy).
    started_session = None
    auto_clocked_in = False
    attendance_session_id: Optional[str] = None
    auto_held_ro = None
    try:
        tenant, mechanic = await fetch_tenant_and_mechanic(
            db,
            tenant_id=order.tenant_id,
            mechanic_id=current_user.id,
        )
        started_session, auto_clocked_in, attendance_session_id, auto_held_ro = await start_session(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            session_type=MechanicSessionType.REPAIR_ORDER.value,
            repair_order_id=order.id,
            stop_previous_reason="auto_switch",
        )
    except Exception:
        # Don't block workflow transition if timer start fails.
        pass

    await db.commit()
    await db.refresh(order)
    
    # Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
    )
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
    try:
        await broadcast_mechanic_timer_update(
            tenant_id=str(order.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(started_session.id) if started_session else str(order.id),
            action="resume_from_repair_order" if resume_existing else "start_from_repair_order",
        )
        if auto_clocked_in and attendance_session_id:
            await broadcast_mechanic_attendance_update(
                tenant_id=str(order.tenant_id),
                mechanic_id=str(current_user.id),
                attendance_session_id=attendance_session_id,
                action="auto_clock_in",
            )
    except Exception:
        pass
    
    if not resume_existing:
        # Notify customer that work has started
        customer = order.customer
        if customer and customer.email:
            vehicle = order.vehicle
            vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "your vehicle"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #d97706; margin: 0;">🔧 DieselBridge Network</h1>
                </div>
                
                <h2 style="color: #333;">Work Has Started!</h2>
                <p>Hi {customer.first_name},</p>
                <p>Great news! Work has begun on your vehicle.</p>
                
                <div style="background: #f0fdf4; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #bbf7d0;">
                    <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
                    <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
                    <p style="margin: 0; font-size: 18px; color: #16a34a;"><strong>Status: In Progress</strong></p>
                </div>
                
                <p>We'll notify you when the work is complete. You can also check your customer portal for updates.</p>
                
                <p style="margin: 30px 0; text-align: center;">
                    <a href="{settings.FRONTEND_URL}/portal" 
                       style="background-color: #d97706; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                        View in Portal
                    </a>
                </p>
            </body>
            </html>
            """
            
            await send_email(
                db=db,
                tenant_id=str(order.tenant_id),
                to=customer.email,
                subject=f"Work Started on {order.order_number} - DieselBridge Network",
                body=html_body,
                template_name="work_started",
            )
        
        # SMS notification
        if customer and customer.phone:
            vehicle = order.vehicle
            vi = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "your vehicle"
            try:
                await send_sms(
                    db,
                    str(order.tenant_id),
                    customer.phone,
                    f"Work has started on your {vi}. Order #{order.order_number}. We'll text you when it's done. - DieselBridge Network",
                    template_name="work_started_sms",
                    customer_id=customer.id,
                    source="automated",
                )
            except Exception:
                pass  # Don't fail the request if SMS fails
    
    return RepairOrderStartWorkResponse(
        **RepairOrderResponse.model_validate(order).model_dump(),
        auto_clocked_in=auto_clocked_in,
    )


HOLD_REASONS = [
    "waiting_for_parts",
    "waiting_for_customer_approval",
    "need_more_info",
    "other",
]

# System-generated hold reasons (not user-selectable)
SYSTEM_HOLD_REASONS = {
    "switched_to_other_ro": "Switched to another repair order",
}


class HoldRequest(BaseModel):
    reason: str


@router.post("/{order_id}/hold", response_model=RepairOrderResponse)
async def hold_repair_order(
    order_id: UUID,
    body: HoldRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic puts an in-progress RO on hold (waiting for parts, customer approval, etc.)"""
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    if order.status != RepairOrderStatus.IN_PROGRESS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot hold job in '{order.status.value}' status")
    if order.hold_reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is already on hold")

    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hold reason is required")

    order.hold_reason = reason
    order.held_at = datetime.now(timezone.utc)

    # Auto-stop the active RO timer for this order.
    stopped_session = None
    active_session = await get_active_session(db, tenant_id=order.tenant_id, mechanic_id=current_user.id)
    if (
        active_session
        and (active_session.session_type.value if hasattr(active_session.session_type, "value") else active_session.session_type)
        == MechanicSessionType.REPAIR_ORDER.value
        and active_session.repair_order_id == order.id
    ):
        stopped_session = await stop_active_session(
            db,
            tenant_id=order.tenant_id,
            mechanic_id=current_user.id,
            actor_user=current_user,
            stop_reason="hold",
        )

    await db.commit()
    await db.refresh(order)

    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
        send_to_customer=False,
    )
    try:
        await broadcast_mechanic_timer_update(
            tenant_id=str(order.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(stopped_session.id) if stopped_session else str(order.id),
            action="hold_repair_order",
        )
    except Exception:
        pass

    return RepairOrderResponse.model_validate(order)


@router.post("/{order_id}/resume", response_model=RepairOrderStartWorkResponse)
async def resume_repair_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic resumes a held RO — clears hold state and restarts the timer."""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    if order.status != RepairOrderStatus.IN_PROGRESS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot resume job in '{order.status.value}' status")
    if not order.hold_reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not on hold")

    order.hold_reason = None
    order.held_at = None

    # Restart the RO timer.
    started_session = None
    auto_clocked_in = False
    attendance_session_id: Optional[str] = None
    auto_held_ro = None
    try:
        tenant, mechanic = await fetch_tenant_and_mechanic(db, tenant_id=order.tenant_id, mechanic_id=current_user.id)
        started_session, auto_clocked_in, attendance_session_id, auto_held_ro = await start_session(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            session_type=MechanicSessionType.REPAIR_ORDER.value,
            repair_order_id=order.id,
            stop_previous_reason="resume_from_hold",
        )
    except Exception:
        pass

    await db.commit()
    await db.refresh(order)

    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
        send_to_customer=False,
    )
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
    try:
        await broadcast_mechanic_timer_update(
            tenant_id=str(order.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(started_session.id) if started_session else str(order.id),
            action="resume_from_hold",
        )
        if auto_clocked_in and attendance_session_id:
            await broadcast_mechanic_attendance_update(
                tenant_id=str(order.tenant_id),
                mechanic_id=str(current_user.id),
                attendance_session_id=attendance_session_id,
                action="auto_clock_in",
            )
    except Exception:
        pass

    return RepairOrderStartWorkResponse(
        **RepairOrderResponse.model_validate(order).model_dump(),
        auto_clocked_in=auto_clocked_in,
    )


@router.post("/{order_id}/complete-work", response_model=RepairOrderResponse)
async def complete_work(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic marks work as complete - awards points and notifies manager"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    
    if order.status != RepairOrderStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete job in '{order.status.value}' status",
        )
    
    order.status = RepairOrderStatus.PENDING_REVIEW
    order.work_completed_at = datetime.now(timezone.utc)
    # Clear hold state if completing from hold
    order.hold_reason = None
    order.held_at = None

    # Auto-stop active repair-order timer for this work order when work completes.
    stopped_session = None
    try:
        active_session = await get_active_session(
            db,
            tenant_id=order.tenant_id,
            mechanic_id=current_user.id,
        )
        if (
            active_session
            and (active_session.session_type.value if hasattr(active_session.session_type, "value") else active_session.session_type)
            == MechanicSessionType.REPAIR_ORDER.value
            and active_session.repair_order_id == order.id
        ):
            stopped_session = await stop_active_session(
                db,
                tenant_id=order.tenant_id,
                mechanic_id=current_user.id,
                actor_user=current_user,
                stop_reason="auto_complete_work",
            )
    except Exception:
        pass

    # Stamp actual tracked and hold/idle minutes on the RO
    try:
        ro_sessions = await db.execute(
            select(MechanicTimeSession).where(
                MechanicTimeSession.repair_order_id == order.id,
                MechanicTimeSession.deleted_at.is_(None),
            )
        )
        total_tracked = 0
        for s in ro_sessions.scalars():
            end = s.ended_at or order.work_completed_at
            total_tracked += int((end - s.started_at).total_seconds() / 60)
        order.actual_tracked_minutes = total_tracked

        if order.work_started_at and order.work_completed_at:
            wall_minutes = int((order.work_completed_at - order.work_started_at).total_seconds() / 60)
            order.total_hold_minutes = max(0, wall_minutes - total_tracked)
    except Exception:
        pass
    
    # ============ AWARD POINTS ============
    # Points = job value (1 point per $1)
    # Use service prices from internal_notes if available, else total_labor_cost
    labor_value = float(order.total_labor_cost or 0)
    
    # Check for services in internal_notes (quote-based orders with service menu prices)
    if order.internal_notes:
        try:
            import json
            notes_data = json.loads(order.internal_notes)
            selected_services = notes_data.get("selected_services", [])
            if selected_services:
                service_total = sum(
                    float(svc.get("base_price", 0))
                    for svc in selected_services
                )
                if service_total > labor_value:
                    labor_value = service_total
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    
    # Get or create balance record
    result = await db.execute(
        select(MechanicPointsBalance).where(
            MechanicPointsBalance.mechanic_id == current_user.id
        )
    )
    balance = result.scalar_one_or_none()
    
    if not balance:
        balance = MechanicPointsBalance(
            tenant_id=current_user.tenant_id,
            mechanic_id=current_user.id,
            available_points=0,
            total_earned=0,
            total_redeemed=0,
            current_streak_days=0,
        )
        db.add(balance)
    
    # Calculate streak multiplier
    today = date.today()
    multiplier = Decimal("1.00")
    
    if balance.last_work_date:
        last_work = balance.last_work_date.date() if hasattr(balance.last_work_date, 'date') else balance.last_work_date
        days_since = (today - last_work).days
        
        if days_since == 0:
            # Same day, keep streak
            pass
        elif days_since == 1:
            # Consecutive day, increment streak
            balance.current_streak_days += 1
        else:
            # Streak broken
            balance.current_streak_days = 1
    else:
        balance.current_streak_days = 1
    
    balance.last_work_date = today
    
    # Apply streak bonus
    if balance.current_streak_days >= 10:
        multiplier = Decimal("1.25")  # 25% bonus after 10 days
    elif balance.current_streak_days >= 5:
        multiplier = Decimal("1.10")  # 10% bonus after 5 days
    
    # Calculate final points
    base_points = int(labor_value)  # 1 point per $1 labor
    final_points = int(base_points * float(multiplier))
    
    # Minimum 10 points per job (even if no labor recorded yet)
    if final_points < 10:
        final_points = 10
        labor_value = 10.0
    
    # Create points transaction
    points_tx = MechanicPoints(
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
        transaction_type=PointsTransactionType.EARNED,
        points=final_points,
        repair_order_id=order.id,
        labor_value=Decimal(str(labor_value)),
        multiplier=multiplier,
        notes=f"Completed {order.order_number}" + (f" (streak x{multiplier})" if multiplier > 1 else ""),
    )
    db.add(points_tx)
    
    # Update balance
    balance.available_points += final_points
    balance.total_earned += final_points
    
    await db.commit()
    await db.refresh(order)
    
    # Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )
    try:
        await broadcast_mechanic_timer_update(
            tenant_id=str(order.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(stopped_session.id) if stopped_session else str(order.id),
            action="stop_from_repair_order",
        )
    except Exception:
        pass
    
    # Notify managers that work is ready for review
    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == order.tenant_id,
                User.role.in_([UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]),
                User.is_active == True,
            )
        )
    )
    managers = result.scalars().all()
    
    vehicle = order.vehicle
    vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "Vehicle"
    
    for manager in managers:
        if manager.email:
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #d97706; margin: 0;">🔧 DieselBridge Network</h1>
                </div>
                
                <h2 style="color: #333;">Work Ready for Review</h2>
                <p>Hi {manager.first_name},</p>
                <p>{current_user.first_name} {current_user.last_name} has completed work on a repair order and it's ready for your review.</p>
                
                <div style="background: #fef3c7; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #fcd34d;">
                    <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
                    <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
                    <p style="margin: 0 0 10px 0;"><strong>Mechanic:</strong> {current_user.first_name} {current_user.last_name}</p>
                    <p style="margin: 0; font-size: 18px; color: #d97706;"><strong>Status: Pending Review</strong></p>
                </div>
                
                <p style="margin: 30px 0; text-align: center;">
                    <a href="{settings.FRONTEND_URL}/dashboard/repair-orders" 
                       style="background-color: #d97706; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                        Review in Dashboard
                    </a>
                </p>
            </body>
            </html>
            """
            
            await send_email(
                db=db,
                tenant_id=str(order.tenant_id),
                to=manager.email,
                subject=f"Review Needed: {order.order_number} - DieselBridge Network",
                body=html_body,
                template_name="work_pending_review",
            )
    
    # SMS to customer: work is done, under review
    customer = order.customer
    if customer and customer.phone:
        vehicle = order.vehicle
        vi = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "your vehicle"
        try:
            await send_sms(
                db,
                str(order.tenant_id),
                customer.phone,
                f"Repair on your {vi} is complete and under review. Order #{order.order_number}. - DieselBridge Network",
                template_name="work_complete_sms",
                customer_id=customer.id,
                source="automated",
            )
        except Exception:
            pass
    
    return RepairOrderResponse.model_validate(order)


class ApproveCompletionRequest(BaseModel):
    review_notes: Optional[str] = None
    mileage_out: Optional[int] = None  # odometer at completion


@router.post("/{order_id}/approve-completion", response_model=RepairOrderResponse)
async def approve_completion(
    order_id: UUID,
    body: Optional[ApproveCompletionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.FLEET_MANAGER,
    )),
):
    """Manager approves completed work - notifies customer"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    if order.status != RepairOrderStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve job in '{order.status.value}' status",
        )
    
    # Record the odometer at completion when provided.
    if body and body.mileage_out is not None:
        order.mileage_out = body.mileage_out

    order.status = RepairOrderStatus.COMPLETED

    # Completing an internal preventive-maintenance order advances the truck's next PM.
    if order.is_internal and order.is_pm:
        veh_result = await db.execute(select(Vehicle).where(Vehicle.id == order.vehicle_id))
        veh = veh_result.scalar_one_or_none()
        if veh:
            from app.services.internal_fleet import advance_vehicle_pm
            advance_vehicle_pm(veh, order.mileage_out)

    # Append review notes to internal_notes if provided
    if body and body.review_notes:
        import json
        from datetime import datetime
        review_entry = {
            "type": "manager_review",
            "notes": body.review_notes,
            "reviewed_by": f"{current_user.first_name} {current_user.last_name}",
            "reviewed_at": datetime.utcnow().isoformat(),
        }
        try:
            existing_notes = json.loads(order.internal_notes) if order.internal_notes else {}
        except json.JSONDecodeError:
            existing_notes = {"raw_notes": order.internal_notes}
        
        if "reviews" not in existing_notes:
            existing_notes["reviews"] = []
        existing_notes["reviews"].append(review_entry)
        order.internal_notes = json.dumps(existing_notes)
    
    await db.commit()
    await db.refresh(order)
    
    # Broadcast WebSocket update (best-effort: never fail a committed approval)
    try:
        await broadcast_repair_order_update(
            tenant_id=str(order.tenant_id),
            customer_id=str(order.customer_id),
            order_id=str(order.id),
            order_number=order.order_number,
            status=order.status.value,
            updated_at=order.updated_at.isoformat() if order.updated_at else None,
        )
    except Exception:
        logger.exception("approve_completion: broadcast failed for order %s", order_id)

    # Notify customer that work is complete
    customer = order.customer
    if customer and customer.email:
        vehicle = order.vehicle
        vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "your vehicle"
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #d97706; margin: 0;">🔧 DieselBridge Network</h1>
            </div>
            
            <h2 style="color: #16a34a;">Work Complete!</h2>
            <p>Hi {customer.first_name},</p>
            <p>Great news! The work on your vehicle has been completed and verified.</p>
            
            <div style="background: #f0fdf4; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #bbf7d0;">
                <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
                <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
                <p style="margin: 0; font-size: 18px; color: #16a34a;"><strong>Status: Completed ✓</strong></p>
            </div>
            
            <p>You can pick up your vehicle or view the invoice in your customer portal.</p>
            
            <p style="margin: 30px 0; text-align: center;">
                <a href="{settings.FRONTEND_URL}/portal" 
                   style="background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                    View in Portal
                </a>
            </p>
            
            <p style="color: #666; font-size: 14px;">
                Thank you for choosing DieselBridge Network!
            </p>
        </body>
        </html>
        """
        
        try:
            await send_email(
                db=db,
                tenant_id=str(order.tenant_id),
                to=customer.email,
                subject=f"Work Complete: {order.order_number} - DieselBridge Network",
                body=html_body,
                template_name="work_complete",
            )
        except Exception:
            logger.exception("approve_completion: work-complete email failed for order %s", order_id)

    # SMS: ready for pickup
    if customer and customer.phone:
        vehicle = order.vehicle
        vi = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "your vehicle"
        try:
            await send_sms(
                db,
                str(order.tenant_id),
                customer.phone,
                f"Your {vi} is ready for pickup! Order #{order.order_number}. Invoice will follow shortly. - DieselBridge Network",
                template_name="ready_pickup_sms",
                customer_id=customer.id,
                source="automated",
            )
        except Exception:
            pass

    # Auto-create invoice immediately so the customer sees the correct total with all fees
    try:
        from app.api.v1.endpoints.invoices import auto_create_invoice_for_order
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == order.tenant_id))
        auto_tenant = tenant_result.scalar_one_or_none()
        if auto_tenant:
            await auto_create_invoice_for_order(db=db, order=order, tenant=auto_tenant, created_by_user_id=current_user.id)
    except Exception:
        logger.exception("Auto-invoice creation failed for order %s", order_id)

    return RepairOrderResponse.model_validate(order)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repair_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id))
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )

    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    _require_deletable_ro(order)

    # Save identifiers before commit so we can broadcast cache invalidation.
    tenant_id = str(order.tenant_id)
    customer_id = str(order.customer_id)
    order_id_str = str(order.id)
    order_number = order.order_number

    # Soft delete: hide the order (and keep its quote/parts/labor/invoice
    # history intact) rather than destroying it, so it can be restored and
    # so there's always a record of who deleted it and when.
    order.deleted_at = datetime.now(timezone.utc)
    order.deleted_by_user_id = current_user.id
    await db.commit()

    # Broadcast deletion so dashboards/lists update without manual refresh.
    await broadcast_repair_order_update(
        tenant_id=tenant_id,
        customer_id=customer_id,
        order_id=order_id_str,
        order_number=order_number,
        status="deleted",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{order_id}/restore", response_model=RepairOrderResponse)
async def restore_repair_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    """Undo a soft delete. Restores the order to whatever status it had
    when deleted — restoring never changes status on its own."""
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id))
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")

    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if order.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Repair order is not deleted")

    order.deleted_at = None
    order.deleted_by_user_id = None

    # A restored internal fleet WO that had been completed comes back workable:
    # reopen it to in_progress so labor/parts can be (re)added. Otherwise a
    # restored-but-completed WO is frozen with no way to edit it. Customer ROs
    # keep their status (they have quotes/invoices tied to completion).
    if order.is_internal and order.status == RepairOrderStatus.COMPLETED:
        order.status = RepairOrderStatus.IN_PROGRESS
        order.work_completed_at = None

    await db.commit()
    await db.refresh(order)

    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )

    return RepairOrderResponse.model_validate(order)


@router.post("/{order_id}/reopen", response_model=RepairOrderResponse)
async def reopen_repair_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    """Reopen a completed internal fleet work order back to in_progress so more
    labor/parts can be added. Internal-only — customer ROs are locked once
    completed because their quote/invoice/payment depends on it."""
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if not order.is_internal:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only internal fleet work orders can be reopened")
    if order.status != RepairOrderStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only completed work orders can be reopened")

    order.status = RepairOrderStatus.IN_PROGRESS
    order.work_completed_at = None
    await db.commit()
    await db.refresh(order)

    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )

    return RepairOrderResponse.model_validate(order)


# --- Helpers for parts/labor and recompute ---


def _check_ro_access(current_user: User, order: RepairOrder) -> None:
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != order.customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    # Fleet managers are scoped to the garage's own internal-fleet repairs only.
    if current_user.role == UserRole.FLEET_MANAGER and not order.is_internal:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _require_cancelable_ro(order: RepairOrder) -> None:
    # Any status can be cancelled except once it's a financial record
    # (invoiced/paid), which must stay in history.
    if order.status in FINANCIALLY_PROTECTED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoiced or paid orders can't be cancelled — they're kept as a financial record.",
        )


def _require_deletable_ro(order: RepairOrder) -> None:
    # Any status can be soft-deleted (and later restored) except once it's a
    # financial record (invoiced/paid). Internal fleet WOs have no invoice/payment
    # so they're never protected.
    if order.status in FINANCIALLY_PROTECTED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoiced or paid orders can't be deleted — they're kept as a financial record.",
        )


def _require_editable_ro(order: RepairOrder) -> None:
    if _is_pricing_locked_for_edits(order):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pricing is locked for this repair order",
        )
    # Internal fleet WOs log labor/parts throughout the active flow; they only
    # freeze once completed/invoiced/cancelled. Customer ROs stay draft/quoted.
    if order.is_internal:
        if order.status in INTERNAL_FROZEN_RO_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parts and labor can't be modified after the work order is completed",
            )
        return
    if order.status not in EDITABLE_RO_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parts and labor can only be modified when repair order is draft or quoted",
        )


async def _recompute_repair_order_totals(db: AsyncSession, order_id: UUID) -> None:
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(
            selectinload(RepairOrder.parts_usage),
            selectinload(RepairOrder.labor_items),
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        return
    total_parts = sum(Decimal(str(pu.total_price)) for pu in order.parts_usage)
    total_labor = sum(Decimal(str(li.total_cost)) for li in order.labor_items)
    order.total_parts_cost = total_parts
    order.total_labor_cost = total_labor
    # Apply manager discounts: labor discount off labor, order discount off total.
    labor_disc = Decimal(str(order.labor_discount_amount or 0))
    order_disc = Decimal(str(order.order_discount_amount or 0))
    labor_net = max(Decimal("0.00"), total_labor - labor_disc)
    order.total_cost = max(Decimal("0.00"), total_parts + labor_net - order_disc)
    await db.commit()


# --- Price Builder ---


@router.get("/{order_id}/price-build", response_model=PriceBuildSummaryResponse)
async def get_price_build_summary(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    try:
        order = await price_build_service.load_order(db, order_id)
        _check_ro_access(current_user, order)
        return _to_price_build_summary(order)
    except Exception as exc:
        raise _map_price_build_error(exc)


@router.post("/{order_id}/price-build/flat-service", response_model=PriceBuildSummaryResponse)
async def add_price_build_flat_service(
    order_id: UUID,
    body: PriceBuildFlatServiceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PRICE_BUILD_EDIT_ROLES)),
):
    try:
        order = await price_build_service.load_order(db, order_id)
        _check_ro_access(current_user, order)
        result = await price_build_service.add_flat_service_line(
            db,
            order,
            body.service_id,
            quantity=body.quantity,
        )
        return _to_price_build_summary(
            result.order,
            warnings=[PriceBuildWarning(code=w.code, message=w.message) for w in result.warnings],
        )
    except Exception as exc:
        raise _map_price_build_error(exc)


@router.post("/{order_id}/price-build/repair-ops/search", response_model=PriceBuildSearchResponse)
async def search_price_build_repair_operations(
    order_id: UUID,
    body: PriceBuildRepairOpsSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    try:
        order = await price_build_service.load_order(db, order_id)
        _check_ro_access(current_user, order)
        candidates, warnings = await price_build_service.search_repair_operations(db, order, body.query)
        return PriceBuildSearchResponse(
            candidates=[
                RepairOperationCandidate(
                    operation_id=c.operation_id,
                    name=c.name,
                    description=c.description,
                    estimated_hours=c.estimated_hours,
                    provider=c.provider,
                )
                for c in candidates
            ],
            warnings=[PriceBuildWarning(code=w.code, message=w.message) for w in warnings],
        )
    except Exception as exc:
        raise _map_price_build_error(exc)


@router.post("/{order_id}/price-build/repair-ops/apply", response_model=PriceBuildSummaryResponse)
async def apply_price_build_repair_operation(
    order_id: UUID,
    body: PriceBuildRepairOpsApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PRICE_BUILD_EDIT_ROLES)),
):
    try:
        order = await price_build_service.load_order(db, order_id)
        _check_ro_access(current_user, order)
        result = await price_build_service.add_repair_operation_line(
            db,
            order,
            operation_id=body.operation_id,
            name=body.name,
            description=body.description,
            estimated_hours=body.estimated_hours,
            provider=body.provider,
            auto_recalc_enabled=body.auto_recalc_enabled,
        )
        return _to_price_build_summary(
            result.order,
            warnings=[PriceBuildWarning(code=w.code, message=w.message) for w in result.warnings],
        )
    except Exception as exc:
        raise _map_price_build_error(exc)


@router.patch("/{order_id}/price-build/lines/{line_id}", response_model=PriceBuildSummaryResponse)
async def update_price_build_line(
    order_id: UUID,
    line_id: UUID,
    body: PriceBuildLineUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PRICE_BUILD_EDIT_ROLES)),
):
    try:
        order = await price_build_service.load_order(db, order_id)
        _check_ro_access(current_user, order)
        result = await price_build_service.update_line(
            db,
            order,
            line_id=line_id,
            description=body.description,
            hours=body.hours,
            hourly_rate=body.hourly_rate,
            auto_recalc_enabled=body.auto_recalc_enabled,
        )
        return _to_price_build_summary(
            result.order,
            warnings=[PriceBuildWarning(code=w.code, message=w.message) for w in result.warnings],
        )
    except Exception as exc:
        raise _map_price_build_error(exc)


@router.delete("/{order_id}/price-build/lines/{line_id}", response_model=PriceBuildSummaryResponse)
async def delete_price_build_line(
    order_id: UUID,
    line_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PRICE_BUILD_EDIT_ROLES)),
):
    try:
        order = await price_build_service.load_order(db, order_id)
        _check_ro_access(current_user, order)
        result = await price_build_service.remove_line(db, order, line_id=line_id)
        return _to_price_build_summary(
            result.order,
            warnings=[PriceBuildWarning(code=w.code, message=w.message) for w in result.warnings],
        )
    except Exception as exc:
        raise _map_price_build_error(exc)


@router.post("/{order_id}/price-build/recalculate", response_model=PriceBuildSummaryResponse)
async def recalculate_price_build(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PRICE_BUILD_EDIT_ROLES)),
):
    try:
        order = await price_build_service.load_order(db, order_id)
        _check_ro_access(current_user, order)
        result = await price_build_service.recalculate_order(db, order)
        return _to_price_build_summary(
            result.order,
            warnings=[PriceBuildWarning(code=w.code, message=w.message) for w in result.warnings],
        )
    except Exception as exc:
        raise _map_price_build_error(exc)


@router.post("/{order_id}/price-build/sublet", response_model=PriceBuildSummaryResponse, status_code=status.HTTP_201_CREATED)
async def add_sublet_to_price_build(
    order_id: UUID,
    body: PriceBuildSubletRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*PRICE_BUILD_EDIT_ROLES)),
):
    try:
        order = await price_build_service.load_order(db, order_id)
        _check_ro_access(current_user, order)
        if not current_user.tenant_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
        # Sublet: we store vendor cost and charge the customer the charge_to_customer amount.
        # hours=1, hourly_rate=charge_to_customer gives total_cost = charge_to_customer.
        labor = Labor(
            tenant_id=current_user.tenant_id,
            repair_order_id=order_id,
            description=body.description,
            hours=Decimal("1"),
            hourly_rate=body.charge_to_customer,
            total_cost=body.charge_to_customer,
            line_type=LaborLineType.SUBLET,
            vendor_name=body.vendor_name,
            vendor_cost=body.vendor_cost,
            auto_recalc_enabled=False,
        )
        db.add(labor)
        await db.commit()
        await db.refresh(labor)
        await _recompute_repair_order_totals(db, order_id)
        order = await price_build_service.load_order(db, order_id)
        return _to_price_build_summary(order)
    except HTTPException:
        raise
    except Exception as exc:
        raise _map_price_build_error(exc)


# --- Parts ---


@router.post("/{order_id}/parts", response_model=PartsUsageResponse, status_code=status.HTTP_201_CREATED)
async def add_parts_to_repair_order(
    order_id: UUID,
    body: PartsUsageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    if order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    result = await db.execute(
        select(Inventory).where(
            and_(
                Inventory.id == body.inventory_id,
                Inventory.tenant_id == current_user.tenant_id,
            )
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
    if body.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be greater than zero")
    packages_needed = _packages_consumed(body.quantity)
    if inv.stock_quantity < packages_needed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock: have {inv.stock_quantity}, requested {body.quantity} ({packages_needed} package(s))",
        )
    # Internal fleet repairs price parts at cost (no markup, no customer-facing list price);
    # customer repairs default to the selling price.
    default_price = inv.cost if order.is_internal else inv.selling_price
    unit_price = body.unit_price if body.unit_price is not None else default_price
    list_price = inv.cost if order.is_internal else inv.selling_price
    total_price = unit_price * body.quantity
    pu = PartsUsage(
        tenant_id=current_user.tenant_id,
        repair_order_id=order_id,
        inventory_id=body.inventory_id,
        quantity=body.quantity,
        unit_cost=inv.cost,
        unit_price=unit_price,
        list_price=list_price,
        total_price=total_price,
        source_service_id=body.source_service_id,
    )
    db.add(pu)
    inv.stock_quantity -= packages_needed
    await db.commit()
    await db.refresh(pu)
    await _recompute_repair_order_totals(db, order_id)
    await db.refresh(pu)
    result = await db.execute(
        select(PartsUsage).where(PartsUsage.id == pu.id).options(selectinload(PartsUsage.inventory_item))
    )
    pu_loaded = result.scalar_one_or_none()
    inv_loaded = pu_loaded.inventory_item if pu_loaded else inv
    return _build_parts_usage_response(pu, inv_loaded)


@router.get("/{order_id}/parts", response_model=List[PartsUsageResponse])
async def list_repair_order_parts(
    order_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)

    total_result = await db.execute(
        select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id == order_id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(PartsUsage)
        .where(PartsUsage.repair_order_id == order_id)
        .options(selectinload(PartsUsage.inventory_item))
        .order_by(PartsUsage.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    parts_usage = result.scalars().all()

    out = [_build_parts_usage_response(pu) for pu in parts_usage]
    return paginated_or_list(out, total, skip, limit, paginated)


@router.get("/{order_id}/parts/suggestions", response_model=PartSuggestionsResponse)
async def get_repair_order_part_suggestions(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Part-tab empty-state suggestions: parts that paired with the operations/
    services already on this order elsewhere in the shop's history, plus the
    tenant's overall most-frequently-used in-stock parts as a fallback."""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(selectinload(RepairOrder.labor_items))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)

    already_added_result = await db.execute(
        select(PartsUsage.inventory_id).where(PartsUsage.repair_order_id == order_id)
    )
    already_added_ids = {row[0] for row in already_added_result.all()}

    service_ids = {li.source_service_id for li in order.labor_items if li.source_service_id}
    operation_ids = {li.provider_operation_id for li in order.labor_items if li.provider_operation_id}

    def _to_suggestions(rows) -> List[PartSuggestion]:
        suggestions: List[PartSuggestion] = []
        for inv, use_count in rows:
            if inv.id in already_added_ids or inv.deleted_at is not None or (inv.stock_quantity or 0) <= 0:
                continue
            suggestions.append(
                PartSuggestion(
                    inventory_id=inv.id,
                    sku=inv.sku,
                    name=inv.name,
                    stock_quantity=inv.stock_quantity,
                    unit_type=inv.unit_type,
                    selling_price=inv.selling_price,
                    use_count=use_count,
                )
            )
        return suggestions[:8]

    for_this_order: List[PartSuggestion] = []
    if service_ids or operation_ids:
        match_clauses = []
        if service_ids:
            match_clauses.append(Labor.source_service_id.in_(service_ids))
        if operation_ids:
            match_clauses.append(Labor.provider_operation_id.in_(operation_ids))
        co_occurring_ro_ids_result = await db.execute(
            select(Labor.repair_order_id)
            .where(
                and_(
                    Labor.tenant_id == current_user.tenant_id,
                    Labor.repair_order_id != order_id,
                    or_(*match_clauses),
                )
            )
            .distinct()
        )
        co_occurring_ro_ids = [row[0] for row in co_occurring_ro_ids_result.all()]
        if co_occurring_ro_ids:
            for_this_order_result = await db.execute(
                select(Inventory, func.count(PartsUsage.id).label("use_count"))
                .join(PartsUsage, PartsUsage.inventory_id == Inventory.id)
                .where(PartsUsage.repair_order_id.in_(co_occurring_ro_ids))
                .group_by(Inventory.id)
                .order_by(func.count(PartsUsage.id).desc())
                .limit(20)
            )
            for_this_order = _to_suggestions(for_this_order_result.all())

    most_used_result = await db.execute(
        select(Inventory, func.count(PartsUsage.id).label("use_count"))
        .join(PartsUsage, PartsUsage.inventory_id == Inventory.id)
        .where(Inventory.tenant_id == current_user.tenant_id)
        .group_by(Inventory.id)
        .order_by(func.count(PartsUsage.id).desc())
        .limit(20)
    )
    most_used = _to_suggestions(most_used_result.all())

    return PartSuggestionsResponse(for_this_order=for_this_order, most_used=most_used)


@router.patch("/{order_id}/parts/{parts_usage_id}", response_model=PartsUsageResponse)
async def update_parts_quantity(
    order_id: UUID,
    parts_usage_id: UUID,
    body: PartsUsageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    if body.quantity is None and body.unit_price is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update")
    if body.quantity is not None and body.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be greater than zero")
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    result = await db.execute(
        select(PartsUsage).where(
            and_(
                PartsUsage.id == parts_usage_id,
                PartsUsage.repair_order_id == order_id,
                PartsUsage.tenant_id == current_user.tenant_id,
            )
        ).options(selectinload(PartsUsage.inventory_item))
    )
    pu = result.scalar_one_or_none()
    if not pu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parts usage not found")

    inv = pu.inventory_item

    if body.quantity is not None:
        # Stock tracks whole packages, so compare packages consumed at the old vs.
        # new quantity rather than the raw fractional delta (e.g. going from 1.0
        # to 1.25 gal still draws from the same already-opened jug).
        old_packages = _packages_consumed(pu.quantity)
        new_packages = _packages_consumed(body.quantity)
        package_delta = new_packages - old_packages
        if inv is not None and package_delta > 0 and (inv.stock_quantity or 0) < package_delta:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for '{inv.name}': have {inv.stock_quantity}, need {package_delta} more package(s)",
            )
        if inv is not None:
            inv.stock_quantity = (inv.stock_quantity or 0) - package_delta
        pu.quantity = body.quantity

    if body.unit_price is not None:
        # Floor at the cost snapshot (or current inventory cost as fallback) — never sell below cost.
        floor = pu.unit_cost if pu.unit_cost is not None else (inv.cost if inv else None)
        if floor is not None and body.unit_price < floor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unit price cannot be lower than cost ({floor})",
            )
        if body.unit_price < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unit price cannot be negative")
        pu.unit_price = body.unit_price

    pu.total_price = pu.unit_price * pu.quantity
    await db.commit()
    await _recompute_repair_order_totals(db, order_id)
    await db.refresh(pu)
    return _build_parts_usage_response(pu, inv)


async def _load_order_for_summary(db: AsyncSession, order_id: UUID) -> RepairOrder:
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)).options(selectinload(RepairOrder.labor_items))
    )
    return result.scalar_one()


@router.post("/{order_id}/parts/pricing-mode", response_model=PriceBuildSummaryResponse)
async def set_parts_pricing_mode(
    order_id: UUID,
    body: PartsPricingModeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    """Bulk-set every part on the order to garage cost ('stock') or list price ('list')."""
    if body.mode not in ("stock", "list"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mode must be 'stock' or 'list'")
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)).options(
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item)
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)

    for pu in order.parts_usage:
        inv = pu.inventory_item
        if body.mode == "stock":
            price = pu.unit_cost if pu.unit_cost is not None else (inv.cost if inv else pu.unit_price)
        else:
            price = pu.list_price if pu.list_price is not None else (inv.selling_price if inv else pu.unit_price)
        # Never below cost.
        floor = pu.unit_cost if pu.unit_cost is not None else (inv.cost if inv else None)
        if floor is not None and price < floor:
            price = floor
        pu.unit_price = price
        pu.total_price = price * pu.quantity
    await db.commit()
    await _recompute_repair_order_totals(db, order_id)
    return _to_price_build_summary(await _load_order_for_summary(db, order_id))


@router.patch("/{order_id}/discounts", response_model=PriceBuildSummaryResponse)
async def update_repair_order_discounts(
    order_id: UUID,
    body: DiscountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    """Set a dollar discount on labor and/or the order total (owner dashboard)."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)).options(
            selectinload(RepairOrder.parts_usage), selectinload(RepairOrder.labor_items)
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)

    parts_total = sum(Decimal(str(pu.total_price)) for pu in order.parts_usage)
    labor_total = sum(Decimal(str(li.total_cost)) for li in order.labor_items)

    if body.labor_discount_amount is not None:
        d = Decimal(str(body.labor_discount_amount)).quantize(Decimal("0.01"))
        if d < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Labor discount cannot be negative")
        if d > labor_total:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Labor discount cannot exceed the labor total (${labor_total})")
        order.labor_discount_amount = d

    if body.order_discount_amount is not None:
        d = Decimal(str(body.order_discount_amount)).quantize(Decimal("0.01"))
        if d < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order discount cannot be negative")
        labor_net = max(Decimal("0.00"), labor_total - Decimal(str(order.labor_discount_amount or 0)))
        subtotal = parts_total + labor_net
        if d > subtotal:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Order discount cannot exceed the order subtotal (${subtotal})")
        order.order_discount_amount = d

    await db.commit()
    await _recompute_repair_order_totals(db, order_id)
    return _to_price_build_summary(await _load_order_for_summary(db, order_id))


@router.delete("/{order_id}/parts/{parts_usage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_parts_from_repair_order(
    order_id: UUID,
    parts_usage_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    result = await db.execute(
        select(PartsUsage).where(
            and_(
                PartsUsage.id == parts_usage_id,
                PartsUsage.repair_order_id == order_id,
                PartsUsage.tenant_id == current_user.tenant_id,
            )
        ).options(selectinload(PartsUsage.inventory_item))
    )
    pu = result.scalar_one_or_none()
    if not pu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parts usage not found")
    inv = pu.inventory_item
    if inv is not None:
        inv.stock_quantity += _packages_consumed(pu.quantity)
    await db.delete(pu)
    await db.commit()
    await _recompute_repair_order_totals(db, order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Labor ---


@router.post("/{order_id}/labor", response_model=LaborResponse, status_code=status.HTTP_201_CREATED)
async def add_labor_to_repair_order(
    order_id: UUID,
    body: LaborCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        *PRICE_BUILD_EDIT_ROLES,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    if order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    total_cost = body.hours * body.hourly_rate
    labor = Labor(
        tenant_id=current_user.tenant_id,
        repair_order_id=order_id,
        description=body.description or "",
        hours=body.hours,
        hourly_rate=body.hourly_rate,
        total_cost=total_cost,
        mechanic_id=body.mechanic_id,
        service_code=body.service_code,
        line_type=body.line_type,
        provider=body.provider,
        provider_operation_id=body.provider_operation_id,
        auto_recalc_enabled=body.auto_recalc_enabled,
        source_service_id=body.source_service_id,
    )
    db.add(labor)
    await db.commit()
    await db.refresh(labor)
    await _recompute_repair_order_totals(db, order_id)
    await db.refresh(labor)
    return LaborResponse.model_validate(labor)


@router.get("/{order_id}/labor", response_model=List[LaborResponse])
async def list_repair_order_labor(
    order_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)

    total_result = await db.execute(
        select(func.count(Labor.id)).where(Labor.repair_order_id == order_id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(Labor)
        .where(Labor.repair_order_id == order_id)
        .order_by(Labor.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    labor_items = result.scalars().all()
    items = [LaborResponse.model_validate(li) for li in labor_items]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.put("/{order_id}/labor/{labor_id}", response_model=LaborResponse)
async def update_repair_order_labor(
    order_id: UUID,
    labor_id: UUID,
    body: LaborUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        *PRICE_BUILD_EDIT_ROLES,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    result = await db.execute(
        select(Labor).where(
            and_(
                Labor.id == labor_id,
                Labor.repair_order_id == order_id,
                Labor.tenant_id == current_user.tenant_id,
            )
        )
    )
    labor = result.scalar_one_or_none()
    if not labor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Labor item not found")
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(labor, field, value)
    if "hours" in update_data or "hourly_rate" in update_data:
        labor.total_cost = labor.hours * labor.hourly_rate
    await db.commit()
    await db.refresh(labor)
    await _recompute_repair_order_totals(db, order_id)
    await db.refresh(labor)
    return LaborResponse.model_validate(labor)


@router.delete("/{order_id}/labor/{labor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_labor_from_repair_order(
    order_id: UUID,
    labor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        *PRICE_BUILD_EDIT_ROLES,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    result = await db.execute(
        select(Labor).where(
            and_(
                Labor.id == labor_id,
                Labor.repair_order_id == order_id,
                Labor.tenant_id == current_user.tenant_id,
            )
        )
    )
    labor = result.scalar_one_or_none()
    if not labor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Labor item not found")
    await db.delete(labor)
    await db.commit()
    await _recompute_repair_order_totals(db, order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Recommended Services ---

RECOMMENDED_SERVICES_ROLES = (
    UserRole.GARAGE_OWNER,
    UserRole.GARAGE_ADMIN,
    UserRole.RECEPTIONIST,
    UserRole.MECHANIC,
    UserRole.FLEET_MANAGER,
)


@router.post(
    "/{order_id}/recommended-services",
    response_model=RecommendedServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_recommended_service(
    order_id: UUID,
    body: RecommendedServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RECOMMENDED_SERVICES_ROLES)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    svc = RecommendedService(
        tenant_id=current_user.tenant_id,
        repair_order_id=order_id,
        description=body.description,
        estimated_cost=body.estimated_cost,
        priority=body.priority,
        notes=body.notes,
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)
    return RecommendedServiceResponse.model_validate(svc)


@router.get("/{order_id}/recommended-services", response_model=List[RecommendedServiceResponse])
async def list_recommended_services(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RECOMMENDED_SERVICES_ROLES)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    svcs_result = await db.execute(
        select(RecommendedService).where(
            and_(
                RecommendedService.repair_order_id == order_id,
                RecommendedService.tenant_id == current_user.tenant_id,
            )
        )
    )
    svcs = svcs_result.scalars().all()
    return [RecommendedServiceResponse.model_validate(s) for s in svcs]


@router.patch("/{order_id}/recommended-services/{service_id}", response_model=RecommendedServiceResponse)
async def update_recommended_service(
    order_id: UUID,
    service_id: UUID,
    body: RecommendedServiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RECOMMENDED_SERVICES_ROLES)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    svc_result = await db.execute(
        select(RecommendedService).where(
            and_(
                RecommendedService.id == service_id,
                RecommendedService.repair_order_id == order_id,
                RecommendedService.tenant_id == current_user.tenant_id,
            )
        )
    )
    svc = svc_result.scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommended service not found")
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(svc, field, value)
    await db.commit()
    await db.refresh(svc)
    return RecommendedServiceResponse.model_validate(svc)


@router.delete("/{order_id}/recommended-services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recommended_service(
    order_id: UUID,
    service_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RECOMMENDED_SERVICES_ROLES)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    svc_result = await db.execute(
        select(RecommendedService).where(
            and_(
                RecommendedService.id == service_id,
                RecommendedService.repair_order_id == order_id,
                RecommendedService.tenant_id == current_user.tenant_id,
            )
        )
    )
    svc = svc_result.scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommended service not found")
    await db.delete(svc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
