"""DB-045 immutable part activity and dedicated counter-sale aggregates.

The classes in this module deliberately do not reuse repair orders, invoices,
payments, or parts usage.  Counter sales are their own tenant-scoped financial
aggregate and activity is an append-only index over authoritative domain rows.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, BaseModel


class PartActivityEvent(Base):
    __tablename__ = "part_activity_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_part_activity_tenant_idempotency"),
        ForeignKeyConstraint(
            ["tenant_id", "inventory_id"],
            ["inventory.tenant_id", "inventory.id"],
            name="fk_part_activity_tenant_inventory",
        ),
        CheckConstraint(
            "category IN ('catalog','stock','repairs','purchasing','returns','sales')",
            name="ck_part_activity_category",
        ),
        CheckConstraint("origin IN ('live','baseline','backfill_snapshot')", name="ck_part_activity_origin"),
        Index("ix_part_activity_tenant_occurred", "tenant_id", "occurred_at", "id"),
        Index("ix_part_activity_part_occurred", "tenant_id", "inventory_id", "occurred_at", "id"),
        Index("ix_part_activity_category_type", "tenant_id", "category", "event_type"),
        Index("ix_part_activity_actor", "tenant_id", "actor_id"),
        Index("ix_part_activity_source", "tenant_id", "source_type", "source_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False)
    category = Column(String(32), nullable=False)
    event_type = Column(String(80), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    correlation_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    source_type = Column(String(48), nullable=True)
    source_id = Column(UUID(as_uuid=True), nullable=True)
    source_number_snapshot = Column(String(120), nullable=True)
    part_sku_snapshot = Column(String(100), nullable=False)
    part_name_snapshot = Column(String(255), nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_name_snapshot = Column(String(255), nullable=False, default="System")
    reason_code = Column(String(80), nullable=True)
    note = Column(Text, nullable=True)
    origin = Column(String(24), nullable=False, default="live")
    payload_version = Column(SmallInteger, nullable=False, default=1)
    idempotency_key = Column(String(255), nullable=False)
    before_values = Column(JSON, nullable=False, default=dict)
    after_values = Column(JSON, nullable=False, default=dict)
    stock_snapshot = Column(JSON, nullable=True)
    money_snapshot = Column(JSON, nullable=True)
    payment_snapshot = Column(JSON, nullable=True)
    source_snapshot = Column(JSON, nullable=True)


class PartActivityBackfillRun(BaseModel):
    __tablename__ = "part_activity_backfill_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "payload_version", "cutoff_at", name="uq_activity_backfill_run"),
        CheckConstraint("state IN ('running','failed','reconciled','verified')", name="ck_activity_backfill_state"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    payload_version = Column(SmallInteger, nullable=False, default=1)
    cutoff_at = Column(DateTime(timezone=True), nullable=False)
    state = Column(String(24), nullable=False, default="running", index=True)
    batch_cursor = Column(String(255), nullable=True)
    source_counts = Column(JSON, nullable=False, default=dict)
    inserted_counts = Column(JSON, nullable=False, default=dict)
    replayed_counts = Column(JSON, nullable=False, default=dict)
    source_checksums = Column(JSON, nullable=False, default=dict)
    duplicate_count = Column(Integer, nullable=False, default=0)
    error_summary = Column(Text, nullable=True)
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)


class CounterSale(BaseModel):
    __tablename__ = "counter_sales"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_counter_sales_tenant_id_id"),
        UniqueConstraint("tenant_id", "sale_number", name="uq_counter_sales_tenant_number"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"],
            name="fk_counter_sales_tenant_customer",
        ),
        CheckConstraint(
            "status IN ('draft','completed','partially_returned','returned','cancelled')",
            name="ck_counter_sale_status",
        ),
        CheckConstraint("currency = 'USD'", name="ck_counter_sale_currency"),
        CheckConstraint("version >= 1", name="ck_counter_sale_version"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    sale_number = Column(String(100), nullable=False)
    status = Column(String(32), nullable=False, default="draft", index=True)
    version = Column(Integer, nullable=False, default=1)
    customer_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    buyer_name_snapshot = Column(String(255), nullable=True)
    buyer_email_snapshot = Column(String(255), nullable=True)
    buyer_phone_snapshot = Column(String(40), nullable=True)
    currency = Column(String(3), nullable=False, default="USD")
    tax_rate_snapshot = Column(Numeric(7, 4), nullable=False, default=0)
    list_subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    charged_subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    discount_total = Column(Numeric(14, 2), nullable=False, default=0)
    tax_total = Column(Numeric(14, 2), nullable=False, default=0)
    total = Column(Numeric(14, 2), nullable=False, default=0)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    completed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancelled_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    receipt_snapshot = Column(JSON, nullable=True)


class CounterSaleLine(BaseModel):
    __tablename__ = "counter_sale_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_counter_sale_lines_tenant_id_id"),
        UniqueConstraint(
            "tenant_id", "sale_id", "id",
            name="uq_counter_sale_lines_tenant_sale_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sale_id"], ["counter_sales.tenant_id", "counter_sales.id"],
            name="fk_counter_sale_lines_tenant_sale",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "inventory_id"], ["inventory.tenant_id", "inventory.id"],
            name="fk_counter_sale_lines_tenant_inventory",
        ),
        CheckConstraint("quantity > 0", name="ck_counter_sale_line_quantity"),
        CheckConstraint("list_unit_price >= 0 AND charged_unit_price > 0", name="ck_counter_sale_line_prices"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    sale_id = Column(UUID(as_uuid=True), ForeignKey("counter_sales.id"), nullable=False, index=True)
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    sku_snapshot = Column(String(100), nullable=False)
    name_snapshot = Column(String(255), nullable=False)
    unit_snapshot = Column(String(20), nullable=False)
    category_snapshot = Column(String(100), nullable=True)
    unit_cost = Column(Numeric(14, 2), nullable=False)
    list_unit_price = Column(Numeric(14, 2), nullable=False)
    charged_unit_price = Column(Numeric(14, 2), nullable=False)
    discount_total = Column(Numeric(14, 2), nullable=False, default=0)
    item_subtotal = Column(Numeric(14, 2), nullable=False)
    tax_allocation = Column(Numeric(14, 2), nullable=False, default=0)
    total = Column(Numeric(14, 2), nullable=False)
    cost_total = Column(Numeric(14, 2), nullable=False)
    price_override_reason = Column(Text, nullable=True)
    price_override_actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    unit_allocations = Column(JSON, nullable=False, default=list)


class CounterSalePaymentAttempt(BaseModel):
    __tablename__ = "counter_sale_payment_attempts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_counter_sale_attempt_idempotency"),
        UniqueConstraint("tenant_id", "id", name="uq_counter_sale_attempts_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "sale_id"], ["counter_sales.tenant_id", "counter_sales.id"],
            name="fk_counter_sale_attempts_tenant_sale",
        ),
        CheckConstraint("state = 'succeeded'", name="ck_counter_sale_attempt_state"),
        CheckConstraint("amount > 0", name="ck_counter_sale_attempt_amount"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    sale_id = Column(UUID(as_uuid=True), ForeignKey("counter_sales.id"), nullable=False, index=True)
    tender = Column(String(32), nullable=False)
    state = Column(String(40), nullable=False, default="succeeded", index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    request_fingerprint = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    external_reference = Column(String(255), nullable=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)


class CounterSaleReturn(BaseModel):
    __tablename__ = "counter_sale_returns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_counter_sale_returns_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "sale_id"], ["counter_sales.tenant_id", "counter_sales.id"],
            name="fk_counter_sale_returns_tenant_sale",
        ),
        CheckConstraint("state = 'completed'", name="ck_counter_sale_return_state"),
        CheckConstraint("version >= 1", name="ck_counter_sale_return_version"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    sale_id = Column(UUID(as_uuid=True), ForeignKey("counter_sales.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    state = Column(String(24), nullable=False, default="completed", index=True)
    item_amount = Column(Numeric(14, 2), nullable=False)
    tax_amount = Column(Numeric(14, 2), nullable=False)
    refund_amount = Column(Numeric(14, 2), nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    refund_reference = Column(String(255), nullable=True)
    correlation_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class CounterSaleReturnLine(BaseModel):
    __tablename__ = "counter_sale_return_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "return_id"], ["counter_sale_returns.tenant_id", "counter_sale_returns.id"],
            name="fk_counter_sale_return_lines_tenant_return",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sale_line_id"], ["counter_sale_lines.tenant_id", "counter_sale_lines.id"],
            name="fk_counter_sale_return_lines_tenant_sale_line",
        ),
        CheckConstraint("quantity > 0", name="ck_counter_sale_return_line_quantity"),
        CheckConstraint("disposition IN ('restock','damaged')", name="ck_counter_sale_return_disposition"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    return_id = Column(UUID(as_uuid=True), ForeignKey("counter_sale_returns.id"), nullable=False, index=True)
    sale_line_id = Column(UUID(as_uuid=True), ForeignKey("counter_sale_lines.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    disposition = Column(String(16), nullable=False)
    item_amount = Column(Numeric(14, 2), nullable=False)
    discount_amount = Column(Numeric(14, 2), nullable=False)
    tax_amount = Column(Numeric(14, 2), nullable=False)
    cost_amount = Column(Numeric(14, 2), nullable=False)
    unit_ordinals = Column(JSON, nullable=False, default=list)
