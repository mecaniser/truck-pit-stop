"""DB132 bounded, extra-forbidden requests. Decimal values never use float math."""
from decimal import Decimal
from typing import Annotated, Literal, Union
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.services.parts_pricing_rules import validate_bands
from app.core.work_value_validation import validate_part_quantity, validate_labor_hours

Money = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2, allow_inf_nan=False)]

class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

class MatrixBand(StrictInput):
    min_cost: Money
    max_cost: Money | None
    markup_percent: Annotated[Decimal, Field(ge=0, le=10000, decimal_places=2, allow_inf_nan=False)]

class BandsInput(StrictInput):
    bands: list[MatrixBand] = Field(min_length=1, max_length=30)
    @field_validator('bands')
    @classmethod
    def check_bands(cls, value):
        validate_bands([b.model_dump() for b in value])
        return value

class MatrixCreate(BandsInput):
    name: str = Field(min_length=1, max_length=100)
    @field_validator('name')
    @classmethod
    def strip_name(cls, value):
        value = value.strip()
        if not value: raise ValueError('Enter a matrix name.')
        return value

class MatrixUpdate(MatrixCreate):
    expected_version: int = Field(ge=1)

class MatrixArchive(StrictInput):
    expected_version: int = Field(ge=1)

class DefaultUpdate(StrictInput):
    matrix_id: UUID | None
    expected_generation: int = Field(ge=0)

class InventoryPolicyPatch(StrictInput):
    expected_pricing_version: int = Field(ge=0)
    selling_price: Money | None = None
    pricing_cost_floor: Money | None = None
    minimum_sale_price: Money | None = None
    fixed_sales_price: bool | None = None
    @model_validator(mode='after')
    def required_values(self):
        for field in ('selling_price', 'fixed_sales_price'):
            if field in self.model_fields_set and getattr(self,field) is None:
                raise ValueError(field + ' cannot be null')
        return self

class DraftSample(StrictInput):
    sample_key: str = Field(min_length=1, max_length=80)
    label: str | None = Field(default=None, max_length=120)
    actual_unit_cost: Money | None
    catalog_unit_price: Money | None
    pricing_cost_floor: Money | None = None
    minimum_sale_price: Money | None = None
    fixed_sales_price: bool = False

class SamplePreview(BandsInput):
    mode: Literal['samples']
    samples: list[DraftSample] = Field(min_length=1,max_length=20)
    @field_validator('samples')
    @classmethod
    def unique_keys(cls, value):
        if len({v.sample_key for v in value}) != len(value): raise ValueError('Sample keys must be unique')
        return value

class InventoryPreview(BandsInput):
    mode: Literal['inventory']
    inventory_ids: list[UUID] = Field(min_length=1,max_length=50)
    @field_validator('inventory_ids')
    @classmethod
    def unique_keys(cls, value):
        if len(set(value)) != len(value): raise ValueError('Inventory IDs must be unique')
        return value

DraftPreview = Annotated[Union[SamplePreview,InventoryPreview],Field(discriminator='mode')]

class RepairContext(StrictInput):
    kind: Literal['repair_order']
    repair_order_id: UUID

class FleetContext(StrictInput):
    kind: Literal['fleet_draft']
    vehicle_id: UUID
    bill_to_customer_id: UUID | None = None

class CounterContext(StrictInput):
    kind: Literal['counter_sale']
    sale_id: UUID | None = None
    customer_id: UUID | None = None
    expected_sale_version: int | None = Field(default=None,ge=1)

class AddLine(StrictInput):
    client_key: str = Field(min_length=1,max_length=100)
    inventory_id: UUID
    quantity: Decimal
    source_line_id: UUID | None = None
    source_service_id: UUID | None = None
    pricing_intent: Literal['default','manual','stock'] = 'default'
    unit_price: Money | None = None
    price_override_reason: str | None = Field(default=None,max_length=500)
    _quantity = field_validator('quantity')(validate_part_quantity)

class PartsAdd(StrictInput):
    kind: Literal['parts_add']
    lines: list[AddLine] = Field(max_length=100)
    @field_validator('lines')
    @classmethod
    def unique_keys(cls,value):
        if len({v.client_key for v in value}) != len(value): raise ValueError('Line keys must be unique')
        return value

class ServiceApply(StrictInput):
    attachment_path: Literal['shop_flat_service','fleet_legacy_service'] = 'shop_flat_service'
    kind: Literal['service_apply']
    service_id: UUID
    quantity: int = Field(default=1,ge=1,le=999)

class PmReplace(StrictInput):
    kind: Literal['pm_replace']
    service_ids: list[UUID] = Field(max_length=30)
    @field_validator('service_ids')
    @classmethod
    def unique_services(cls,value):
        if len(set(value)) != len(value): raise ValueError('Service IDs must be unique')
        return value

class StagedLabor(StrictInput):
    description: str = Field(min_length=1,max_length=500)
    hours: Decimal
    _hours = field_validator('hours')(validate_labor_hours)

class FleetCreate(PmReplace):
    kind: Literal['fleet_create']
    part_lines: list[AddLine] = Field(default_factory=list,max_length=100)
    labor_lines: list[StagedLabor] = Field(default_factory=list,max_length=100)

class CounterLine(StrictInput):
    sale_line_id: UUID | None = None
    inventory_id: UUID
    quantity: int = Field(ge=1,le=999)
    pricing_intent: Literal['default','manual','stock','list'] = 'default'
    charged_unit_price: Money | None = None
    price_override_reason: str | None = Field(default=None,max_length=500)

class CounterDraft(StrictInput):
    kind: Literal['counter_draft']
    lines: list[CounterLine] = Field(min_length=1,max_length=100)
    @field_validator('lines')
    @classmethod
    def unique_parts(cls,value):
        if len({v.inventory_id for v in value}) != len(value): raise ValueError('Each part may appear only once')
        return value

class ResolveRequest(StrictInput):
    context: Annotated[Union[RepairContext,FleetContext,CounterContext],Field(discriminator='kind')]
    plan: Annotated[Union[PartsAdd,ServiceApply,PmReplace,FleetCreate,CounterDraft],Field(discriminator='kind')]
    pricing_presentation: Literal['shop','fleet'] | None = None
    include_management_details: bool = False

class SafePrice(BaseModel):
    policy_source: Literal["customer", "shop", "internal", "legacy"] | None = None
    origin_source: Literal['matrix','fixed','catalog','ad_hoc','internal','legacy_unknown']
    current_source: Literal['matrix','fixed','catalog','ad_hoc','internal','legacy_unknown','manual']
    managed: bool
    default_unit_price: str | None
    charged_unit_price: str | None
    line_total: str | None
    pricing_version: int | None
    can_override: bool
