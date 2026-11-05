"""Immutable encrypted customer EFS claims. No bearer data in financial evidence."""
from sqlalchemy import Column,String,Text,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint,event
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel

class EfsInstrumentSubmission(BaseModel):
    __tablename__='efs_instrument_submissions'
    __table_args__=(
        UniqueConstraint('attempt_id',name='uq_efs_submission_attempt'),
        UniqueConstraint('tenant_id','provider','code_fingerprint',name='uq_efs_tenant_instrument'),
        ForeignKeyConstraint(['tenant_id','invoice_id'],['invoices.tenant_id','invoices.id'],name='fk_efs_invoice'),
        ForeignKeyConstraint(['tenant_id','customer_id'],['customers.tenant_id','customers.id'],name='fk_efs_customer'),
        ForeignKeyConstraint(['tenant_id','attempt_id'],['invoice_payment_attempts.tenant_id','invoice_payment_attempts.id'],name='fk_efs_attempt'),
        ForeignKeyConstraint(['tenant_id','settlement_id'],['invoice_settlements.tenant_id','invoice_settlements.id'],name='fk_efs_settlement'),
        CheckConstraint("provider='EFS' AND length(code_fingerprint)=64 AND length(fingerprint_key_identity)=64 AND length(last4)=4",name='ck_efs_claim_shape'),
    )
    tenant_id=Column(UUID(as_uuid=True),ForeignKey('tenants.id'),nullable=False,index=True)
    invoice_id=Column(UUID(as_uuid=True),nullable=False)
    settlement_id=Column(UUID(as_uuid=True),nullable=False)
    attempt_id=Column(UUID(as_uuid=True),nullable=False)
    customer_id=Column(UUID(as_uuid=True),nullable=False)
    provider=Column(String(8),nullable=False,default='EFS')
    secret_ciphertext=Column(Text,nullable=False)
    key_version=Column(String(32),nullable=False)
    code_fingerprint=Column(String(64),nullable=False)
    fingerprint_key_identity=Column(String(64),nullable=False)
    last4=Column(String(4),nullable=False)
    submission_request_sha256=Column(String(64),nullable=False)

@event.listens_for(EfsInstrumentSubmission,'before_update')
@event.listens_for(EfsInstrumentSubmission,'before_delete')
def immutable_submission(*args):raise ValueError('EFS instrument claims are immutable')
