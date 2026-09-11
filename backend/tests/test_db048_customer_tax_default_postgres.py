"""Explicit disposable PostgreSQL only; actual customer/issuance serialization."""
import asyncio
import os
from decimal import Decimal
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload
from app.db.models.customer import Customer
from app.db.models.customer_tax_exemption import CustomerTaxExemptionAudit
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.api.v1.endpoints.invoices import auto_create_invoice_for_order
from app.schemas.customer import CustomerTaxExemptionWrite
from app.services.customer_tax_exemption import update_setting
from app.services.invoice_settlement_service import SettlementDomainError
from tests.test_db048_cash import context
from uuid import uuid4

pytestmark = pytest.mark.skipif(not os.environ.get("DB048_POSTGRES_URL"), reason="requires disposable migrated PostgreSQL")


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["toggle", "issuance", "competing_toggle"])
async def test_customer_tax_serialization_and_audit_trigger(monkeypatch, winner):
    engine = create_async_engine(os.environ["DB048_POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as seed:
            ctx = await context(seed, monkeypatch)
            ctx[0].sales_tax_rate = Decimal("8.5")
            ctx[3].status = InvoiceStatus.CANCELLED
            order = await seed.get(RepairOrder, ctx[3].repair_order_id)
            order.total_labor_cost = Decimal("100")
            ids = ctx[0].id, ctx[1].id, ctx[2].id, order.id
            await seed.commit()
        async with sessions() as first, sessions() as second:
            async def toggle(db, key):
                return await update_setting(db, ids[2], await db.get(User, ids[1]),
                    CustomerTaxExemptionWrite(tax_exempt=True, expected_version=0), key)
            async def issue(db):
                order = await db.scalar(select(RepairOrder).where(RepairOrder.id == ids[3]).options(
                    selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle)))
                return await auto_create_invoice_for_order(db, order, await db.get(Tenant, ids[0]), ids[1],
                    commit=False, notify=False)
            issued = None
            if winner == "issuance": issued = await issue(first)
            else: await toggle(first, "first-setting")
            pending = asyncio.create_task(issue(second) if winner == "toggle" else toggle(second, "second-setting"))
            await asyncio.sleep(0.05)
            assert not pending.done(), "Customer row must serialize setting and issuance"
            await first.commit()
            if winner == "competing_toggle":
                with pytest.raises(SettlementDomainError) as stale: await pending
                assert stale.value.code == "stale_customer_tax_version"
                await second.rollback()
            else:
                result = await pending
                if winner == "toggle": issued = result
                await second.commit()
                assert issued.tax_amount == 0 if winner == "toggle" else issued.tax_amount > 0
                assert bool(issued.tax_exemption) == (winner == "toggle")
        async with sessions() as check:
            assert (await check.get(Customer, ids[2])).tax_exemption_version == 1
            for command in ("UPDATE customer_tax_exemption_audits SET version=99 WHERE customer_id=:id",
                            "DELETE FROM customer_tax_exemption_audits WHERE customer_id=:id"):
                with pytest.raises(Exception, match="immutable"):
                    await check.execute(text(command), {"id": ids[2]})
                await check.rollback()
            with pytest.raises(Exception, match="tenant mismatch"):
                await check.execute(text("""INSERT INTO customer_tax_exemption_audits
                    (id,tenant_id,customer_id,version,idempotency_key,request_hash,evidence)
                    SELECT :audit_id,:wrong_tenant,customer_id,99,:key,request_hash,evidence
                    FROM customer_tax_exemption_audits WHERE customer_id=:customer_id LIMIT 1"""),
                    {"audit_id": uuid4(), "wrong_tenant": uuid4(), "key": str(uuid4()), "customer_id": ids[2]})
            await check.rollback()
            if issued:
                stored = await check.get(Invoice, issued.id)
                assert bool(stored.tax_exemption) == (winner == "toggle")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_customer_key_collision_rolls_back_only_loser(monkeypatch):
    engine = create_async_engine(os.environ["DB048_POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as seed:
            ctx = await context(seed, monkeypatch)
            other = Customer(tenant_id=ctx[0].id, first_name="Other", last_name="Customer", email=f"{uuid4()}@example.com")
            seed.add(other)
            await seed.flush()
            owner_id, customer_id, other_id = ctx[1].id, ctx[2].id, other.id
            await seed.commit()
        async with sessions() as first, sessions() as second:
            body = CustomerTaxExemptionWrite(tax_exempt=True, expected_version=0)
            key = f"collision-{uuid4()}"
            await update_setting(first, customer_id, await first.get(User, owner_id), body, key)
            owner = await second.get(User, owner_id)
            pending = asyncio.create_task(update_setting(second, other_id, owner, body, key))
            await asyncio.sleep(0.05)
            assert not pending.done()
            await first.commit()
            with pytest.raises(SettlementDomainError) as conflict: await pending
            assert conflict.value.code == "idempotency_conflict"
            await second.commit()
        async with sessions() as check:
            other = await check.get(Customer, other_id)
            assert not other.tax_exempt and other.tax_exemption_version == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_merge_preserves_archived_customer_audit_and_winner_setting(monkeypatch):
    from app.api.v1.endpoints.customers import merge_customers
    from app.schemas.customer import CustomerMergeRequest
    engine = create_async_engine(os.environ["DB048_POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            ctx = await context(db, monkeypatch)
            loser = Customer(tenant_id=ctx[0].id, first_name="Duplicate", last_name="Customer", email=f"{uuid4()}@example.com")
            db.add(loser)
            await db.flush()
            loser_id = loser.id
            await update_setting(db, loser_id, ctx[1], CustomerTaxExemptionWrite(tax_exempt=True, expected_version=0), f"merge-{uuid4()}")
            audit = await db.scalar(select(CustomerTaxExemptionAudit).where(CustomerTaxExemptionAudit.customer_id == loser_id))
            evidence = dict(audit.evidence)
            await db.commit()
            await merge_customers(CustomerMergeRequest(winner_id=ctx[2].id, loser_id=loser_id), db, ctx[1])
            assert await db.get(Customer, loser_id) is None
            await db.refresh(audit)
            assert audit.customer_id == loser_id and audit.evidence == evidence
            winner = await db.get(Customer, ctx[2].id)
            assert not winner.tax_exempt and winner.tax_exemption_version == 0
    finally:
        await engine.dispose()
