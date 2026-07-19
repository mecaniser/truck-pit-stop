"""Small, purpose-built payloads for repair-order workspace typeaheads.

These are deliberately not aliases of the full list/detail response models.
The repair-order workspace only needs enough information to select a record;
returning accounting balances, service bundles, or inventory photos while an
operator types makes that interaction needlessly expensive.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CustomerTypeaheadResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    company_name: Optional[str] = None
    email: str
    phone: Optional[str] = None


class VehicleTypeaheadResponse(BaseModel):
    id: UUID
    customer_id: UUID
    make: str
    model: str
    year: Optional[int] = None
    unit_number: Optional[str] = None
    license_plate: Optional[str] = None
    vin: Optional[str] = None


class ServiceTypeaheadResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    duration_minutes: int
    base_price: Optional[Decimal] = None
    requires_vehicle: bool


class InventoryTypeaheadResponse(BaseModel):
    id: UUID
    sku: str
    name: str
    stock_quantity: int
    on_order_quantity: int
    unit_type: str
    cost: Decimal
    selling_price: Decimal
