"""Disposable PostgreSQL cohort/null semantics and immutable readiness reads."""
import os
from uuid import uuid4
import pytest,pytest_asyncio
from sqlalchemy import text,select,event,update
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.db.base import Base
from app.db.models.invoice_settlement import InvoiceSettlement,TenantPaymentProviderConfiguration
from app.services import booking_payment_provider as provider,invoice_settlement_service as settlement
from test_booking_readiness_legacy_mirrors import context,clone_invoice,fingerprint,ETS

@pytest_asyncio.fixture
async def pg_readiness():
    url=os.environ.get('BOOKING_POSTGRES_TEST_URL')
    if not url:pytest.skip('Explicit disposable PostgreSQL DSN required')
    schema='booking_readiness_'+uuid4().hex
    admin=create_async_engine(url)
    async with admin.begin() as connection:await connection.execute(text(f'CREATE SCHEMA {schema}'))
    engine=create_async_engine(url,connect_args={'server_settings':{'search_path':schema}})
    async with engine.begin() as connection:await connection.run_sync(Base.metadata.create_all)
    try:
        async with async_sessionmaker(engine,expire_on_commit=False,autoflush=False)() as db:yield db
    finally:
        await engine.dispose()
        async with admin.begin() as connection:await connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        await admin.dispose()

@pytest.mark.asyncio
@pytest.mark.parametrize('sources,excluded',[((None,None),False),((ETS,None),False),((None,ETS),False),((ETS,ETS),True)])
async def test_pg_null_and_exact_marker_classification_preserves_all_rows(pg_readiness,monkeypatch,sources,excluded):
    db=pg_readiness;ctx=await context(db,monkeypatch)
    await clone_invoice(db,ctx,invoice_source=sources[0],order_source=sources[1])
    before=await fingerprint(db)
    actual=await settlement.provider_readiness(db,ctx[0])
    assert ('invoice_settlement_backfill_stale_invoice' not in actual.reasons)==excluded
    assert await fingerprint(db)==before
    assert not db.new and not db.dirty and not db.deleted

@pytest.mark.asyncio
@pytest.mark.parametrize('stray',[False,True])
async def test_pg_direct_raw_mirror_never_becomes_payable(pg_readiness,monkeypatch,stray):
    db=pg_readiness;ctx=await context(db,monkeypatch);invoice,_=await clone_invoice(db,ctx)
    if stray:
        db.add(InvoiceSettlement(tenant_id=ctx[0].id,invoice_id=invoice.id,customer_id=ctx[2].id,principal_total=100));await db.commit()
    before=await fingerprint(db)
    assert 'raw_imported_invoice_read_only' in (await settlement.provider_readiness(db,ctx[0],invoice_id=invoice.id)).reasons
    assert await fingerprint(db)==before

@pytest.mark.asyncio
async def test_pg_historical_not_ready_fresh_ready_both_bindings_and_stale_cache_denial(pg_readiness,monkeypatch):
    from datetime import datetime,timezone
    db=pg_readiness;ctx=await context(db,monkeypatch);tenant,_,_,_,config,_=ctx
    for _ in range(4):await clone_invoice(db,ctx)
    before=await fingerprint(db);calls=[]
    def mutation(_connection,_cursor,sql,*args):
        if sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):calls.append(sql)
    event.listen(db.bind.sync_engine,'before_cursor_execute',mutation)
    try:
        cap=await provider.booking_provider_capability(db,tenant)
        assert cap.available
        assert await provider._bound_configuration(db,cap.binding,new_charge=True) is config
        assert config.readiness_state=='not_ready'
        assert await fingerprint(db)==before and not calls
    finally:event.remove(db.bind.sync_engine,'before_cursor_execute',mutation)
    await (await db.connection()).execute(update(TenantPaymentProviderConfiguration.__table__).where(TenantPaymentProviderConfiguration.id==config.id).values(is_active=False,deactivated_at=datetime.now(timezone.utc)))
    assert config.is_active
    before=await fingerprint(db)
    assert not (await provider.booking_provider_capability(db,tenant)).available
    with pytest.raises(provider.BookingProviderError):await provider._bound_configuration(db,cap.binding,new_charge=True)
    assert await fingerprint(db)==before
