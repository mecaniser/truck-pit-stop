from sqlalchemy import Column, String, Integer, ForeignKey, Text, Enum as SQLEnum, DateTime, Date
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import BaseModel


class PTORequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"


class PTORequestType(str, enum.Enum):
    PTO = "pto"      # Paid time off using points
    CASH = "cash"    # Cash out points


class PTORequest(BaseModel):
    """PTO or cash-out requests from mechanics"""
    __tablename__ = "pto_requests"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id])
    
    request_type = Column(
        SQLEnum(PTORequestType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    
    status = Column(
        SQLEnum(PTORequestStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PTORequestStatus.PENDING,
        index=True,
    )
    
    # For PTO requests
    pto_start_date = Column(Date, nullable=True)
    pto_end_date = Column(Date, nullable=True)
    pto_days = Column(Integer, nullable=True)
    
    # Points to redeem
    points_requested = Column(Integer, nullable=False)
    
    # Cash value (for cash requests)
    cash_value = Column(Integer, nullable=True)  # In cents
    
    # Notes
    mechanic_notes = Column(Text, nullable=True)
    manager_notes = Column(Text, nullable=True)
    
    # Manager who processed the request
    processed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    processed_by = relationship("User", foreign_keys=[processed_by_id])
    processed_at = Column(DateTime(timezone=True), nullable=True)
