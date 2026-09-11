"""Actual Fleet locks, unique identity, immutable evidence and downgrade fence."""
import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.models.customer import Customer
from app.db.models.invoice_settlement import InvoicePaymentAttempt, InvoiceSettlement
from app.services.invoice_settlement_service import SettlementDomainError
from tests.test_db048_cash import context
from tests.test_db048_fleet_payment import create, confirm, evidence
from tests.test_db048_tax_exemption_postgres import load
from tests.test_db048_invoice_settlements import _add_eligible_invoice

pytestmark = pytest.mark.skipif(not os.environ.get("DB048_POSTGRES_URL"), reason="requires disposable PostgreSQL at146")


@pytest.mark.asyncio
@pytest.mark.parametrize("cross_customer", [False, True])
async def test_fleet_reference_confirmation_serializes_and_db_enforces_identity(monkeypatch, cross_customer):
    engine = create_async_engine(os.environ["DB048_POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as seed:
            ctx = await context(seed, monkeypatch)
            customer = ctx[2]
            if cross_customer:
                customer = Customer(tenant_id=ctx[0].id, first_name="Other", last_name="Fleet payer",
                                    email=f"{uuid4()}@example.com")
                seed.add(customer)
                await seed.flush()
            invoice = await _add_eligible_invoice(seed, tenant=ctx[0], customer=customer,
                reference_invoice=ctx[3], with_shadow_settlement=True)
            settlement = await seed.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == invoice.id))
            other = ctx[0], ctx[1], customer, invoice, settlement
            first = await create(seed, ctx)
            second = await create(seed, other, key="fleet-other")
            ids = (ctx[0].id, ctx[1].id, ctx[3].id), (ctx[0].id, ctx[1].id, invoice.id)
            attempt_ids = first.attempt.id, second.attempt.id
            await seed.commit()
        async with sessions() as first_db, sessions() as second_db:
            a, b = await load(first_db, ids[0]), await load(second_db, ids[1])
            first = await first_db.get(InvoicePaymentAttempt, attempt_ids[0])
            second = await second_db.get(InvoicePaymentAttempt, attempt_ids[1])
            await confirm(first_db, a, first)
            task = asyncio.create_task(confirm(second_db, b, second))
            await asyncio.sleep(0.05)
            assert not task.done(), "The shop's instrument receipt confirmations must serialize"
            await first_db.commit()
            with pytest.raises(SettlementDomainError, match="already been recorded"):
                await task
            await second_db.rollback()
        async with sessions() as check:
            first = await check.get(InvoicePaymentAttempt, attempt_ids[0])
            second = await check.get(InvoicePaymentAttempt, attempt_ids[1])
            assert first.state == "confirmed" and second.state == "pending"
            with pytest.raises(Exception, match="uq_invoice_payment_fleet_reference|uq_invoice_payment_manual_reference"):
                await check.execute(text("UPDATE invoice_payment_attempts SET manual_reference_fingerprint=:fingerprint WHERE id=:id"),
                    {"fingerprint": first.manual_reference_fingerprint, "id": second.id})
            await check.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_fleet_evidence_database_immutable_and_populated_downgrade_refused(monkeypatch):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    engine = create_async_engine(os.environ["DB048_POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            ctx = await context(db, monkeypatch)
            made = await create(db, ctx, data=evidence("Other", fleet_provider_name="Fleet Union"))
            attempt_id = made.attempt.id
            await db.commit()
            with pytest.raises(Exception, match="evidence is immutable"):
                await db.execute(text("UPDATE invoice_payment_attempts SET manual_evidence=manual_evidence::jsonb || '{\"reference_number\":\"changed\"}'::jsonb WHERE id=:id"), {"id": attempt_id})
            await db.rollback()
        async with engine.begin() as connection:
            def downgrade(sync):
                from pathlib import Path
                import importlib.util
                path = Path(__file__).resolve().parents[1] / "alembic/versions/146_fleet_payment_rail.py"
                spec = importlib.util.spec_from_file_location("fleet_migration146", path)
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)
                with Operations.context(MigrationContext.configure(sync)):
                    migration.downgrade()
            with pytest.raises(RuntimeError, match="must be preserved"):
                await connection.run_sync(downgrade)
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "146_fleet_payment_rail"
    finally:
        await engine.dispose()
