from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from decimal import Decimal
from app.db.models.repair_order import RepairOrderStatus
from app.db.models.labor import LaborLineType
from app.db.models.recommended_service import RecommendedServicePriority


# --- Parts and labor line items ---


class PartsUsageCreate(BaseModel):
    inventory_id: UUID
    # Decimal so fluid parts (oil, coolant, DEF) can be entered in fractional
    # amounts, e.g. 1.25 gallons.
    quantity: Decimal
    unit_price: Optional[Decimal] = None  # override; else use inventory selling_price
    source_service_id: Optional[UUID] = None
    source_line_id: Optional[UUID] = None  # labor line this part is attached to
    # Explicit acknowledgement that the shop has physical stock which has not
    # been recorded in inventory yet. The API retains the shortfall for audit.
    allow_stock_shortage: bool = False


class PartsUsageUpdate(BaseModel):
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    allow_stock_shortage: bool = False


class PartsPricingModeRequest(BaseModel):
    mode: str  # 'stock' (all parts at garage cost) | 'list' (all parts at list price)


class DiscountUpdate(BaseModel):
    labor_discount_amount: Optional[Decimal] = None   # $ off the labor subtotal
    order_discount_amount: Optional[Decimal] = None   # $ off the order total


class PartsUsageResponse(BaseModel):
    id: UUID
    repair_order_id: UUID
    inventory_id: UUID
    inventory_sku: str
    inventory_name: str
    quantity: Decimal
    unit_type: str = "each"
    unit_price: Decimal
    unit_cost: Optional[Decimal] = None
    list_price: Optional[Decimal] = None
    savings: Decimal = Decimal("0")
    total_price: Decimal
    source_service_id: Optional[UUID] = None
    source_line_id: Optional[UUID] = None
    stock_shortage_override: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class RepairOrderHistoryEventResponse(BaseModel):
    id: UUID
    event_type: str
    label: str
    detail: Optional[str] = None
    entity_id: Optional[UUID] = None
    actor_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PartSuggestion(BaseModel):
    inventory_id: UUID
    sku: str
    name: str
    stock_quantity: int
    unit_type: str = "each"
    selling_price: Decimal
    use_count: int


class PartSuggestionsResponse(BaseModel):
    for_this_order: List[PartSuggestion] = []
    most_used: List[PartSuggestion] = []


class LaborCreate(BaseModel):
    description: Optional[str] = None
    hours: Decimal
    hourly_rate: Decimal
    mechanic_id: Optional[UUID] = None
    service_code: Optional[str] = None
    line_type: LaborLineType = LaborLineType.MANUAL
    provider: Optional[str] = None
    provider_operation_id: Optional[str] = None
    auto_recalc_enabled: bool = True
    source_service_id: Optional[UUID] = None
    vendor_name: Optional[str] = None
    vendor_cost: Optional[Decimal] = None


class LaborUpdate(BaseModel):
    description: Optional[str] = None
    hours: Optional[Decimal] = None
    hourly_rate: Optional[Decimal] = None
    mechanic_id: Optional[UUID] = None
    service_code: Optional[str] = None
    line_type: Optional[LaborLineType] = None
    provider: Optional[str] = None
    provider_operation_id: Optional[str] = None
    auto_recalc_enabled: Optional[bool] = None
    source_service_id: Optional[UUID] = None
    vendor_name: Optional[str] = None
    vendor_cost: Optional[Decimal] = None


class LaborResponse(BaseModel):
    id: UUID
    repair_order_id: UUID
    description: str
    hours: Decimal
    hourly_rate: Decimal
    total_cost: Decimal
    mechanic_id: Optional[UUID] = None
    service_code: Optional[str] = None
    line_type: LaborLineType = LaborLineType.MANUAL
    provider: Optional[str] = None
    provider_operation_id: Optional[str] = None
    auto_recalc_enabled: bool = True
    source_service_id: Optional[UUID] = None
    vendor_name: Optional[str] = None
    vendor_cost: Optional[Decimal] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RepairOrderPhotoResponse(BaseModel):
    id: UUID
    repair_order_id: UUID
    image_url: str
    caption: Optional[str] = None
    uploaded_at: datetime
    uploader_name: str = "Unknown"

    class Config:
        from_attributes = True


class RepairOrderBase(BaseModel):
    description: Optional[str] = None
    customer_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    po_number: Optional[str] = None
    mileage_in: Optional[int] = None


class RepairOrderCreate(RepairOrderBase):
    customer_id: UUID
    vehicle_id: UUID
    assigned_mechanic_id: Optional[UUID] = None
    parent_repair_order_id: Optional[UUID] = None
    is_warranty_repair: bool = False


class RepairOrderUpdate(BaseModel):
    status: Optional[RepairOrderStatus] = None
    description: Optional[str] = None
    customer_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    assigned_mechanic_id: Optional[UUID] = None
    po_number: Optional[str] = None
    mileage_in: Optional[int] = None
    mileage_out: Optional[int] = None
    parent_repair_order_id: Optional[UUID] = None
    is_warranty_repair: Optional[bool] = None


class RepairOrderResponse(RepairOrderBase):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    vehicle_id: UUID
    order_number: str
    status: RepairOrderStatus
    assigned_mechanic_id: Optional[UUID]
    total_parts_cost: Decimal
    total_labor_cost: Decimal
    total_cost: Decimal
    created_at: datetime
    updated_at: datetime
    work_started_at: Optional[datetime] = None
    work_completed_at: Optional[datetime] = None
    hold_reason: Optional[str] = None
    held_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by_user_id: Optional[UUID] = None
    cancelled_by_name: Optional[str] = None
    deleted_at: Optional[datetime] = None
    deleted_by_user_id: Optional[UUID] = None
    deleted_by_name: Optional[str] = None
    estimated_labor_minutes: Optional[int] = None
    actual_tracked_minutes: Optional[int] = None
    total_hold_minutes: Optional[int] = None
    assigned_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    pricing_locked_at: Optional[datetime] = None
    pricing_lock_reason: Optional[str] = None
    quote_sent: Optional[bool] = None  # True if quote exists and was sent to customer
    quote_approved: Optional[bool] = None
    quote_sent_at: Optional[datetime] = None
    invoice_created_at: Optional[datetime] = None
    invoice_due_date: Optional[datetime] = None
    pending_zelle_confirmation: bool = False
    mileage_out: Optional[int] = None
    po_number: Optional[str] = None
    parent_repair_order_id: Optional[UUID] = None
    is_warranty_repair: bool = False
    is_internal: bool = False
    bill_labor_at_customer_rate: bool = False
    is_pm: bool = False
    # Vehicle summary fields (denormalized for display)
    vehicle_make: str = ""
    vehicle_model: str = ""
    vehicle_year: Optional[int] = None
    vehicle_unit_number: Optional[str] = None
    vehicle_vin: Optional[str] = None
    # Customer summary fields (denormalized for display) so the list doesn't need
    # to load the full customer table to resolve names.
    customer_first_name: str = ""
    customer_last_name: str = ""
    customer_company_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None

    @field_validator("bill_labor_at_customer_rate", mode="before")
    @classmethod
    def default_bill_labor_at_customer_rate(cls, value):
        # SQLAlchemy column defaults are applied on flush. Keep response
        # validation stable for newly constructed/legacy ORM instances too.
        return False if value is None else value

    class Config:
        from_attributes = True


class RepairOrderPMServiceEntry(BaseModel):
    service_id: UUID
    name: str
    duration_minutes: int = 0

    class Config:
        from_attributes = True


class RepairOrderDetailResponse(RepairOrderResponse):
    parts_usage: List[PartsUsageResponse] = []
    labor_items: List[LaborResponse] = []
    history_events: List[RepairOrderHistoryEventResponse] = []
    # Selected PM services (fleet PM work orders only); empty for other orders.
    pm_services: List[RepairOrderPMServiceEntry] = []


class RepairOrderStartWorkResponse(RepairOrderResponse):
    auto_clocked_in: bool = False


class PriceBuildWarning(BaseModel):
    code: str
    message: str
    line_id: Optional[UUID] = None


class PriceBuildFlatServiceRequest(BaseModel):
    service_id: UUID
    quantity: int = 1


class PriceBuildRepairOpsSearchRequest(BaseModel):
    query: str


class RepairOperationCandidate(BaseModel):
    operation_id: str
    name: str
    description: Optional[str] = None
    estimated_hours: Decimal
    provider: str = "internal_library"


class PriceBuildRepairOpsApplyRequest(BaseModel):
    operation_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    estimated_hours: Optional[Decimal] = None
    provider: Optional[str] = None
    auto_recalc_enabled: bool = True


class PriceBuildLineUpdateRequest(BaseModel):
    description: Optional[str] = None
    hours: Optional[Decimal] = None
    hourly_rate: Optional[Decimal] = None
    auto_recalc_enabled: Optional[bool] = None


class PriceBuildSummaryResponse(BaseModel):
    order_id: UUID
    labor_total: Decimal                          # gross labor (before discount)
    parts_total: Decimal                          # gross parts
    labor_discount_amount: Decimal = Decimal("0.00")
    order_discount_amount: Decimal = Decimal("0.00")
    total_cost: Decimal                           # net of both discounts
    pricing_locked: bool
    pricing_locked_at: Optional[datetime] = None
    pricing_lock_reason: Optional[str] = None
    can_edit_work: bool = False
    can_assign_technician: bool = False
    can_start_work: bool = False
    can_finalize: bool = False
    lines: List[LaborResponse] = []
    warnings: List[PriceBuildWarning] = []


class PriceBuildSearchResponse(BaseModel):
    candidates: List[RepairOperationCandidate] = []
    warnings: List[PriceBuildWarning] = []


class QuickRepairOrderCreate(BaseModel):
    phone: Optional[str] = None
    vehicle_description: Optional[str] = None
    complaint: Optional[str] = None


class PriceBuildSubletRequest(BaseModel):
    description: str
    vendor_name: str
    vendor_cost: Decimal
    charge_to_customer: Decimal
    hourly_rate: Optional[Decimal] = None  # if None, use charge_to_customer as flat amount


class RecommendedServiceCreate(BaseModel):
    description: str
    estimated_cost: Optional[Decimal] = None
    priority: RecommendedServicePriority = RecommendedServicePriority.SOON
    notes: Optional[str] = None


class RecommendedServiceUpdate(BaseModel):
    description: Optional[str] = None
    estimated_cost: Optional[Decimal] = None
    priority: Optional[RecommendedServicePriority] = None
    notes: Optional[str] = None
    is_resolved: Optional[bool] = None
    resolved_by_repair_order_id: Optional[UUID] = None


class RecommendedServiceResponse(BaseModel):
    id: UUID
    repair_order_id: UUID
    tenant_id: UUID
    description: str
    estimated_cost: Optional[Decimal] = None
    priority: RecommendedServicePriority
    notes: Optional[str] = None
    is_resolved: bool
    resolved_by_repair_order_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True
