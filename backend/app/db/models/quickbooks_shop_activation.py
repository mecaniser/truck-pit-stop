"""Persistent management boundary; a disabled row is never legacy admission."""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class QuickBooksShopActivation(BaseModel):
    __tablename__ = "quickbooks_shop_activations"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_qbo_shop_activation_tenant"),
        UniqueConstraint("tenant_id", "id", name="uq_qbo_shop_activation_identity"),
        CheckConstraint("environment IN ('sandbox','production')", name="ck_qbo_shop_environment"),
        CheckConstraint("writer = 'dieselbridge' AND version > 0", name="ck_qbo_shop_writer"),
        CheckConstraint("NOT enabled OR activated_at IS NOT NULL", name="ck_qbo_shop_cutoff"),
        CheckConstraint("deleted_at IS NULL", name="ck_qbo_shop_not_deleted"),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    realm_id = Column(String(255), nullable=False)
    environment = Column(String(16), nullable=False)
    writer = Column(String(32), nullable=False, default="dieselbridge", server_default="dieselbridge")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    activated_at = Column(DateTime(timezone=True), nullable=True)
