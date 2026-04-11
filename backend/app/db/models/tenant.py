from sqlalchemy import Column, String, Boolean, ForeignKey, Integer, Numeric, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from decimal import Decimal
from app.db.base import BaseModel


class Tenant(BaseModel):
    __tablename__ = "tenants"
    
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    address = Column(String(500), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sms_phone_number = Column(String(20), nullable=True, unique=True, index=True)
    sms_phone_sid = Column(String(64), nullable=True)
    sms_enabled = Column(Boolean, default=False, nullable=False)
    sms_messaging_service_sid = Column(String(64), nullable=True)
    
    # Garage ownership
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    owner = relationship("User", foreign_keys=[owner_id], post_update=True)
    
    # Stripe Connect
    stripe_account_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_onboarding_complete = Column(Boolean, default=False, nullable=False)
    
    # Zelle payment info
    zelle_email = Column(String(255), nullable=True)
    zelle_phone = Column(String(20), nullable=True)
    zelle_qr_image = Column(Text, nullable=True)  # Base64 encoded QR image
    
    # Invoice reminder settings (tenant-controlled)
    invoice_reminders_enabled = Column(Boolean, default=True, nullable=False)
    reminder_frequency_days = Column(Integer, default=3, nullable=False)
    max_invoice_reminders = Column(Integer, default=3, nullable=False)
    
    # Tax and fee settings (percentages, applied at checkout)
    sales_tax_rate = Column(Numeric(5, 3), default=Decimal("0.000"), nullable=False)  # e.g., 8.25% = 8.250
    shop_supplies_rate = Column(Numeric(5, 3), default=Decimal("0.000"), nullable=False)  # % of labor
    service_fee_rate = Column(Numeric(5, 3), default=Decimal("0.000"), nullable=False)  # % of total
    labor_rate = Column(Numeric(10, 2), default=Decimal("100.00"), nullable=False)  # Default hourly rate

    # Workforce settings (mechanic utilization tracking)
    timezone = Column(String(64), default="America/New_York", nullable=False)
    default_core_hours_minutes = Column(Integer, default=480, nullable=False)  # 8 hours
    default_shift_start_local = Column(String(5), default="08:00", nullable=False)
    default_shift_end_local = Column(String(5), default="18:00", nullable=False)
    minimum_clock_in_remaining_minutes = Column(Integer, default=60, nullable=False)
    
    # Enrollment fields
    enrollment_status = Column(String(20), default="pending", nullable=False)  # pending, approved, rejected
    business_license = Column(String(100), nullable=True)
    ein = Column(String(20), nullable=True)  # Employer Identification Number
    website = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    partner_summary = Column(String(280), nullable=True)
    partner_services = Column(String(180), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    rejection_reason = Column(Text, nullable=True)
