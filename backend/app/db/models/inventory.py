from sqlalchemy import Column, String, Integer, Numeric, ForeignKey, Text
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
    reorder_level = Column(Integer, default=0, nullable=False)
    cost = Column(Numeric(10, 2), nullable=False)
    selling_price = Column(Numeric(10, 2), nullable=False)
    
    supplier_name = Column(String(255), nullable=True)
    supplier_contact = Column(String(255), nullable=True)
    
    parts_usage = relationship("PartsUsage", back_populates="inventory_item")


class PartsUsage(BaseModel):
    __tablename__ = "parts_usage"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="parts_usage")
    
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    repair_order = relationship("RepairOrder", back_populates="parts_usage")
    
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False, index=True)
    inventory_item = relationship("Inventory", back_populates="parts_usage")
    
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)


