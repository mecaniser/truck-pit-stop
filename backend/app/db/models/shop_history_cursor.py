"""Durable rotating scan; no contact or financial data is stored here."""
from sqlalchemy import Column, ForeignKey, UniqueConstraint, Integer, String, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class ShopHistoryCursor(BaseModel):
    __tablename__ = "shop_history_cursors"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_shop_history_cursor_tenant"),)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    last_invoice_id = Column(UUID(as_uuid=True), nullable=True)


class ShopHistoryObservation(BaseModel):
    __tablename__ = "shop_history_observations"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_id", name="uq_shop_history_observation_invoice"),
                      CheckConstraint("sequence >= 1", name="ck_shop_history_observation_sequence"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    source_revision = Column(String(64), nullable=False)
    sequence = Column(Integer, nullable=False)
