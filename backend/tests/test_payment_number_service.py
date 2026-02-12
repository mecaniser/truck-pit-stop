from __future__ import annotations

from uuid import uuid4

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
import app.db.models  # noqa: F401
from app.db.models.payment_number_counter import PaymentNumberCounter
from app.db.models.tenant import Tenant
from app.services.payment_number_service import allocate_next_payment_number


@pytest.mark.asyncio
async def test_allocate_next_payment_number_rolls_back_without_advancing():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    tenant_id = uuid4()
    async with session_factory() as db:
        db.add(Tenant(id=tenant_id, name="Rollback Garage", slug="rollback-garage"))
        await db.commit()

    # Simulate a failure after allocation and roll the transaction back.
    async with session_factory() as db:
        with pytest.raises(RuntimeError, match="forced failure"):
            await allocate_next_payment_number(db, tenant_id)
            raise RuntimeError("forced failure")
        await db.rollback()

    async with session_factory() as db:
        next_number = await allocate_next_payment_number(db, tenant_id)
        await db.commit()
        assert next_number.endswith("000001")

        result = await db.execute(
            select(PaymentNumberCounter).where(PaymentNumberCounter.tenant_id == tenant_id)
        )
        counter = result.scalar_one()
        assert counter.last_number == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_allocate_next_payment_number_increments_monotonically():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    tenant_id = uuid4()
    async with session_factory() as db:
        db.add(Tenant(id=tenant_id, name="Counter Garage", slug="counter-garage"))
        await db.commit()

    async with session_factory() as db:
        first = await allocate_next_payment_number(db, tenant_id)
        await db.commit()

    async with session_factory() as db:
        second = await allocate_next_payment_number(db, tenant_id)
        await db.commit()

    assert first.endswith("000001")
    assert second.endswith("000002")
    await engine.dispose()
