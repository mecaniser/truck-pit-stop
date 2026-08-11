import base64
import math
import re
import traceback
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, exists, or_, func, literal_column, case
from sqlalchemy.orm import joinedload, selectinload
from pydantic import BaseModel
from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.search import build_search
from app.core.vehicle_display import vehicle_display_label
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.tenant import Tenant
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor, LaborLineType
from app.db.models.recommended_service import RecommendedService, RecommendedServicePriority
from app.db.models.quote import Quote
from app.db.models.mechanic_points import MechanicPoints, MechanicPointsBalance, PointsTransactionType
from app.db.models.description_library import DescriptionLibraryEntry
from app.db.models.work_photo import WorkPhoto
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.services.email_service import send_email
from app.services.tenant_branding import build_tenant_contact_html, get_tenant_display_name
from app.services.twilio_service import send_sms
from app.services.price_build_service import (
    PriceBuildLockedError,
    PriceBuildNotFoundError,
    PriceBuildService,
    PriceBuildValidationError,
)
from app.services.pricing import get_order_total
from app.services.internal_fleet import fleet_labor_uses_customer_rate, uses_internal_fleet_pricing
from app.services.vehicle_identity import ensure_vehicle_relationship
from app.core.config import settings
from app.core.metrics import record_repair_order_created
from app.core.logging import get_logger
from app.core.phone import normalize_phone
from app.core.websocket import broadcast_repair_order_update
from app.core.websocket import broadcast_mechanic_timer_update
from app.core.websocket import broadcast_mechanic_attendance_update
from app.services.mechanic_time_service import fetch_tenant_and_mechanic, get_active_session, start_session, stop_active_session
from app.services.cloudinary_service import create_direct_image_upload_signature, is_cloudinary_configured, upload_work_photo
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
    RepairOrderPhotoResponse,
    RecommendedServiceCreate,
    RecommendedServiceUpdate,
    RecommendedServiceResponse,
    PartSuggestion,
    PartSuggestionsResponse,
    RepairOrderHistoryEventResponse,
)

logger = get_logger(__name__)

router = APIRouter()
price_build_service = PriceBuildService()

# Work-first is the canonical customer workflow. A repair order is the shop's
# live work record, so parts/labor/pricing stay editable until manager review is
# finalized into an invoice. Quotes are optional authorization snapshots and do
# not freeze the underlying work record.
EDITABLE_RO_STATUSES = (
    RepairOrderStatus.DRAFT,
    RepairOrderStatus.QUOTED,
    RepairOrderStatus.DECLINED,
    RepairOrderStatus.APPROVED,
    RepairOrderStatus.ASSIGNED,
    RepairOrderStatus.ACKNOWLEDGED,
    RepairOrderStatus.IN_PROGRESS,
    RepairOrderStatus.PENDING_REVIEW,
)
ASSIGNABLE_RO_STATUSES = (
    RepairOrderStatus.DRAFT,
    RepairOrderStatus.QUOTED,
    RepairOrderStatus.DECLINED,
    RepairOrderStatus.APPROVED,
    RepairOrderStatus.ASSIGNED,
    RepairOrderStatus.ACKNOWLEDGED,
    RepairOrderStatus.IN_PROGRESS,
)
STARTABLE_WITHOUT_MECHANIC_STATUSES = (
    RepairOrderStatus.DRAFT,
    RepairOrderStatus.QUOTED,
    RepairOrderStatus.DECLINED,
    RepairOrderStatus.APPROVED,
)
DANGER_ACTION_RO_STATUSES = (
    RepairOrderStatus.DRAFT,
    RepairOrderStatus.QUOTED,
    RepairOrderStatus.DECLINED,
    RepairOrderStatus.APPROVED,
    RepairOrderStatus.ASSIGNED,
    RepairOrderStatus.ACKNOWLEDGED,
)
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
ALLOWED_REPAIR_PHOTO_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
MAX_REPAIR_PHOTO_BYTES = 10 * 1024 * 1024
CUSTOMER_VISIBLE_PHOTO_STATUSES = (
    RepairOrderStatus.APPROVED,
    RepairOrderStatus.ASSIGNED,
    RepairOrderStatus.ACKNOWLEDGED,
    RepairOrderStatus.IN_PROGRESS,
    RepairOrderStatus.PENDING_REVIEW,
    RepairOrderStatus.COMPLETED,
    RepairOrderStatus.INVOICED,
    RepairOrderStatus.PAID,
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
    can_edit_work = not pricing_locked and (
        (order.is_internal and order.status not in INTERNAL_FROZEN_RO_STATUSES)
        or (not order.is_internal and order.status in EDITABLE_RO_STATUSES)
    )
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
        can_edit_work=can_edit_work,
        can_assign_technician=(
            not order.is_internal and order.status in ASSIGNABLE_RO_STATUSES
        ),
        can_start_work=(
            order.status in STARTABLE_WITHOUT_MECHANIC_STATUSES
            or order.status in (RepairOrderStatus.ASSIGNED, RepairOrderStatus.ACKNOWLEDGED)
        ),
        can_finalize=order.status == RepairOrderStatus.PENDING_REVIEW,
        lines=labor_resp,
        parts=[_build_parts_usage_response(part) for part in order.parts_usage],
        warnings=warnings or [],
    )


def _is_pricing_locked_for_edits(order: RepairOrder) -> bool:
    if order.pricing_locked_at is None:
        return False
    # Legacy quote sends stamped a lock marker. In the work-first model an
    # estimate never freezes the live repair order, regardless of its status.
    if order.pricing_lock_reason == "quote_sent":
        return False
    return True


def _customer_financials_are_published(order: RepairOrder) -> bool:
    """Live work-order money is staff-only until a final invoice exists."""
    return order.status in (RepairOrderStatus.INVOICED, RepairOrderStatus.PAID)


def _packages_consumed(quantity: Decimal) -> int:
    """Whole packages/jugs a part quantity draws down from stock.

    stock_quantity tracks whole packages on hand (e.g. 5-gal jugs), not
    fractional volume. A fluid quantity of 1.25 gal still opens (and is
    billed against) one jug, so any quantity > 0 rounds up to at least 1
    package; a delta of 0.25 more on an existing line also rounds up to 1
    additional package. We deliberately don't track partial-jug remainders.
    """
    return max(1, math.ceil(quantity)) if quantity > 0 else 0


def _stock_packages_reserved(part: "PartsUsage") -> int:
    """Return the packages this row actually reserved from inventory.

    Older rows predate shortage overrides and have no stored reservation, so
    retain their original whole-package consumption as the safe fallback.
    """
    if part.stock_reserved_packages is not None:
        return max(0, part.stock_reserved_packages)
    return _packages_consumed(part.quantity)


def _insufficient_stock_detail(
    inventory: "Inventory",
    *,
    requested_quantity: Decimal,
    required_packages: int,
    available_packages: int,
) -> dict[str, object]:
    """Stable 400 payload the parts picker can render beside the failed row."""
    return {
        "code": "insufficient_stock",
        "message": (
            f"Insufficient stock: have {available_packages}, requested {requested_quantity} "
            f"({required_packages} package(s))"
        ),
        "inventory_id": str(inventory.id),
        "inventory_name": inventory.name,
        "requested_quantity": str(requested_quantity),
        "required_packages": required_packages,
        "available_packages": available_packages,
        "shortfall_packages": max(0, required_packages - available_packages),
        "can_override": True,
    }


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
        source_line_id=pu.source_line_id,
        stock_shortage_override=bool(pu.stock_shortage_override),
        created_at=pu.created_at,
    )


def _part_unit_label(unit_type: Optional[str]) -> str:
    return {
        "each": "ea",
        "gallon": "gal",
        "quart": "qt",
        "liter": "L",
    }.get(unit_type or "", unit_type or "ea")


def _format_part_quantity(quantity: Decimal) -> str:
    formatted = format(quantity, "f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def _part_history_detail(inventory_name: str, quantity: Decimal, unit_type: Optional[str]) -> str:
    return f"{inventory_name} · {_format_part_quantity(quantity)} {_part_unit_label(unit_type)}"


def _record_repair_order_history_event(
    db: AsyncSession,
    *,
    order: RepairOrder,
    current_user: User,
    event_type: str,
    label: str,
    detail: str,
    entity_id: Optional[UUID] = None,
) -> None:
    actor_name = f"{current_user.first_name} {current_user.last_name}".strip() or current_user.email
    db.add(
        RepairOrderHistoryEvent(
            tenant_id=order.tenant_id,
            repair_order_id=order.id,
            created_at=datetime.now(timezone.utc),
            event_type=event_type,
            label=label,
            detail=detail,
            entity_id=entity_id,
            actor_name=actor_name,
        )
    )


def _uploader_name(user: Optional[User]) -> str:
    if not user:
        return "Unknown"
    return f"{user.first_name} {user.last_name}".strip() or user.email or "Unknown"


def _work_photo_response(photo: WorkPhoto) -> "RepairOrderPhotoResponse":
    return RepairOrderPhotoResponse(
        id=photo.id,
        repair_order_id=photo.repair_order_id,
        image_url=photo.image_url,
        caption=photo.caption,
        uploaded_at=photo.uploaded_at,
        uploader_name=_uploader_name(getattr(photo, "mechanic", None)),
    )


class DirectPhotoUploadSignatureResponse(BaseModel):
    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str
    upload_url: str


class DirectRepairOrderPhotoCreate(BaseModel):
    image_url: str
    public_id: str
    caption: Optional[str] = None


async def _read_validated_repair_image(image: UploadFile) -> tuple[str, str]:
    content_type = (image.content_type or "").lower()
    if content_type not in ALLOWED_REPAIR_PHOTO_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a JPEG, PNG, WebP, HEIC, or HEIF image")
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image file is empty")
    if len(image_bytes) > MAX_REPAIR_PHOTO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large. Max 10MB")
    data_uri = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    return data_uri, content_type


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

    # The physical truck anchors service history. The selected customer is the
    # bill-to account for this visit and need not be the current owner.
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == order_data.vehicle_id,
                Vehicle.tenant_id == current_user.tenant_id,
                Vehicle.deleted_at.is_(None),
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )

    tenant = await db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    uses_internal_pricing = uses_internal_fleet_pricing(customer, tenant)

    is_fleet_vehicle = bool((await db.execute(select(exists(select(FleetMembership.id).where(
        FleetMembership.vehicle_id == vehicle.id,
        FleetMembership.tenant_id == current_user.tenant_id,
        FleetMembership.effective_to.is_(None),
        FleetMembership.deleted_at.is_(None),
    ))))).scalar()) or customer.is_internal_fleet
    if current_user.role == UserRole.FLEET_MANAGER:
        if not is_fleet_vehicle:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Fleet managers can only create work orders for active fleet vehicles",
            )

    await ensure_vehicle_relationship(
        db,
        tenant_id=current_user.tenant_id,
        vehicle_id=vehicle.id,
        customer_id=customer.id,
        relationship_type="default_payer",
    )
    
    # Use retry wrapper to handle rare race conditions on order number
    from app.core.unique_id import create_with_retry
    
    async def create_order_with_number(order_number: str) -> RepairOrder:
        repair_order = RepairOrder(
            tenant_id=current_user.tenant_id,
            order_number=order_number,
            status=RepairOrderStatus.DRAFT,
            # Repairs on the garage's own fleet are internal-cost (no markup/invoice).
            is_internal=uses_internal_pricing,
            is_fleet_work=is_fleet_vehicle,
            bill_labor_at_customer_rate=(
                bool(vehicle.bill_labor_at_customer_rate)
                if uses_internal_pricing else False
            ),
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

    from app.tasks.description_library_refresh import process_on_demand_library_regenerate
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
    """Return a bounded repair-order list from its screen-specific projection.

    The legacy query remains only for databases restored without the projection
    backfill. A healthy migrated tenant takes two bounded queries: one count
    and one indexed projection read, regardless of its invoice/quote history.
    """
    if deleted and current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise HTTPException(status_code=403, detail="Access denied")

    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        projection_filters = [RepairOrderReadModel.customer_id == current_user.customer_id]
        source_filters = [RepairOrder.customer_id == current_user.customer_id]
    else:
        if not current_user.tenant_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        projection_filters = [RepairOrderReadModel.tenant_id == current_user.tenant_id]
        source_filters = [RepairOrder.tenant_id == current_user.tenant_id]
        if current_user.role == UserRole.FLEET_MANAGER:
            projection_filters.append(RepairOrderReadModel.is_internal.is_(True))
            source_filters.append(RepairOrder.is_internal.is_(True))
        if customer_id:
            projection_filters.append(RepairOrderReadModel.customer_id == customer_id)
            source_filters.append(RepairOrder.customer_id == customer_id)

    if vehicle_id:
        projection_filters.append(RepairOrderReadModel.vehicle_id == vehicle_id)
        source_filters.append(RepairOrder.vehicle_id == vehicle_id)
    if status:
        projection_filters.append(RepairOrderReadModel.status == status.value)
        source_filters.append(RepairOrder.status == status)

    projection_filters.append(RepairOrderReadModel.is_deleted.is_(deleted))
    source_filters.append(
        RepairOrder.deleted_at.isnot(None) if deleted else RepairOrder.deleted_at.is_(None)
    )

    # Compare source and projection counts in one query. Any mismatch means a
    # restored database has rows awaiting backfill, so preserve correctness by
    # falling back to the pre-projection implementation for that request.
    source_count, projected_count = (
        await db.execute(
            select(
                func.count(RepairOrder.id),
                func.count(RepairOrderReadModel.repair_order_id),
            )
            .select_from(RepairOrder)
            .outerjoin(
                RepairOrderReadModel,
                RepairOrderReadModel.repair_order_id == RepairOrder.id,
            )
            .where(*source_filters)
        )
    ).one()
    total = source_count or 0
    if total != (projected_count or 0):
        return await _list_repair_orders_legacy(
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            status=status,
            search=search,
            deleted=deleted,
            skip=skip,
            limit=limit,
            paginated=paginated,
            db=db,
            current_user=current_user,
        )

    search_term = (search if isinstance(search, str) else "").strip()
    if search_term:
        compact_term = re.sub(r"[^A-Za-z0-9]", "", search_term)
        search_filters = [RepairOrderReadModel.search_document.ilike(f"%{search_term}%")]
        if compact_term:
            search_filters.append(RepairOrderReadModel.search_compact.ilike(f"%{compact_term}%"))
        projection_filters.append(or_(*search_filters))
        total = (
            await db.execute(
                select(func.count(RepairOrderReadModel.repair_order_id)).where(*projection_filters)
            )
        ).scalar() or 0

    result = await db.execute(
        select(RepairOrderReadModel.payload)
        .where(*projection_filters)
        .order_by(RepairOrderReadModel.created_at.desc(), RepairOrderReadModel.repair_order_id.desc())
        .offset(skip)
        .limit(limit)
    )
    items = [RepairOrderResponse.model_validate(payload) for payload in result.scalars().all()]
    if current_user.role == UserRole.CUSTOMER:
        items = [
            item.model_copy(
                update={
                    "internal_notes": None,
                    "total_parts_cost": Decimal("0.00"),
                    "total_labor_cost": Decimal("0.00"),
                    "total_cost": Decimal("0.00"),
                }
            )
            if item.status not in (RepairOrderStatus.INVOICED, RepairOrderStatus.PAID)
            else item
            for item in items
        ]
    return paginated_or_list(items, total, skip, limit, paginated)


async def _list_repair_orders_legacy(
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
        # Fleet operations may be customer-billed; pricing scope is separate.
        if current_user.role == UserRole.FLEET_MANAGER:
            query = query.where(RepairOrder.is_fleet_work.is_(True))
            count_query = count_query.where(RepairOrder.is_fleet_work.is_(True))
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
    order_by = [RepairOrder.created_at.desc()]
    if search_term:
        full_name = Customer.first_name + literal_column("' '") + Customer.last_name
        query = query.join(Customer, RepairOrder.customer_id == Customer.id).join(
            Vehicle, RepairOrder.vehicle_id == Vehicle.id
        )
        count_query = count_query.join(Customer, RepairOrder.customer_id == Customer.id).join(
            Vehicle, RepairOrder.vehicle_id == Vehicle.id
        )
        # Shared search semantics (see app/core/search.py): ILIKE + separator-
        # squashed IDs (order number / VIN / unit) + pg_trgm typo tolerance on
        # customer name/company and vehicle make, ranked so exact hits lead.
        search_clause, relevance = build_search(
            search_term,
            primary=[
                RepairOrder.order_number,
                Customer.first_name,
                Customer.last_name,
                full_name,
                Customer.company_name,
                Vehicle.vin,
                Vehicle.unit_number,
            ],
            squashed=[RepairOrder.order_number, Vehicle.vin, Vehicle.unit_number],
            secondary=[
                RepairOrder.description,
                Customer.usdot_number,
                Customer.mc_number,
                Vehicle.make,
                Vehicle.model,
            ],
            similarity=[full_name, Customer.company_name, Vehicle.make],
        )
        # Phone matching only kicks in when the term itself looks like a phone
        # number (all digits after stripping common phone punctuation) — a
        # term with real letters in it (e.g. "77 cargo") is a name/company
        # search, and matching its incidental digits ("77") against every
        # phone number on file would swamp the results with false positives.
        stripped = re.sub(r"[\s().+-]", "", search_term)
        if stripped and stripped.isdigit():
            phone_hit = func.regexp_replace(func.coalesce(Customer.phone, ""), r"\D", "", "g").ilike(f"%{stripped}%")
            search_clause = or_(search_clause, phone_hit)
            relevance = func.greatest(relevance, case((phone_hit, 1.0), else_=0.0))
        query = query.where(search_clause)
        count_query = count_query.where(search_clause)
        order_by = [relevance.desc(), RepairOrder.created_at.desc()]

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(*order_by)
        .options(selectinload(RepairOrder.vehicle), selectinload(RepairOrder.customer))
    )
    orders = result.scalars().all()
    
    # Get quote_sent status for all orders
    order_ids = [o.id for o in orders]
    if order_ids:
        quote_result = await db.execute(
            select(Quote.repair_order_id, Quote.sent_to_customer, Quote.sent_at, Quote.is_approved)
            .where(Quote.repair_order_id.in_(order_ids))
            .order_by(Quote.revision.asc())
        )
        quote_rows = quote_result.fetchall()
        quote_sent_map = {row[0]: row[1] for row in quote_rows}
        quote_sent_at_map = {row[0]: row[2] for row in quote_rows}
        quote_approved_map = {row[0]: row[3] for row in quote_rows}

        invoice_result = await db.execute(
            select(
                Invoice.repair_order_id,
                Invoice.status,
                Invoice.zelle_pending_submitted_at,
                Invoice.created_at,
                Invoice.due_date,
            )
            .where(
                Invoice.repair_order_id.in_(order_ids),
                Invoice.status != InvoiceStatus.CANCELLED,
            )
        )
        invoice_rows = invoice_result.fetchall()
        pending_zelle_map = {row[0]: (row[2] is not None and row[1] != InvoiceStatus.PAID) for row in invoice_rows}
        invoice_created_at_map = {row[0]: row[3] for row in invoice_rows}
        invoice_due_date_map = {row[0]: row[4] for row in invoice_rows}
    else:
        quote_sent_map = {}
        quote_sent_at_map = {}
        quote_approved_map = {}
        pending_zelle_map = {}
        invoice_created_at_map = {}
        invoice_due_date_map = {}

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
        'quote_sent', 'quote_approved', 'quote_sent_at', 'invoice_created_at', 'invoice_due_date', 'pending_zelle_confirmation', 'vehicle_make', 'vehicle_model', 'vehicle_year',
        'vehicle_unit_number', 'vehicle_vin', 'cancelled_by_name', 'deleted_by_name',
        'customer_first_name', 'customer_last_name', 'customer_company_name', 'customer_email', 'customer_phone',
    }
    items = [
        RepairOrderResponse(
            **RepairOrderResponse.model_validate(o).model_dump(exclude=_vf_exclude),
            **_vehicle_fields(o.vehicle),
            **_customer_fields(o.customer),
            quote_sent=quote_sent_map.get(o.id),
            quote_approved=quote_approved_map.get(o.id),
            quote_sent_at=quote_sent_at_map.get(o.id),
            invoice_created_at=invoice_created_at_map.get(o.id),
            invoice_due_date=invoice_due_date_map.get(o.id),
            pending_zelle_confirmation=pending_zelle_map.get(o.id, False),
            cancelled_by_name=actor_name_map.get(o.cancelled_by_user_id),
            deleted_by_name=actor_name_map.get(o.deleted_by_user_id),
        )
        for o in orders
    ]
    if current_user.role == UserRole.CUSTOMER:
        for item, order in zip(items, orders):
            item.internal_notes = None
            if not _customer_financials_are_published(order):
                item.total_parts_cost = Decimal("0.00")
                item.total_labor_cost = Decimal("0.00")
                item.total_cost = Decimal("0.00")
                item.labor_discount_amount = Decimal("0.00")
                item.order_discount_amount = Decimal("0.00")
    return paginated_or_list(items, total, skip, limit, paginated)


@router.get("/{order_id}/workspace", response_model=RepairOrderResponse)
async def get_repair_order_workspace(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the compact contract needed to open the repair workspace.

    The full detail route intentionally includes every line item, history event,
    PM service, and invoice state. That is right for the History and legacy
    detail views, but it is needlessly expensive when a dashboard link opens an
    order that is outside the current paginated list. Prefer the same
    transactionally maintained projection that powers the list; retain a
    one-query fallback while a projection is being backfilled.
    """
    projection = await db.scalar(
        select(RepairOrderReadModel)
        .where(RepairOrderReadModel.repair_order_id == order_id)
    )
    if projection:
        item = RepairOrderResponse.model_validate(projection.payload)
        if projection.is_deleted and current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
        if current_user.role == UserRole.CUSTOMER:
            if not current_user.customer_id or current_user.customer_id != projection.customer_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
            if not _customer_financials_are_published(item):
                item.internal_notes = None
                item.total_parts_cost = Decimal("0.00")
                item.total_labor_cost = Decimal("0.00")
                item.total_cost = Decimal("0.00")
                item.labor_discount_amount = Decimal("0.00")
                item.order_discount_amount = Decimal("0.00")
        elif current_user.tenant_id != projection.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        elif current_user.role == UserRole.FLEET_MANAGER and not (item.is_fleet_work or item.is_internal):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return item

    # A new repair order can be opened before the read-model maintainer has
    # written its row. Do not turn that short window into a 404; load only the
    # workspace shell instead of falling through to the heavyweight detail API.
    can_see_deleted = current_user.role in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
    deleted_filter = () if can_see_deleted else (RepairOrder.deleted_at.is_(None),)
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, *deleted_filter)
        .options(joinedload(RepairOrder.customer), joinedload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)

    exclude = {
        "quote_sent", "quote_approved", "quote_sent_at", "invoice_created_at", "invoice_due_date",
        "pending_zelle_confirmation", "vehicle_make", "vehicle_model", "vehicle_year",
        "vehicle_unit_number", "vehicle_vin", "cancelled_by_name", "deleted_by_name",
        "customer_first_name", "customer_last_name", "customer_company_name", "customer_email", "customer_phone",
    }
    vehicle = order.vehicle
    customer = order.customer
    item = RepairOrderResponse(
        **RepairOrderResponse.model_validate(order).model_dump(exclude=exclude),
        vehicle_make=vehicle.make or "" if vehicle else "",
        vehicle_model=vehicle.model or "" if vehicle else "",
        vehicle_year=vehicle.year if vehicle else None,
        vehicle_unit_number=vehicle.unit_number if vehicle else None,
        vehicle_vin=vehicle.vin if vehicle else None,
        customer_first_name=customer.first_name or "" if customer else "",
        customer_last_name=customer.last_name or "" if customer else "",
        customer_company_name=customer.company_name if customer else None,
        customer_email=customer.email if customer else None,
        customer_phone=customer.phone if customer else None,
    )
    if current_user.role == UserRole.CUSTOMER and not _customer_financials_are_published(order):
        item.internal_notes = None
        item.total_parts_cost = Decimal("0.00")
        item.total_labor_cost = Decimal("0.00")
        item.total_cost = Decimal("0.00")
        item.labor_discount_amount = Decimal("0.00")
        item.order_discount_amount = Decimal("0.00")
    return item


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
            selectinload(RepairOrder.customer),
            selectinload(RepairOrder.vehicle),
            selectinload(RepairOrder.cancelled_by_user),
            selectinload(RepairOrder.deleted_by_user),
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    customer_financials_hidden = (
        current_user.role == UserRole.CUSTOMER
        and not _customer_financials_are_published(order)
    )
    parts_resp = [] if customer_financials_hidden else [_build_parts_usage_response(pu) for pu in order.parts_usage]
    labor_resp = [] if customer_financials_hidden else [LaborResponse.model_validate(li) for li in order.labor_items]
    history_result = await db.execute(
        select(RepairOrderHistoryEvent)
        .where(
            RepairOrderHistoryEvent.repair_order_id == order.id,
            RepairOrderHistoryEvent.tenant_id == order.tenant_id,
            RepairOrderHistoryEvent.deleted_at.is_(None),
        )
        .order_by(RepairOrderHistoryEvent.created_at.asc())
    )
    history_resp = [RepairOrderHistoryEventResponse.model_validate(event) for event in history_result.scalars().all()]

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
        select(Invoice)
        .where(
            Invoice.repair_order_id == order.id,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
        .order_by(Invoice.created_at.desc())
        .limit(1)
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

    detail_base = RepairOrderResponse.model_validate(order).model_dump(exclude=_detail_vf_exclude)
    customer = order.customer
    detail_base.update({
        "customer_first_name": customer.first_name or "" if customer else "",
        "customer_last_name": customer.last_name or "" if customer else "",
        "customer_company_name": customer.company_name if customer else None,
        "customer_email": customer.email if customer else None,
        "customer_phone": customer.phone if customer else None,
    })
    if current_user.role == UserRole.CUSTOMER:
        detail_base["internal_notes"] = None
    if customer_financials_hidden:
        detail_base.update({
            "total_parts_cost": Decimal("0.00"),
            "total_labor_cost": Decimal("0.00"),
            "total_cost": Decimal("0.00"),
            "labor_discount_amount": Decimal("0.00"),
            "order_discount_amount": Decimal("0.00"),
        })

    return RepairOrderDetailResponse(
        **detail_base,
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
        history_events=history_resp,
        pm_services=pm_services_resp,
    )


@router.get("/{order_id}/photos", response_model=List[RepairOrderPhotoResponse])
async def list_repair_order_photos(
    order_id: UUID,
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
    if current_user.role == UserRole.CUSTOMER and order.status not in CUSTOMER_VISIBLE_PHOTO_STATUSES:
        return []

    photo_result = await db.execute(
        select(WorkPhoto)
        .where(WorkPhoto.repair_order_id == order.id)
        .options(selectinload(WorkPhoto.mechanic))
        .order_by(WorkPhoto.uploaded_at.desc())
    )
    return [_work_photo_response(photo) for photo in photo_result.scalars().all()]


@router.post("/{order_id}/photos", response_model=RepairOrderPhotoResponse, status_code=status.HTTP_201_CREATED)
async def upload_repair_order_photo(
    order_id: UUID,
    image: UploadFile = File(...),
    caption: Optional[str] = Form(None, max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)

    if not is_cloudinary_configured():
        raise HTTPException(
            status_code=424,
            detail="Photo upload service is not configured. Add Cloudinary settings before uploading photos.",
        )

    data_uri, _content_type = await _read_validated_repair_image(image)
    try:
        image_url = await upload_work_photo(
            base64_image=data_uri,
            repair_order_id=str(order.id),
            mechanic_id=str(current_user.id),
        )
    except Exception as exc:
        logger.error(
            "repair_order_photo_upload_failed",
            repair_order_id=str(order.id),
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=424,
            detail="Photo upload service failed. Check the Cloudinary settings and try again.",
        ) from exc

    photo = WorkPhoto(
        repair_order_id=order.id,
        mechanic_id=current_user.id,
        image_url=image_url,
        caption=caption,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    await db.refresh(photo, attribute_names=["mechanic"])
    return _work_photo_response(photo)


@router.post("/{order_id}/photos/direct-upload-signature", response_model=DirectPhotoUploadSignatureResponse)
async def create_repair_order_photo_upload_signature(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)

    if not is_cloudinary_configured():
        raise HTTPException(
            status_code=424,
            detail="Photo upload service is not configured. Add Cloudinary settings before uploading photos.",
        )

    return create_direct_image_upload_signature(f"work_photos/{order.id}")


@router.post("/{order_id}/photos/direct", response_model=RepairOrderPhotoResponse, status_code=status.HTTP_201_CREATED)
async def create_repair_order_photo_from_direct_upload(
    order_id: UUID,
    body: DirectRepairOrderPhotoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)

    expected_folder = f"work_photos/{order.id}/"
    if not body.public_id.startswith(expected_folder):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded photo does not belong to this repair order")

    photo = WorkPhoto(
        repair_order_id=order.id,
        mechanic_id=current_user.id,
        image_url=body.image_url,
        cloudinary_public_id=body.public_id,
        caption=body.caption.strip() if body.caption else None,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    await db.refresh(photo, attribute_names=["mechanic"])
    return _work_photo_response(photo)


@router.delete("/{order_id}/photos/{photo_id}")
async def delete_repair_order_photo(
    order_id: UUID,
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*RO_MANAGE_ROLES)),
):
    result = await db.execute(
        select(WorkPhoto, RepairOrder)
        .join(RepairOrder, WorkPhoto.repair_order_id == RepairOrder.id)
        .where(
            WorkPhoto.id == photo_id,
            WorkPhoto.repair_order_id == order_id,
            RepairOrder.deleted_at.is_(None),
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    photo, order = row
    _check_ro_access(current_user, order)

    if current_user.role == UserRole.MECHANIC and photo.mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Can only delete your own photos")

    await db.delete(photo)
    await db.commit()
    return {"message": "Photo deleted"}


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
        select(Invoice)
        .where(
            Invoice.repair_order_id == order.id,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
        .order_by(Invoice.created_at.desc())
        .limit(1)
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
                    # Restore exactly what this part row actually reserved.
                    pu.inventory_item.stock_quantity = (pu.inventory_item.stock_quantity or 0) + _stock_packages_reserved(pu)
                await db.delete(pu)

    update_data = order_data.model_dump(exclude_unset=True)
    attribution_fields = {
        "lead_source_channel", "external_lead_id", "callrail_call_id", "google_click_id",
        "gbraid", "wbraid", "landing_page_url", "utm_source", "utm_medium",
        "utm_campaign", "utm_term", "utm_content",
    }
    if attribution_fields.intersection(update_data) and order.status in (RepairOrderStatus.INVOICED, RepairOrderStatus.PAID):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Attribution is locked after invoice finalization")

    # Update fields
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


@router.post("/{order_id}/override-start-work", response_model=RepairOrderResponse)
async def override_start_work_without_mechanic(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
    )),
):
    """Owner/admin: start active customer work without assigning a mechanic."""
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

    if order.is_internal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the internal work order start action for fleet work orders",
        )

    if order.assigned_mechanic_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This repair order already has an assigned mechanic",
        )

    if order.status not in STARTABLE_WITHOUT_MECHANIC_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Work can only be started from an active checked-in repair order",
        )

    order.status = RepairOrderStatus.IN_PROGRESS
    if order.work_started_at is None:
        order.work_started_at = datetime.now(timezone.utc)
    _record_repair_order_history_event(
        db,
        order=order,
        current_user=current_user,
        event_type="admin_override_started_work",
        label="Work started by admin override",
        detail="Technician assignment was bypassed; work is being handled outside the mechanic portal.",
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
    )

    return RepairOrderResponse.model_validate(order)


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
        # First assignment is an operational action. Customer quote approval is
        # optional and must not gate putting a checked-in truck into a bay.
        if order.is_internal:
            if order.status in INTERNAL_FROZEN_RO_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Can't assign a mechanic after the work order is completed",
                )
        elif order.status not in ASSIGNABLE_RO_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can't assign a technician after the repair order is finalized",
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
    # Any intake/authorization state becomes operationally assigned. Existing
    # in-progress work remains in progress when it is reassigned.
    if order.status in (
        RepairOrderStatus.DRAFT,
        RepairOrderStatus.QUOTED,
        RepairOrderStatus.DECLINED,
        RepairOrderStatus.APPROVED,
        RepairOrderStatus.ACKNOWLEDGED,
    ):
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
    shop_name = await get_tenant_display_name(db, order.tenant_id)
    
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
                    f"Portal: {portal_url} - {shop_name}"
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
    await db.refresh(order, attribute_names=["customer", "vehicle"])
    
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
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == order.tenant_id))
        email_tenant = tenant_result.scalar_one_or_none()
        shop_name = email_tenant.name.strip() if email_tenant and email_tenant.name and email_tenant.name.strip() else "Your repair shop"
        shop_contact_html = build_tenant_contact_html(email_tenant)
        if customer and customer.email:
            vehicle = order.vehicle
            vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "your vehicle"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #d97706; margin: 0;">🔧 {shop_name}</h1>
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
                {shop_contact_html}
            </body>
            </html>
            """
            
            await send_email(
                db=db,
                tenant_id=str(order.tenant_id),
                to=customer.email,
                subject=f"Work Started on {order.order_number} - {shop_name}",
                body=html_body,
                template_name="work_started",
                sender_name=shop_name,
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
                    f"Work has started on your {vi}. Order #{order.order_number}. We'll text you when it's done. - {shop_name}",
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
    await db.refresh(order, attribute_names=["customer", "vehicle"])
    
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
    shop_name = await get_tenant_display_name(db, order.tenant_id)
    
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
                f"Repair on your {vi} is complete and under review. Order #{order.order_number}. - {shop_name}",
                template_name="work_complete_sms",
                customer_id=customer.id,
                source="automated",
            )
        except Exception:
            pass
    
    return RepairOrderResponse.model_validate(order)


@router.post("/{order_id}/admin-complete-work", response_model=RepairOrderResponse)
async def admin_complete_unassigned_work(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    """Admin marks an override-started customer repair order ready for review."""
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

    if order.is_internal:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use the internal work order completion flow")

    if order.assigned_mechanic_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned repair orders must be completed by the technician")

    if order.status != RepairOrderStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete job in '{order.status.value}' status",
        )

    order.status = RepairOrderStatus.PENDING_REVIEW
    order.work_completed_at = datetime.now(timezone.utc)
    order.hold_reason = None
    order.held_at = None
    _record_repair_order_history_event(
        db,
        order=order,
        current_user=current_user,
        event_type="admin_completed_work",
        label="Work marked complete by admin",
        detail="Admin completed override-started work without a technician assignment.",
    )

    await db.commit()
    await db.refresh(order)
    await db.refresh(order, attribute_names=["customer", "vehicle"])

    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )

    customer = order.customer
    if customer and customer.phone:
        vehicle = order.vehicle
        vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "your vehicle"
        shop_name = await get_tenant_display_name(db, order.tenant_id)
        try:
            await send_sms(
                db,
                str(order.tenant_id),
                customer.phone,
                f"Repair on your {vehicle_info} is complete and under review. Order #{order.order_number}. - {shop_name}",
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
    """Finalize reviewed work, lock pricing, create the invoice, and notify the customer."""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
        .with_for_update()
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

    # Estimates are optional in the work-first model. Once the shop chooses to
    # send one, however, finalization must honor the customer's immutable
    # authorization history. Added cost is approved through a later revision;
    # the original approval is never reset.
    if not order.is_internal:
        sent_quote_result = await db.execute(
            select(Quote)
            .where(
                Quote.repair_order_id == order.id,
                Quote.sent_to_customer.is_(True),
            )
            .order_by(Quote.revision.desc())
            .limit(1)
        )
        latest_sent_quote = sent_quote_result.scalar_one_or_none()
        approved_quote_result = await db.execute(
            select(Quote)
            .where(
                Quote.repair_order_id == order.id,
                Quote.is_approved.is_(True),
            )
            .order_by(Quote.revision.desc())
            .limit(1)
        )
        latest_approved_quote = approved_quote_result.scalar_one_or_none()
        authorized_total = (
            Decimal(str(latest_approved_quote.total_amount))
            if latest_approved_quote
            else Decimal("0.00")
        )
        current_total = get_order_total(order)
        if latest_sent_quote and current_total > authorized_total + Decimal("0.005"):
            additional_amount = current_total - authorized_total
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Customer authorization is required before finalization. "
                    f"Request approval for the additional ${additional_amount:,.2f}."
                ),
            )
    
    # Record the odometer at completion when provided.
    if body and body.mileage_out is not None:
        order.mileage_out = body.mileage_out

    order.status = RepairOrderStatus.COMPLETED
    # Finalization is the financial lock boundary in the work-first model.
    # Quotes never lock pricing; manager approval does.
    order.pricing_locked_at = datetime.now(timezone.utc)
    order.pricing_lock_reason = "invoice_finalized"
    if order.assigned_mechanic_id is None:
        _record_repair_order_history_event(
            db,
            order=order,
            current_user=current_user,
            event_type="admin_approved_completion",
            label="Completion approved by admin",
            detail="Admin reviewed and approved work completed outside the mechanic portal.",
        )

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
        review_entry = {
            "type": "manager_review",
            "notes": body.review_notes,
            "reviewed_by": f"{current_user.first_name} {current_user.last_name}",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            existing_notes = json.loads(order.internal_notes) if order.internal_notes else {}
        except json.JSONDecodeError:
            existing_notes = {"raw_notes": order.internal_notes}
        
        if "reviews" not in existing_notes:
            existing_notes["reviews"] = []
        existing_notes["reviews"].append(review_entry)
        order.internal_notes = json.dumps(existing_notes)
    
    invoice = None
    invoice_tenant = None
    invoice_email_queued = False
    if not order.is_internal:
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == order.tenant_id))
        invoice_tenant = tenant_result.scalar_one_or_none()
        if not invoice_tenant:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to finalize repair order because the shop configuration is missing",
            )
        try:
            from app.api.v1.endpoints.invoices import (
                auto_create_invoice_for_order,
                enqueue_invoice_created_email,
            )

            invoice = await auto_create_invoice_for_order(
                db=db,
                order=order,
                tenant=invoice_tenant,
                created_by_user_id=current_user.id,
                commit=False,
                notify=False,
            )
            if invoice is None:
                raise RuntimeError("A repair order in quality review already has an invoice")
            invoice_email_queued = await enqueue_invoice_created_email(
                db,
                invoice=invoice,
                order=order,
                tenant=invoice_tenant,
            )
        except Exception as error:
            await db.rollback()
            logger.exception("approve_completion: atomic invoice creation failed for order %s", order_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to finalize the repair order. No changes were saved; please try again.",
            ) from error

    # One commit owns the manager review, PM update, pricing lock, immutable
    # invoice snapshot, and final status. Any error above rolls everything back.
    await db.commit()
    await db.refresh(order)
    await db.refresh(order, attribute_names=["customer", "vehicle"])
    if invoice is not None:
        await db.refresh(invoice)

    # Provider and websocket I/O happens only after the financial record is
    # durable. Failures are logged and can be retried without recreating it.
    if invoice is not None and invoice_tenant is not None:
        try:
            from app.api.v1.endpoints.invoices import notify_invoice_created

            await notify_invoice_created(
                db,
                invoice=invoice,
                order=order,
                tenant=invoice_tenant,
                email_queued=invoice_email_queued,
            )
        except Exception:
            logger.exception("approve_completion: invoice notification failed for order %s", order_id)
    else:
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

    customer = order.customer
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == order.tenant_id))
    email_tenant = tenant_result.scalar_one_or_none()
    shop_name = email_tenant.name.strip() if email_tenant and email_tenant.name and email_tenant.name.strip() else "Your repair shop"

    # SMS: ready for pickup
    if customer and customer.phone:
        vehicle = order.vehicle
        vi = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "your vehicle"
        completion_message = (
            f"Your {vi} is ready for pickup! Order #{order.order_number}. Your final invoice is now available. - {shop_name}"
            if invoice is not None
            else f"Work on your {vi} is complete! Order #{order.order_number}. - {shop_name}"
        )
        try:
            await send_sms(
                db,
                str(order.tenant_id),
                customer.phone,
                completion_message,
                template_name="ready_pickup_sms",
                customer_id=customer.id,
                source="automated",
            )
        except Exception:
            pass

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
    #
    # Stock: an order that never reached the shop floor (draft/quoted) was
    # holding its parts reserved — deleting it must give that stock back, or the
    # parts stay silently deducted for an order nobody will ever work. Past that
    # point the parts were really consumed, so leave stock alone.
    #
    # We only adjust stock, never drop the PartsUsage rows: delete is
    # *restorable*, and restore re-deducts (see restore_repair_order). Dropping
    # the rows would make the undo lossy.
    if order.status in DANGER_ACTION_RO_STATUSES:
        await _release_reserved_stock(db, order.id)

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


class RepairOrderRestoreResponse(BaseModel):
    """The restored order, plus any parts that couldn't be re-reserved because
    stock ran out while the order was deleted."""
    order: RepairOrderResponse
    stock_shortages: List[str] = []


@router.post("/{order_id}/restore", response_model=RepairOrderRestoreResponse)
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

    # Mirror the delete: if we released this order's reserved stock when it was
    # deleted (draft/quoted only), take it back now. Another order may have
    # consumed those parts in the meantime, so collect any shortfalls and hand
    # them back to the caller instead of silently driving stock negative.
    stock_shortages: list[str] = []
    if order.status in DANGER_ACTION_RO_STATUSES:
        stock_shortages = await _reserve_stock_again(db, order.id)

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

    return RepairOrderRestoreResponse(
        order=RepairOrderResponse.model_validate(order),
        stock_shortages=stock_shortages,
    )


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
    if current_user.role == UserRole.FLEET_MANAGER and not (order.is_fleet_work or order.is_internal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _release_reserved_stock(db: AsyncSession, order_id: UUID) -> None:
    """Give back the stock an order's parts were holding, without dropping the
    PartsUsage rows (soft delete is restorable — see _reserve_stock_again)."""
    result = await db.execute(
        select(PartsUsage)
        .where(PartsUsage.repair_order_id == order_id)
        .options(selectinload(PartsUsage.inventory_item))
    )
    for pu in result.scalars().all():
        if pu.inventory_item is not None:
            # Give back only the packages this row actually reserved.
            pu.inventory_item.stock_quantity = (pu.inventory_item.stock_quantity or 0) + _stock_packages_reserved(pu)


async def _reserve_stock_again(db: AsyncSession, order_id: UUID) -> list[str]:
    """Re-deduct the stock an order's parts need when it's restored.

    While the order sat deleted its parts were back on the shelf, so another
    order may have taken them. Re-deduct what's actually there and report the
    shortfalls so the caller can warn the user rather than silently driving
    stock negative.
    """
    result = await db.execute(
        select(PartsUsage)
        .where(PartsUsage.repair_order_id == order_id)
        .options(selectinload(PartsUsage.inventory_item))
    )
    shortages: list[str] = []
    for pu in result.scalars().all():
        inv = pu.inventory_item
        if inv is None:
            continue
        needed = _stock_packages_reserved(pu)
        available = inv.stock_quantity or 0
        if available < needed:
            shortages.append(f"{inv.name} (need {needed}, {available} in stock)")
            inv.stock_quantity = 0
            pu.stock_reserved_packages = available
            pu.stock_shortage_override = True
        else:
            inv.stock_quantity = available - needed
    return shortages


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
    # Internal and customer work records remain editable throughout the active
    # repair lifecycle. Finalization/invoicing is the financial lock boundary.
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
            detail="Parts and labor can't be modified after the repair order is finalized",
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
    _apply_repair_order_totals(order)
    await db.commit()


def _apply_repair_order_totals(
    order: RepairOrder,
    *,
    parts_total: Optional[Decimal] = None,
    labor_total: Optional[Decimal] = None,
) -> None:
    """Update totals from relationships that are already loaded on ``order``."""
    if parts_total is None:
        parts_total = sum(Decimal(str(pu.total_price)) for pu in order.parts_usage)
    if labor_total is None:
        labor_total = sum(Decimal(str(li.total_cost)) for li in order.labor_items)
    order.total_parts_cost = parts_total
    order.total_labor_cost = labor_total
    # Apply manager discounts: labor discount off labor, order discount off total.
    labor_disc = Decimal(str(order.labor_discount_amount or 0))
    order_disc = Decimal(str(order.order_discount_amount or 0))
    labor_net = max(Decimal("0.00"), labor_total - labor_disc)
    order.total_cost = max(Decimal("0.00"), parts_total + labor_net - order_disc)


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
            warnings=[PriceBuildWarning(code=w.code, message=w.message, line_id=w.line_id) for w in result.warnings],
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
            warnings=[PriceBuildWarning(code=w.code, message=w.message, line_id=w.line_id) for w in warnings],
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
            warnings=[PriceBuildWarning(code=w.code, message=w.message, line_id=w.line_id) for w in result.warnings],
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
            warnings=[PriceBuildWarning(code=w.code, message=w.message, line_id=w.line_id) for w in result.warnings],
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
            warnings=[PriceBuildWarning(code=w.code, message=w.message, line_id=w.line_id) for w in result.warnings],
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
            warnings=[PriceBuildWarning(code=w.code, message=w.message, line_id=w.line_id) for w in result.warnings],
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
    if body.source_line_id is not None:
        line_result = await db.execute(
            select(Labor.id).where(
                and_(
                    Labor.id == body.source_line_id,
                    Labor.repair_order_id == order_id,
                    Labor.tenant_id == current_user.tenant_id,
                )
            )
        )
        if line_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Labor line not found on this order")
    packages_needed = _packages_consumed(body.quantity)
    available_packages = max(0, inv.stock_quantity or 0)
    if available_packages < packages_needed and not body.allow_stock_shortage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_insufficient_stock_detail(
                inv,
                requested_quantity=body.quantity,
                required_packages=packages_needed,
                available_packages=available_packages,
            ),
        )
    # Fleet parts are always billed at inventory cost. The truck's pricing
    # preference changes labor only; non-fleet repairs use selling price.
    default_price = inv.cost if order.is_internal else inv.selling_price
    unit_price = body.unit_price if body.unit_price is not None else default_price
    list_price = inv.cost if order.is_internal else inv.selling_price
    total_price = unit_price * body.quantity
    reserved_packages = min(available_packages, packages_needed)
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
        source_line_id=body.source_line_id,
        stock_reserved_packages=reserved_packages,
        stock_shortage_override=reserved_packages < packages_needed,
    )
    db.add(pu)
    await db.flush()
    inv.stock_quantity = available_packages - reserved_packages
    _record_repair_order_history_event(
        db,
        order=order,
        current_user=current_user,
        event_type="part_added",
        label="Part added with stock override" if pu.stock_shortage_override else "Part added to repair order",
        detail=_part_history_detail(inv.name, body.quantity, inv.unit_type),
        entity_id=pu.id,
    )
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
    old_quantity = pu.quantity

    if body.quantity is not None:
        # Stock tracks whole packages. Compare the reservation held by this row
        # to the new requirement rather than raw fractional quantity, because an
        # earlier shortage override may have reserved fewer packages than were
        # billed on the repair order.
        old_reserved_packages = _stock_packages_reserved(pu)
        new_packages = _packages_consumed(body.quantity)
        if inv is not None:
            available_packages = max(0, inv.stock_quantity or 0)
            additional_packages = max(0, new_packages - old_reserved_packages)
            if additional_packages > available_packages and not body.allow_stock_shortage:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=_insufficient_stock_detail(
                        inv,
                        requested_quantity=body.quantity,
                        required_packages=new_packages,
                        available_packages=available_packages + old_reserved_packages,
                    ),
                )
            reserved_packages = min(new_packages, old_reserved_packages + available_packages)
            if reserved_packages >= old_reserved_packages:
                inv.stock_quantity = available_packages - (reserved_packages - old_reserved_packages)
            else:
                inv.stock_quantity = available_packages + (old_reserved_packages - reserved_packages)
            pu.stock_reserved_packages = reserved_packages
            pu.stock_shortage_override = reserved_packages < new_packages
        else:
            pu.stock_reserved_packages = 0
            pu.stock_shortage_override = new_packages > 0
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
    if body.quantity is not None and body.quantity != old_quantity:
        override_update = body.allow_stock_shortage and bool(pu.stock_shortage_override)
        _record_repair_order_history_event(
            db,
            order=order,
            current_user=current_user,
            event_type="part_quantity_updated",
            label="Part quantity updated with stock override" if override_update else "Part quantity updated",
            detail=(
                f"{inv.name if inv else 'Part'} · "
                f"{_format_part_quantity(old_quantity)} {_part_unit_label(inv.unit_type if inv else None)} → "
                f"{_format_part_quantity(body.quantity)} {_part_unit_label(inv.unit_type if inv else None)}"
            ),
            entity_id=pu.id,
        )
    await db.commit()
    await _recompute_repair_order_totals(db, order_id)
    await db.refresh(pu)
    return _build_parts_usage_response(pu, inv)


async def _load_order_for_summary(db: AsyncSession, order_id: UUID) -> RepairOrder:
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(
            selectinload(RepairOrder.labor_items),
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
        )
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
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
            selectinload(RepairOrder.labor_items),
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
    _apply_repair_order_totals(order)
    await db.commit()
    return _to_price_build_summary(order)


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
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
            selectinload(RepairOrder.labor_items),
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

    _apply_repair_order_totals(order, parts_total=parts_total, labor_total=labor_total)
    await db.commit()
    return _to_price_build_summary(order)


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
        inv.stock_quantity += _stock_packages_reserved(pu)
    _record_repair_order_history_event(
        db,
        order=order,
        current_user=current_user,
        event_type="part_removed",
        label="Part removed from repair order",
        detail=_part_history_detail(
            inv.name if inv else "Part",
            pu.quantity,
            inv.unit_type if inv else None,
        ),
        entity_id=pu.id,
    )
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
    hourly_rate = body.hourly_rate
    if order.is_internal:
        tenant = (await db.execute(select(Tenant).where(Tenant.id == order.tenant_id))).scalar_one()
        hourly_rate = (
            tenant.labor_rate if fleet_labor_uses_customer_rate(order) else tenant.internal_labor_rate
        )
    total_cost = body.hours * hourly_rate
    labor = Labor(
        tenant_id=current_user.tenant_id,
        repair_order_id=order_id,
        description=body.description or "",
        hours=body.hours,
        hourly_rate=hourly_rate,
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
