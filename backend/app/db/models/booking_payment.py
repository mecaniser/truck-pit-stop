"""Booking prepayment liability evidence, separate from invoice receipts/revenue."""
from sqlalchemy import Column, String, Integer, BigInteger, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, DateTime, Index, text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel

class BookingPaymentAttempt(BaseModel):
    __tablename__ = 'booking_payment_attempts'
    __table_args__ = (
        UniqueConstraint('tenant_id','id', name='uq_booking_attempt_tenant_id'),
        UniqueConstraint('tenant_id','id','appointment_id', name='uq_booking_attempt_appointment'),
        UniqueConstraint('tenant_id','idempotency_key', name='uq_booking_attempt_request'),
        UniqueConstraint('provider','provider_account_id','provider_intent_id', name='uq_booking_provider_intent'),
        ForeignKeyConstraint(['tenant_id','appointment_id'],['appointments.tenant_id','appointments.id']),
        ForeignKeyConstraint(['tenant_id','customer_id'],['customers.tenant_id','customers.id']),
        ForeignKeyConstraint(['tenant_id','configuration_version'],['tenant_payment_provider_configurations.tenant_id','tenant_payment_provider_configurations.version']),
        CheckConstraint("amount_minor>=50 AND currency='usd'",name='ck_booking_attempt_amount'),
        CheckConstraint("provider IN ('quickbooks_payments','stripe_connect')",name='ck_booking_attempt_provider'),
        CheckConstraint("state IN ('created','creating','requires_action','requires_payment_method','processing','outcome_unknown','succeeded','failed','cancelled')",name='ck_booking_attempt_state'),
        UniqueConstraint('provider','provider_account_id','provider_request_id',name='uq_booking_provider_request'),
        Index('uq_booking_live_attempt', 'appointment_id', unique=True,
            postgresql_where=text("state IN ('created','creating','requires_action','requires_payment_method','processing','outcome_unknown')"),
            sqlite_where=text("state IN ('created','creating','requires_action','requires_payment_method','processing','outcome_unknown')")),
    )
    tenant_id=Column(UUID(as_uuid=True),ForeignKey('tenants.id'),nullable=False,index=True)
    appointment_id=Column(UUID(as_uuid=True),nullable=False,index=True)
    customer_id=Column(UUID(as_uuid=True),nullable=False)
    amount_minor=Column(BigInteger,nullable=False)
    currency=Column(String(3),nullable=False)
    provider=Column(String(32),nullable=False)
    provider_account_id=Column(String(255),nullable=False)
    configuration_version=Column(Integer,nullable=False)
    environment=Column(String(24),nullable=False)
    source_metadata_sha256=Column(String(64),nullable=False)
    provider_intent_id=Column(String(255),nullable=True)
    provider_charge_id=Column(String(255),nullable=True)
    provider_request_id=Column(String(200),nullable=False)
    state=Column(String(32),nullable=False)
    idempotency_key=Column(String(200),nullable=False)
    request_sha256=Column(String(64),nullable=False)
    verified_at=Column(DateTime(timezone=True))

class BookingReceipt(BaseModel):
    __tablename__='booking_receipts'
    __table_args__=(
        UniqueConstraint('tenant_id','id',name='uq_booking_receipt_tenant_id'),
        UniqueConstraint('attempt_id',name='uq_booking_receipt_attempt'),
        UniqueConstraint('provider','provider_account_id','provider_intent_id',name='uq_booking_receipt_provider'),
        ForeignKeyConstraint(['tenant_id','appointment_id'],['appointments.tenant_id','appointments.id']),
        ForeignKeyConstraint(['tenant_id','attempt_id','appointment_id'],['booking_payment_attempts.tenant_id','booking_payment_attempts.id','booking_payment_attempts.appointment_id']),
        CheckConstraint("verification_basis IN ('server_retrieval','verified_connect_webhook')",name='ck_booking_receipt_basis'),
        CheckConstraint("amount_received_minor>=50 AND refunded_amount_minor>=0 AND refunded_amount_minor<=amount_received_minor AND currency='usd'",name='ck_booking_receipt_amount'),
    )
    tenant_id=Column(UUID(as_uuid=True),ForeignKey('tenants.id'),nullable=False)
    appointment_id=Column(UUID(as_uuid=True),nullable=False)
    attempt_id=Column(UUID(as_uuid=True),nullable=False)
    provider=Column(String(32),nullable=False)
    provider_account_id=Column(String(255),nullable=False)
    provider_intent_id=Column(String(255),nullable=False)
    charge_id=Column(String(255),nullable=True)
    amount_received_minor=Column(BigInteger,nullable=False)
    currency=Column(String(3),nullable=False)
    received_at=Column(DateTime(timezone=True),nullable=False)
    refunded_amount_minor=Column(BigInteger,nullable=False,default=0,server_default='0')
    verification_basis=Column(String(40),nullable=False)
    proof_sha256=Column(String(64),nullable=False)

class BookingPaymentEvent(BaseModel):
    __tablename__='booking_payment_events'
    __table_args__=(
        ForeignKeyConstraint(['tenant_id','appointment_id'],['appointments.tenant_id','appointments.id']),
        UniqueConstraint('provider','provider_account_id','provider_event_id',name='uq_booking_provider_event'),
        ForeignKeyConstraint(['tenant_id','attempt_id','appointment_id'],['booking_payment_attempts.tenant_id','booking_payment_attempts.id','booking_payment_attempts.appointment_id']),
    )
    tenant_id=Column(UUID(as_uuid=True),ForeignKey('tenants.id'),nullable=False)
    appointment_id=Column(UUID(as_uuid=True),nullable=False)
    attempt_id=Column(UUID(as_uuid=True))
    actor_user_id=Column(UUID(as_uuid=True),ForeignKey('users.id'))
    source=Column(String(40),nullable=False)
    before_state=Column(String(32))
    after_state=Column(String(32),nullable=False)
    provider=Column(String(32))
    provider_account_id=Column(String(255))
    provider_event_id=Column(String(255))
    event_at=Column(DateTime(timezone=True),nullable=False)
    proof_sha256=Column(String(64))
