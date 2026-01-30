from sqlalchemy import Column, String, Integer, Numeric, ForeignKey, Text, Enum as SQLEnum, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import enum
from decimal import Decimal
from app.db.base import BaseModel


class PointsTransactionType(str, enum.Enum):
    EARNED = "earned"           # Points earned from completing a job
    REDEEMED_PTO = "redeemed_pto"    # Redeemed for PTO
    REDEEMED_CASH = "redeemed_cash"  # Redeemed for cash
    BONUS = "bonus"             # Streak or quality bonus
    ADJUSTMENT = "adjustment"   # Manual adjustment by admin


class MechanicPoints(BaseModel):
    """Track mechanic points earnings and redemptions"""
    __tablename__ = "mechanic_points"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id])
    
    # Transaction details
    transaction_type = Column(
        SQLEnum(PointsTransactionType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True
    )
    points = Column(Integer, nullable=False)  # Positive for earned, negative for redeemed
    
    # Reference to repair order (for earned points)
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=True)
    repair_order = relationship("RepairOrder")
    
    # Labor value this was based on (for audit)
    labor_value = Column(Numeric(10, 2), nullable=True)
    
    # Multiplier applied (streak bonus, etc)
    multiplier = Column(Numeric(3, 2), default=Decimal("1.00"), nullable=False)
    
    # Notes (reason for adjustment, redemption details, etc)
    notes = Column(Text, nullable=True)
    
    # For redemptions: cash value or PTO hours
    redemption_value = Column(Numeric(10, 2), nullable=True)


class MechanicPointsBalance(BaseModel):
    """Cached balance for quick lookups - updated on each transaction"""
    __tablename__ = "mechanic_points_balance"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id])
    
    # Current available balance
    available_points = Column(Integer, default=0, nullable=False)
    
    # Lifetime stats
    total_earned = Column(Integer, default=0, nullable=False)
    total_redeemed = Column(Integer, default=0, nullable=False)
    
    # Current streak
    current_streak_days = Column(Integer, default=0, nullable=False)
    last_work_date = Column(DateTime(timezone=True), nullable=True)
