"""Run only against an explicitly supplied disposable migrated PostgreSQL DB."""
import asyncio
import os
from decimal import Decimal
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models.invoice import Invoice
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.db.models.invoice_settlement import InvoiceSettlement
from app.services.invoice_settlement_service import create_attempt, SettlementDomainError
from tests.test_db048_tax_exemption import setup, apply

pytestmark = pytest.mark.skipif(not os.environ.get("DB048_POSTGRES_URL"), reason="requires disposable migrated PostgreSQL")


async def load(db, ids):
    tenant = await db.get(Tenant, ids[0])
    owner = await db.get(User, ids[1])
    invoice = await db.scalar(select(Invoice).where(Invoice.id == ids[2]).options(
        selectinload(Invoice.repair_order).selectinload(RepairOrder.customer)))
    settlement = await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == invoice.id))
    return tenant, owner, invoice.repair_order.customer, invoice, settlement


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["exemption", "payment", "exemption_before_payment"])
async def test_serialization(monkeypatch, winner):
    engine = create_async_engine(os.environ["DB048_POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as seed:
            ctx = await setup(seed, monkeypatch)
            ids = (ctx[0].id, ctx[1].id, ctx[3].id)
            await seed.commit()
        async with sessions() as first, sessions() as second:
            a, b = await load(first, ids), await load(second, ids)
            async def payment(db, ctx):
                return await create_attempt(db, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
                    actor=ctx[1], amount=Decimal("10"), rail="check", expected_settlement_version=1,
                    idempotency_key="postgres-tax-payment", source="staff", subject_type="staff", subject_id=ctx[1].id)
            if winner == "payment":
                await payment(first, a)
            else:
                await apply(first, a)
            if winner == "exemption_before_payment":
                pending = asyncio.create_task(payment(second, b))
                await asyncio.sleep(0.05)
                assert not pending.done(), "Payment should wait for exemption's settlement lock"
                await first.commit()
                with pytest.raises(SettlementDomainError) as rejected:
                    await pending
                assert rejected.value.code == "stale_settlement_version"
                await second.rollback()
            else:
                with pytest.raises(SettlementDomainError) as busy:
                    await apply(second, b)
                assert busy.value.code == "invoice_busy"
                await second.rollback()
                await first.commit()
                b = await load(second, ids)
                if winner == "exemption":
                    await apply(second, b)  # exact replay
                    assert b[4].version == 2
                else:
                    with pytest.raises(SettlementDomainError):
                        await apply(second, b, version=b[4].version)
                    assert b[3].tax_exemption is None
                await second.rollback()
        if winner != "payment":
            async with sessions() as check:
                row = (await check.execute(text("SELECT payload FROM invoice_read_models WHERE invoice_id=:id"), {"id": ids[2]})).scalar_one()
                assert Decimal(str(row["tax_amount"])) == 0
                assert Decimal(str(row["total_amount"])) == Decimal("109")
                # The database, not only the endpoint, prevents removing audit.
                with pytest.raises(Exception, match="immutable"):
                    await check.execute(text("UPDATE invoices SET tax_exemption=NULL WHERE id=:id"), {"id": ids[2]})
                await check.rollback()
    finally:
        await engine.dispose()
