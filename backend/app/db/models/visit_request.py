from sqlalchemy import Column, String, Text, Date, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel

class VisitRequest(BaseModel):
    __tablename__='visit_requests'
    __table_args__=(
        UniqueConstraint('tenant_id','idempotency_key',name='uq_visit_request_key'),
        UniqueConstraint('tenant_id','id',name='uq_visit_request_tenant_id'),
        ForeignKeyConstraint(['tenant_id','customer_id'],['customers.tenant_id','customers.id']),
        ForeignKeyConstraint(['tenant_id','vehicle_id'],['vehicles.tenant_id','vehicles.id']),
        ForeignKeyConstraint(['tenant_id','service_id'],['services.tenant_id','services.id']),
        CheckConstraint("status IN ('requested','availability_review','accepted','declined','withdrawn','fulfilled')",name='ck_visit_request_status'),
        CheckConstraint("status <> 'accepted' OR accepted_arrival_date IS NOT NULL",name='ck_visit_request_accepted_date'),
        CheckConstraint('version>=1',name='ck_visit_request_version'),
        ForeignKeyConstraint(['tenant_id','fulfilled_repair_order_id'],['repair_orders.tenant_id','repair_orders.id']),
    )
    version=Column(Integer,nullable=False,default=1,server_default='1')
    accepted_arrival_date=Column(Date)
    reviewed_by_user_id=Column(UUID(as_uuid=True),ForeignKey('users.id'))
    reviewed_at=Column(DateTime(timezone=True))
    internal_review_note=Column(Text)
    fulfilled_repair_order_id=Column(UUID(as_uuid=True))
    tenant_id=Column(UUID(as_uuid=True),ForeignKey('tenants.id'),nullable=False,index=True)
    customer_id=Column(UUID(as_uuid=True),nullable=False,index=True)
    service_id=Column(UUID(as_uuid=True),nullable=False)
    vehicle_id=Column(UUID(as_uuid=True))
    preferred_date=Column(Date)
    customer_notes=Column(Text)
    status=Column(String(24),nullable=False,default='requested')
    request_reference=Column(String(32),nullable=False,unique=True)
    idempotency_key=Column(String(200),nullable=False)
    request_sha256=Column(String(64),nullable=False)
