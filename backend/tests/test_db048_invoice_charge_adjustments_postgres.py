"""Real lock and immutable audit proofs on explicitly disposable PostgreSQL."""
import os
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from tests.test_db048_tax_exemption import setup
from tests.test_db048_tax_exemption_postgres import load
from tests.test_db048_invoice_charge_adjustments import adjust
from app.services.invoice_settlement_service import create_attempt, SettlementDomainError

pytestmark = pytest.mark.skipif(not os.environ.get("DB048_POSTGRES_URL"), reason="requires disposable migrated PostgreSQL")


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["adjustment", "payment", "competing_adjustment"])
@pytest.mark.parametrize("fee", [None, False])
async def test_serialized_charge_changes_and_audit(monkeypatch, winner, fee):
    engine = create_async_engine(os.environ["DB048_POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as seed:
            ctx = await setup(seed, monkeypatch)
            ids = ctx[0].id, ctx[1].id, ctx[3].id
            await seed.commit()
        async with sessions() as first, sessions() as second:
            a, b = await load(first, ids), await load(second, ids)
            async def payment(db, ctx):
                return await create_attempt(db, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
                    actor=ctx[1], amount=Decimal("10"), rail="check", expected_settlement_version=1,
                    idempotency_key=f"payment-{uuid4()}", source="staff", subject_type="staff", subject_id=ctx[1].id)
            if winner == "payment":
                await payment(first, a)
            else:
                await adjust(first, a, tax=True, supplies=False, fee=fee)
            if winner == "adjustment":
                with pytest.raises(SettlementDomainError) as busy:
                    await payment(second, b)
                assert busy.value.code == "invoice_busy"
                await second.rollback()
                await first.commit()
                b = await load(second, ids)
                with pytest.raises(SettlementDomainError) as failure:
                    await payment(second, b)
                assert failure.value.code == "stale_settlement_version"
            else:
                with pytest.raises(SettlementDomainError) as busy:
                    await adjust(second, b, tax=True, fee=fee)
                assert busy.value.code == "invoice_busy"
                await second.rollback()
                await first.commit()
                b = await load(second, ids)
                with pytest.raises(SettlementDomainError):
                    await adjust(second, b, tax=True, version=1, fee=fee)
            await second.rollback()
        if winner != "payment":
            async with sessions() as check:
                for command in ("UPDATE invoice_charge_adjustments SET version=99 WHERE invoice_id=:id",
                                "DELETE FROM invoice_charge_adjustments WHERE invoice_id=:id"):
                    with pytest.raises(Exception, match="immutable"):
                        await check.execute(text(command), {"id": ids[2]})
                    await check.rollback()
                with pytest.raises(Exception, match="tenant mismatch"):
                    await check.execute(text("""INSERT INTO invoice_charge_adjustments
                      (id,tenant_id,invoice_id,version,idempotency_key,request_hash,evidence)
                      SELECT :audit_id,:tenant,invoice_id,99,:key,request_hash,evidence
                      FROM invoice_charge_adjustments WHERE invoice_id=:id LIMIT 1"""),
                      {"audit_id": uuid4(), "tenant": uuid4(), "key": str(uuid4()), "id": ids[2]})
                await check.rollback()
    finally:
        await engine.dispose()
