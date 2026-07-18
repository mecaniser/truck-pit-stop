from sqlalchemy import Column, String, Integer, Numeric, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from decimal import Decimal
from app.db.base import BaseModel


class Inventory(BaseModel):
    __tablename__ = "inventory"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="inventory")
    
    sku = Column(String(100), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    
    stock_quantity = Column(Integer, default=0, nullable=False)
    on_order_quantity = Column(Integer, default=0, nullable=False)
    reorder_level = Column(Integer, default=0, nullable=False)
    cost = Column(Numeric(10, 2), nullable=False)
    selling_price = Column(Numeric(10, 2), nullable=False)

    # Unit this part is dispensed in. "each" parts (filters, belts) use whole-number
    # quantities; fluids (oil, coolant, DEF) are dispensed in fractional amounts of
    # their unit, so quantity on PartsUsage/ServicePart is decimal. stock_quantity
    # above still tracks whole packages/jugs on hand regardless of unit_type.
    unit_type = Column(String(20), default="each", nullable=False)
    
    supplier_name = Column(String(255), nullable=True)
    supplier_contact = Column(String(255), nullable=True)

    # Physical spot in the warehouse (aisle/shelf/bin), e.g. "A3-S2" or "Back wall".
    location = Column(String(100), nullable=True)
    source = Column(String(50), nullable=True, index=True)  # e.g. easy_truck_shop_import

    # Single reference photo for the part (Cloudinary). public_id is kept so the
    # old asset can be deleted on replace/remove.
    image_url = Column(String(500), nullable=True)
    cloudinary_public_id = Column(String(255), nullable=True)

    parts_usage = relationship("PartsUsage", back_populates="inventory_item")


class PartsUsage(BaseModel):
    __tablename__ = "parts_usage"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="parts_usage")
    
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    repair_order = relationship("RepairOrder", back_populates="parts_usage")
    
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False, index=True)
    inventory_item = relationship("Inventory", back_populates="parts_usage")
    
    # Numeric so fluids (oil, coolant, DEF) can be entered in fractional amounts
    # (e.g. 1.25 gallons), not just whole units.
    quantity = Column(Numeric(6, 2), nullable=False)
    unit_cost = Column(Numeric(10, 2), nullable=True)  # inventory cost snapshot at time of use
    unit_price = Column(Numeric(10, 2), nullable=False)
    # Original selling_price at attach time — preserved for savings audit trail when
    # unit_price is discounted below list. Equal to unit_price when no discount given.
    list_price = Column(Numeric(10, 2), nullable=True)
    total_price = Column(Numeric(10, 2), nullable=False)

    # Warranty tracking (surfaced on the fleet Truck Detail "Parts & warranty" list).
    warranty_until = Column(Date, nullable=True)
    warranty_miles = Column(Integer, nullable=True)

    # When set, this PartsUsage row was auto-added because a Service (which bundles
    # parts) was attached to the RO. Mechanics should not edit/delete these directly;
    # removing the parent Labor line is the way to remove them.
    source_service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True, index=True)

