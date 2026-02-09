"""
Error Log Model for persistent error tracking.

Stores application errors with full context for debugging and monitoring.
"""
from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import enum
from app.db.base import BaseModel


class ErrorCategory(str, enum.Enum):
    PAYMENT = "payment"           # Stripe errors, payment failures
    AUTH = "auth"                 # Authentication/authorization errors
    VALIDATION = "validation"     # Input validation errors
    DATABASE = "database"         # Database connection/query errors
    EXTERNAL_API = "external_api" # Third-party API errors
    UNHANDLED = "unhandled"       # Uncaught exceptions


class ErrorSeverity(str, enum.Enum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorLog(BaseModel):
    __tablename__ = "error_logs"
    
    # Request tracking
    correlation_id = Column(String(255), index=True, nullable=True)
    
    # Error classification
    error_type = Column(String(255), index=True, nullable=False)  # e.g., "StripeCardError", "ValidationError"
    error_category = Column(String(50), nullable=False, default=ErrorCategory.UNHANDLED.value, index=True)
    severity = Column(String(20), nullable=False, default=ErrorSeverity.ERROR.value)
    
    # Request context
    endpoint = Column(String(500), index=True, nullable=True)
    method = Column(String(10), nullable=True)
    status_code = Column(Integer, index=True, nullable=True)
    
    # User context (nullable for unauthenticated requests)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Error details
    message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    request_context = Column(JSONB, nullable=True)  # Sanitized request data (no passwords, tokens)
    
    # Resolution tracking
    resolved = Column(Boolean, default=False, nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="errors")
    tenant = relationship("Tenant", foreign_keys=[tenant_id], backref="errors")
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])

    def __repr__(self):
        return f"<ErrorLog {self.error_type} at {self.endpoint}>"
