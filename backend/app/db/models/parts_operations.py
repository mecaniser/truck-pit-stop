"""Tenant-scoped immutable purchasing and stock-operation records (DB-038)."""
from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, BaseModel


class ImmutableOperationRecord(Base):
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class InventoryCategory(BaseModel):
    __tablename__ = "inventory_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "normalized_name", "deleted_at", name="uq_inventory_category_live_name"),)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class InventoryMovement(ImmutableOperationRecord):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("quantity_delta <> 0", name="ck_inventory_movement_nonzero"),
        CheckConstraint("balance_before >= 0", name="ck_inventory_movement_before_nonnegative"),
        CheckConstraint("balance_after >= 0", name="ck_inventory_movement_after_nonnegative"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_inventory_movement_idempotency"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False, index=True)
    bucket = Column(String(24), nullable=False, default="on_hand")
    movement_type = Column(String(64), nullable=False)
    quantity_delta = Column(Integer, nullable=False)
    balance_before = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    unit_cost_snapshot = Column(Numeric(12, 2), nullable=True)
    wac_before = Column(Numeric(12, 2), nullable=True)
    wac_after = Column(Numeric(12, 2), nullable=True)
    source_type = Column(String(64), nullable=True)
    source_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    destination_type = Column(String(64), nullable=True)
    destination_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_display_name_snapshot = Column(String(255), nullable=True)
    reason_code = Column(String(100), nullable=True)
    note = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PurchaseOrder(BaseModel):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "po_number", "deleted_at", name="uq_purchase_order_live_number"),)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    po_number = Column(String(100), nullable=False)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="draft")
    ordered_at = Column(DateTime(timezone=True), nullable=True)
    expected_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class PurchaseOrderLine(BaseModel):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        CheckConstraint("ordered_quantity >= 1 AND ordered_quantity <= 999", name="ck_po_line_ordered_quantity"),
        CheckConstraint("received_quantity >= 0 AND received_quantity <= ordered_quantity", name="ck_po_line_received_quantity"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    purchase_order_id = Column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False, index=True)
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False, index=True)
    sku_snapshot = Column(String(100), nullable=False)
    description_snapshot = Column(String(255), nullable=False)
    unit_type_snapshot = Column(String(20), nullable=False)
    unit_cost_snapshot = Column(Numeric(12, 2), nullable=False)
    core_charge_snapshot = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    ordered_quantity = Column(Integer, nullable=False)
    received_quantity = Column(Integer, nullable=False, default=0)


class PartsOperationIdempotency(ImmutableOperationRecord):
    __tablename__ = "parts_operation_idempotency"
    __table_args__ = (UniqueConstraint("tenant_id", "operation_family", "idempotency_key", name="uq_parts_operation_idempotency"),)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    operation_family = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_fingerprint = Column(String(128), nullable=False)
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class PurchaseReceipt(ImmutableOperationRecord):
    __tablename__ = "purchase_receipts"
    __table_args__ = (UniqueConstraint("tenant_id", "operation_family", "idempotency_key", name="uq_purchase_receipt_idempotency"),)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    purchase_order_id = Column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False, index=True)
    receipt_number = Column(String(100), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    supplier_reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    received_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    operation_family = Column(String(64), nullable=False, default="po_receipt")
    idempotency_key = Column(String(128), nullable=False)
    request_fingerprint = Column(String(128), nullable=False)


class PurchaseReceiptLine(ImmutableOperationRecord):
    __tablename__ = "purchase_receipt_lines"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    purchase_receipt_id = Column(UUID(as_uuid=True), ForeignKey("purchase_receipts.id"), nullable=False, index=True)
    purchase_order_line_id = Column(UUID(as_uuid=True), ForeignKey("purchase_order_lines.id"), nullable=False, index=True)
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)
    wac_before = Column(Numeric(12, 2), nullable=False)
    wac_after = Column(Numeric(12, 2), nullable=False)
    balance_before = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)


class CoreObligation(BaseModel):
    __tablename__ = "core_obligations"
    __table_args__ = (UniqueConstraint("tenant_id", "parts_usage_id", "deleted_at", name="uq_core_obligation_origin"),)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    parts_usage_id = Column(UUID(as_uuid=True), ForeignKey("parts_usage.id"), nullable=False, index=True)
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False, index=True)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_core_value_snapshot = Column(Numeric(12, 2), nullable=False)
    status = Column(String(24), nullable=False, default="expected")
    version = Column(Integer, nullable=False, default=1)
    reason = Column(Text, nullable=True)


class VendorReturn(BaseModel):
    __tablename__ = "vendor_returns"
    __table_args__ = (UniqueConstraint("tenant_id", "return_number", "deleted_at", name="uq_vendor_return_live_number"),)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    return_number = Column(String(100), nullable=False)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    status = Column(String(24), nullable=False, default="draft")
    version = Column(Integer, nullable=False, default=1)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True)
    credited_at = Column(DateTime(timezone=True), nullable=True)
    supplier_reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    reason = Column(String(100), nullable=True)
    reverses_return_id = Column(UUID(as_uuid=True), ForeignKey("vendor_returns.id"), nullable=True, unique=True)


class VendorReturnLine(BaseModel):
    __tablename__ = "vendor_return_lines"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    vendor_return_id = Column(UUID(as_uuid=True), ForeignKey("vendor_returns.id"), nullable=False, index=True)
    purchase_receipt_line_id = Column(UUID(as_uuid=True), ForeignKey("purchase_receipt_lines.id"), nullable=True, index=True)
    core_obligation_id = Column(UUID(as_uuid=True), ForeignKey("core_obligations.id"), nullable=True, index=True)
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    expected_credit = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    actual_credit = Column(Numeric(12, 2), nullable=True)
    stock_value_snapshot = Column(Numeric(12, 2), nullable=True)


class PurchaseOrderAttachment(BaseModel):
    __tablename__ = "purchase_order_attachments"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    purchase_order_id = Column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False, index=True)
    storage_key = Column(String(512), nullable=False)
    display_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    byte_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    uploaded_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
