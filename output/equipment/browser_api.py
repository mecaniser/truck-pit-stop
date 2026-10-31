"""Loopback-only test API: real routes/JWT auth, disposable in-memory database."""
import os
os.environ.update(DATABASE_URL='sqlite+aiosqlite://', SECRET_KEY='db148-isolated-browser-test-key-32-characters', TWILIO_ACCOUNT_SID='AC00000000000000000000000000000000', TWILIO_AUTH_TOKEN='fixture', ENVIRONMENT='test')
import sys, asyncio, json
from pathlib import Path
from uuid import uuid4
from decimal import Decimal
root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(root / 'backend'), str(root / 'backend/tests')]
import conftest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.api.v1.router import api_router
from app.db.session import get_db
from app.db.models import Tenant, Customer, User, Vehicle, RepairOrder, Invoice
from app.db.models.user import UserRole
from app.db.models.invoice import InvoiceStatus
from app.db.models.repair_order import RepairOrderStatus
from app.core.security import create_access_token
from app.core import dependencies
from app.core.rate_limit import limiter
from app.api.v1.endpoints import customers, vehicles
import uvicorn

async def main():
    import tempfile
    temporary = tempfile.TemporaryDirectory(prefix='db148-browser-')
    class TempFactory:
        def mktemp(self, name):
            folder = Path(temporary.name) / name
            folder.mkdir()
            return folder
    schema = conftest._sqlite_schema_template.__wrapped__(TempFactory())
    fixture = conftest._db_engine.__wrapped__(next(schema))
    engine = await fixture.__anext__()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    from app.main import settlement_domain_exception_handler
    from app.services.invoice_settlement_service import SettlementDomainError
    app.add_exception_handler(SettlementDomainError, settlement_domain_exception_handler)
    app.state.limiter = limiter
    limiter.enabled = False
    app.include_router(api_router, prefix='/api/v1')
    @app.get('/health')
    def health(): return {'status':'ok','fixture':'DB148','source':str(root)}
    async def db():
        async with factory() as session: yield session
    app.dependency_overrides[get_db] = db
    async def state(*_): return (False, 0)
    dependencies.get_auth_token_state = state
    async def no_decode(*_, **__): pass
    customers.sync_vehicle_nhtsa_snapshot = no_decode
    vehicles.sync_vehicle_nhtsa_snapshot = no_decode
    async with factory() as session:
        tenant = Tenant(id=uuid4(), name='DB148 Isolated Test Shop', slug='db148-browser', labor_rate=Decimal('100'))
        company = Customer(id=uuid4(), tenant_id=tenant.id, first_name='Ellis', last_name='Fixture', company_name='Ellis Logistics Test', email='db148@example.test')
        owner = User(id=uuid4(), tenant_id=tenant.id, email='owner-db148@example.test', first_name='Test', last_name='Owner', hashed_password='unused', role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True)
        session.add_all([tenant, company, owner]); await session.flush()
        assets = []
        for typ, unit in [('tractor','603'),('tractor','609'),('trailer','T1003130'),('trailer','T1003142')]:
            vehicle = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=company.id, make='Fixture', model='Tractor' if typ=='tractor' else 'Dry Van', equipment_type=typ, unit_number=unit)
            session.add(vehicle); await session.flush()
            from app.services.vehicle_identity import seed_vehicle_account_relationships
            await seed_vehicle_account_relationships(session, vehicle, company)
            order = RepairOrder(id=uuid4(), tenant_id=tenant.id, customer_id=company.id, vehicle_id=vehicle.id, order_number=f'TEST-{unit}', description=f'Maintenance for {unit}', status=RepairOrderStatus.INVOICED)
            session.add(order); await session.flush()
            invoice = Invoice(id=uuid4(), tenant_id=tenant.id, repair_order_id=order.id, billed_customer_id=company.id, invoice_number=f'TEST-INV-{unit}', subtotal=Decimal('100'), total_amount=Decimal('100'), status=InvoiceStatus.SENT)
            session.add(invoice)
            assets.append({'id':str(vehicle.id),'unit':unit,'type':typ,'order_id':str(order.id),'invoice_id':str(invoice.id)})
        await session.commit()
        user = dict(id=str(owner.id), tenant_id=str(tenant.id), customer_id=None, email=owner.email, first_name='Test', last_name='Owner', role='garage_owner', is_active=True, phone=None, tenant_name=tenant.name)
        token = create_access_token({'sub':str(owner.id)})
        (root/'output/equipment/browser_fixture.json').write_text(json.dumps({'user':user,'token':token,'company_id':str(company.id),'assets':assets}))
    try:
        await uvicorn.Server(uvicorn.Config(app, host='127.0.0.1',port=8017,log_level='warning')).serve()
    finally:
        await fixture.aclose()
        schema.close()
        temporary.cleanup()
asyncio.run(main())
