"""Real migration201 and tenant/key concurrency; NEW explicit disposable database only."""
import asyncio,ast,contextvars,importlib.util,json
from pathlib import Path
from uuid import uuid4
from decimal import Decimal
import pytest,pytest_asyncio
from sqlalchemy import select,func,text,insert,update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.exc import DBAPIError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_booking_readiness_legacy_mirrors_postgres import pg_readiness
from test_customer_efs_submissions import fictional_keys,CODE,payload,submit,fictional_zelle_context
from app.services import customer_efs as efs,invoice_settlement_service as domain
from app.core import efs_crypto
from app.schemas.efs_submission import EfsSubmit
from app.db.models.efs_instrument import EfsInstrumentSubmission as Claim

@pytest_asyncio.fixture
async def pg_efs(pg_readiness):
    db=pg_readiness;assert db.bind.dialect.name=='postgresql'
    migration_path=Path(__file__).parents[1]/'alembic/versions/202_customer_efs_submissions.py'
    spec=importlib.util.spec_from_file_location('efs_migration202',migration_path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    async with db.bind.begin() as connection:
        def install(sync):
            # Reproduce the real pre-existing146 database enforcement. ORM
            # create_all alone omits historical functions and hid this boundary.
            sync.execute(text('ALTER TABLE invoice_payment_attempts ALTER COLUMN manual_evidence TYPE jsonb USING manual_evidence::jsonb'))
            legacy=ast.parse((migration_path.parent/'146_fleet_payment_rail.py').read_text())
            for node in ast.walk(legacy):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='execute' and node.args and isinstance(node.args[0],ast.Constant):
                    sql=node.args[0].value
                    if isinstance(sql,str) and ('CREATE FUNCTION guard_db048_fleet_evidence' in sql or 'CREATE TRIGGER trg_db048_fleet_evidence' in sql):sync.execute(text(sql))
            Claim.__table__.drop(sync)
            op=Operations(MigrationContext.configure(sync))
            op.drop_constraint('uq_invoice_settlements_tenant_id','invoice_settlements',type_='unique')
            op.drop_constraint('uq_invoice_attempts_tenant_id','invoice_payment_attempts',type_='unique')
            migration.op=op;migration.upgrade()
        await connection.run_sync(install)
    return db

@pytest.mark.asyncio
async def test_pg_migration_claim_immutable_and_exact_sidecar_binding(pg_efs,monkeypatch):
    db=pg_efs;ctx=await fictional_zelle_context(db,monkeypatch);a,s=await submit(db,ctx)
    row=await db.scalar(select(Claim));assert efs_crypto.decrypt(row)==CODE
    with pytest.raises(DBAPIError):
        async with db.begin_nested():await db.execute(update(Claim).where(Claim.id==row.id).values(last4='9999'))
    await db.refresh(row);assert row.last4=='5678'
    # A second new protected attempt with a valid new sidecar ID; all referenced
    # rows exist, but a same-tenant wrong settlement must fail cross-row binding.
    from tests.test_db048_invoice_settlements import _add_eligible_invoice
    from app.db.models.invoice_settlement import InvoiceSettlement
    other=await _add_eligible_invoice(db,tenant=ctx.tenant,customer=ctx.customer,reference_invoice=ctx.invoice,with_shadow_settlement=True)
    other_settlement=await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id==other.id))
    sid=uuid4();admission=efs.EfsAdmission(ctx.tenant.id,ctx.invoice.id,ctx.customer.id,sid,'1111',efs._SEAL)
    new=await domain.create_attempt(db,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.customer_user,amount=Decimal('1'),rail='fleet_payment',expected_settlement_version=s.version,idempotency_key='raw-binding-fixture',source=efs.SOURCE,subject_type='customer',subject_id=ctx.customer_user.id,sender_evidence={'source':efs.SOURCE,'fleet_provider':'EFS','code_last4':'1111','efs_submission_id':str(sid)},efs_admission=admission)
    await db.flush()
    bad=dict(id=sid,tenant_id=ctx.tenant.id,invoice_id=ctx.invoice.id,settlement_id=other_settlement.id,attempt_id=new.attempt.id,customer_id=ctx.customer.id,provider='EFS',secret_ciphertext='fictional-ciphertext',key_version='v1',code_fingerprint='a'*64,fingerprint_key_identity=efs_crypto.key_identity(),last4='1111',submission_request_sha256='b'*64)
    with pytest.raises(DBAPIError):
        async with db.begin_nested():await db.execute(insert(Claim).values(**bad))
    assert await db.scalar(select(func.count(Claim.id)))==1

@pytest.mark.asyncio
async def test_pg_same_code_different_commands_has_one_claim(pg_efs,monkeypatch):
    db=pg_efs;ctx=await fictional_zelle_context(db,monkeypatch);await db.commit()
    sessions=async_sessionmaker(db.bind,expire_on_commit=False,autoflush=False)
    initial=payload(ctx)
    async def perform(command):
        async with sessions() as own:
            try:
                a,s=await efs.submit(own,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.customer_user,body=EfsSubmit(**initial),idempotency_key=command)
                await own.commit();return 'accepted'
            except domain.SettlementDomainError as error:
                await own.rollback();assert error.code in {'invoice_busy','efs_code_requires_review'};return error.code
    results=await asyncio.gather(perform('one-code-command-A'),perform('one-code-command-B'))
    assert results.count('accepted')==1
    assert await db.scalar(select(func.count(Claim.id)))==1

@pytest.mark.asyncio
async def test_pg_global_first_claim_rejects_conflicting_key_instances_across_tenants(pg_efs,monkeypatch):
    db=pg_efs;first=await fictional_zelle_context(db,monkeypatch);second=await fictional_zelle_context(db,monkeypatch);await db.commit()
    original=efs_crypto.keys;active,ciphers,_=original()
    # Task-local provisioning models two web instances with different configured
    # HMAC keys; no authorization, source proof or domain logic is mocked.
    local_key=contextvars.ContextVar('efs_instance_key')
    monkeypatch.setattr(efs_crypto,'keys',lambda:(active,ciphers,local_key.get()))
    sessions=async_sessionmaker(db.bind,expire_on_commit=False,autoflush=False)
    async def perform(ctx,instance_key):
        local_key.set(instance_key)
        async with sessions() as own:
            try:
                await efs.submit(own,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.customer_user,body=EfsSubmit(**payload(ctx)),idempotency_key='first-tenant-'+str(ctx.tenant.id))
                await own.commit();return 'accepted'
            except domain.SettlementDomainError as error:
                await own.rollback();assert error.code=='efs_unavailable';return 'unavailable'
    results=await asyncio.wait_for(asyncio.gather(perform(first,b'fictional-instance-key-A-32bytes-long'),perform(second,b'fictional-instance-key-B-32bytes-long')),10)
    assert sorted(results)==['accepted','unavailable']
    assert await db.scalar(select(func.count(Claim.id)))==1

@pytest.mark.asyncio
async def test_pg_cancellation_races_actual_receipt_without_losing_money(pg_efs,monkeypatch):
    from app.schemas.efs_submission import EfsVerify
    from app.schemas.invoice_settlement import AttemptResolutionCommand
    from app.services.payment_attempt_resolution import execute
    from app.db.models.payment import Payment
    from app.db.models.invoice_settlement import InvoicePaymentAttempt as Attempt,InvoiceSettlement
    db=pg_efs;ctx=await fictional_zelle_context(db,monkeypatch);a,s=await submit(db,ctx)
    versions=(a.version,s.version);sessions=async_sessionmaker(db.bind,expire_on_commit=False,autoflush=False)
    async def cancel():
        async with sessions() as own:
            try:
                command=AttemptResolutionCommand(action='cancel_unsent',reason_code='not_used',reason='The merchant has not used this code.',expected_attempt_version=versions[0],expected_settlement_version=versions[1])
                await execute(own,a.id,command,'race-efs-cancel',actor=ctx.customer_user);await own.commit();return 'cancelled'
            except domain.SettlementDomainError as error:
                await own.rollback();assert error.code in {'invoice_busy','stale_attempt_version','stale_settlement_version','attempt_resolution_not_allowed'};return error.code
    async def receive():
        async with sessions() as own:
            try:
                command=EfsVerify(action='confirm_received',expected_attempt_version=versions[0],expected_settlement_version=versions[1],reason='Merchant authorized and received actual funds.',merchant_authorized=True,authorization_reference='PG-MERCHANT-RECEIPT',received_amount='168.44')
                await efs.verify(own,a.id,ctx.owner,command,'race-efs-receipt');await own.commit();return 'received'
            except domain.SettlementDomainError as error:
                await own.rollback();assert error.code in {'invoice_busy','stale_attempt_version','stale_settlement_version'};return error.code
    results=await asyncio.wait_for(asyncio.gather(cancel(),receive()),15)
    # If cancellation won, the authorized actual-receipt retry observes the fresh
    # versions and retains late funds. No second request or provider action occurs.
    await db.refresh(a);await db.refresh(s)
    if a.received_amount is None:
        command=EfsVerify(action='confirm_received',expected_attempt_version=a.version,expected_settlement_version=s.version,reason='Record the actual receipt after refreshing this request.',merchant_authorized=True,authorization_reference='PG-MERCHANT-RECEIPT',received_amount='168.44')
        await efs.verify(db,a.id,ctx.owner,command,'race-efs-receipt-retry');await db.commit()
    assert a.received_amount==Decimal('168.44') and s.confirmed_principal==Decimal('168.44') and s.active_pending_principal==0
    assert await db.scalar(select(func.count(Payment.id)))==1
    assert await db.scalar(select(func.count(Claim.id)))==1
    assert await db.scalar(select(func.count(Attempt.id)).where(Attempt.invoice_id==ctx.invoice.id))==1

@pytest.mark.asyncio
@pytest.mark.parametrize('demoted',[False,True])
async def test_pg_masked_notice_and_queue_reauth_before_mock_delivery(pg_efs,monkeypatch,demoted):
    from app.core.config import settings
    from app.db.models.automated_sms import AutomatedSMSOperation
    from app.db.models.user import UserRole
    from app.services import automated_sms_service as sms
    from app.services.zelle_transfer_reports import review_queue
    db=pg_efs;ctx=await fictional_zelle_context(db,monkeypatch)
    ctx.tenant.sms_enabled=True;ctx.tenant.messaging_enabled=True
    ctx.tenant.sms_phone_number='+15005550111';ctx.owner.phone='+15005550777'
    await db.commit();monkeypatch.setattr(settings,'SMS_AUTOMATION_OUTBOX_ENABLED',True)
    a,s=await submit(db,ctx)
    operations=(await db.scalars(select(AutomatedSMSOperation))).all();assert len(operations)==1
    op=operations[0];assert op.template_name=='pending_efs_staff_submit_sms'
    assert CODE not in op.body and '5678' in op.body and '$168.44' in op.body
    rows=(await review_queue(db,ctx.owner,include_cards=True))['rows'];assert len(rows)==1
    assert rows[0]['attempt_id']==str(a.id) and rows[0]['kind']=='canonical_efs_attempt' and rows[0]['provider_label']=='EFS'
    from fastapi.encoders import jsonable_encoder
    assert rows[0]['efs'].can_verify and CODE not in json.dumps(jsonable_encoder(rows))
    class Sender:
        ready=True
        calls=0
        async def send(self,**kwargs):
            self.calls+=1
            assert CODE not in str(kwargs)
            return {'sid':'SM'+uuid4().hex,'status':'queued'}
    sender=Sender()
    if demoted:ctx.owner.role=UserRole.MECHANIC;await db.commit()
    await sms.dispatch_automated_operation(db,op.id,sender)
    assert sender.calls==(0 if demoted else 1),(op.state,op.error_code)
    assert op.state==('rejected' if demoted else 'accepted')
    await sms.dispatch_automated_operation(db,op.id,sender)
    assert sender.calls==(0 if demoted else 1)

@pytest.mark.asyncio
async def test_pg_deferred_attempt_requires_exact_claim_and_keeps_legacy_evidence_guard(pg_efs,monkeypatch):
    db=pg_efs;ctx=await fictional_zelle_context(db,monkeypatch)
    sid=uuid4();admission=efs.EfsAdmission(ctx.tenant.id,ctx.invoice.id,ctx.customer.id,sid,'1111',efs._SEAL)
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await domain.create_attempt(db,invoice=ctx.invoice,tenant=ctx.tenant,customer_id=ctx.customer.id,actor=ctx.customer_user,amount=Decimal('1'),rail='fleet_payment',expected_settlement_version=ctx.settlement.version,idempotency_key='orphan-efs-no-claim',source=efs.SOURCE,subject_type='customer',subject_id=ctx.customer_user.id,sender_evidence={'source':efs.SOURCE,'fleet_provider':'EFS','code_last4':'1111','efs_submission_id':str(sid)},efs_admission=admission)
            await db.execute(text('SET CONSTRAINTS check_efs_attempt_claim IMMEDIATE'))
    await db.refresh(ctx.settlement)
    a,s=await submit(db,ctx)
    from app.db.models.invoice_settlement import InvoicePaymentAttempt as Attempt
    # Source stripping or adding arbitrary plaintext metadata cannot turn the
    # protected request into an ordinary Fleet entry, or mutate old evidence.
    for values in [dict(source='staff'),dict(manual_evidence={'fleet_provider':'EFS','reference_number':'OTHER'}),dict(manual_evidence={**a.manual_evidence,'extra':'not-permitted'})]:
        with pytest.raises(DBAPIError):
            async with db.begin_nested():await db.execute(update(Attempt).where(Attempt.id==a.id).values(**values))
    await db.refresh(a);assert a.source==efs.SOURCE and 'reference_number' not in a.manual_evidence
