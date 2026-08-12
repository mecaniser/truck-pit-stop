from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import BaseModel


class UserAppearancePreference(BaseModel):
    __tablename__ = "user_appearance_preferences"
    __table_args__ = (
        Index(
            "uq_user_appearance_preferences_active_tenant_user",
            "tenant_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    schema_version = Column(Integer, nullable=False, default=1, server_default="1")
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    appearance = Column(JSONB, nullable=False, default=dict, server_default="{}")
    legacy_migration_status = Column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    legacy_migrated_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    user = relationship("User")


class UserPresentationOverride(BaseModel):
    __tablename__ = "user_presentation_overrides"
    __table_args__ = (
        Index(
            "uq_user_presentation_overrides_active_tenant_user",
            "tenant_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    presentation = Column(String(16), nullable=False)

    tenant = relationship("Tenant")
    user = relationship("User")
