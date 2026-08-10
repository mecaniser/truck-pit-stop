from sqlalchemy import Column, String, Boolean, ForeignKey, Enum as SQLEnum, Integer, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import enum
from app.db.base import BaseModel


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"      # Platform owner - manages all garages
    GARAGE_OWNER = "garage_owner"    # Owner of a specific garage
    GARAGE_ADMIN = "garage_admin"    # Admin employee at a garage
    MECHANIC = "mechanic"            # Technician working on repairs
    RECEPTIONIST = "receptionist"    # Front desk staff
    FLEET_MANAGER = "fleet_manager"  # Manages the garage's own fleet (internal-cost repairs)
    CUSTOMER = "customer"            # Truck owner/operator


class User(BaseModel):
    __tablename__ = "users"
    
    email = Column(String(255), unique=True, nullable=False, index=True)
    # Optional WorkOS projection. Existing password users remain valid during
    # cutover, so these fields are deliberately nullable and additive.
    workos_user_id = Column(String(255), unique=True, nullable=True, index=True)
    workos_identity_status = Column(String(32), nullable=False, default="legacy", server_default="legacy")
    workos_identity_linked_at = Column(DateTime(timezone=True), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    address = Column(String(255), nullable=True)
    role = Column(
        SQLEnum(UserRole, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.CUSTOMER
    )
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Grants access to the Messages/Communications surface for roles that don't
    # have it by default (notably fleet managers). Owner/admin/receptionist/
    # mechanic always have messaging regardless of this flag.
    can_access_messaging = Column(Boolean, default=False, nullable=False)

    # Per-user grants for owner-only settings surfaces (keys: payments,
    # taxes_fees, workforce). Only consulted for GARAGE_ADMIN — owners and
    # super admins always pass regardless of this column.
    permissions = Column(JSONB, nullable=False, default=dict, server_default="{}")
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    tenant = relationship("Tenant", foreign_keys=[tenant_id], backref="users")
    
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, unique=True)
    # No backref to Customer: unused elsewhere, and an unguarded backref risks
    # SQLAlchemy silently nullifying it during unrelated unit-of-work flushes
    # (see MessageThread.customer for the incident this pattern caused during
    # customer merges — this FK is nullable so it wouldn't crash, just silently
    # unlink the wrong user).
    customer = relationship("Customer", uselist=False)

    # Optional per-mechanic workforce overrides
    core_hours_target_minutes_override = Column(Integer, nullable=True)
    shift_start_local_override = Column(String(5), nullable=True)  # HH:MM
    shift_end_local_override = Column(String(5), nullable=True)  # HH:MM
