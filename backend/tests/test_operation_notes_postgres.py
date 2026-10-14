"""DB118 real transactions on the existing opt-in isolated local DB110 database."""
import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, event, func, select

from app.db.base import Base
from app.db.models.labor import Labor
from app.db.models.repair_order import RepairOrderStatus as Status
from app.db.models.repair_order_history import RepairOrderHistoryEvent as Event
from app.db.models.tenant import Tenant
from app.schemas.operation_execution import OperationAssignment
from app.services import operation_execution as ops, operation_notes as notes
from test_operation_execution import seed
from test_operation_execution_postgres import pg_case, conflict  # noqa: F401
from test_operation_notes import body

pytestmark = pytest.mark.asyncio


async def test_competing_same_key_replays_one_note_after_contention(pg_case):
    factory, a = pg_case
    request = body()
    async with factory() as one, factory() as two:
        first, created = await notes.append(one, a.order.id, a.lines[0].id, a.owner, request)
        assert created
        await conflict(notes.append(two, a.order.id, a.lines[0].id, a.owner, request), 'another workflow')
        await two.rollback(); await one.commit()
        replay, created = await notes.append(two, a.order.id, a.lines[0].id, a.owner, request)
        assert not created and replay == first
        assert await two.scalar(select(func.count(Event.id)).where(Event.repair_order_id == a.order.id)) == 1


@pytest.mark.parametrize('transition', ['reassign', 'remove', 'delete_order', 'finalize', 'price_lock'])
async def test_lifecycle_or_membership_wins_note_race(pg_case, transition):
    factory, a = pg_case
    async with factory() as one, factory() as two:
        order = await ops.load_order(one, a.order.id, a.owner, write=True)
        line = await ops.load_labor(one, order, a.lines[1].id)
        expected = 409
        if transition == 'reassign':
            await ops.assign(one, order.id, line.id, a.owner, OperationAssignment(mechanic_id=a.lead.id, expected_version=0))
            expected = 403
        elif transition == 'remove':
            await one.delete(line)
            expected = 404
        elif transition == 'delete_order':
            order.deleted_at = datetime.now(UTC)
            expected = 404
        elif transition == 'finalize':
            order.status = Status.COMPLETED
        else:
            order.pricing_locked_at = datetime.now(UTC)
            order.pricing_lock_reason = 'invoice_created'
        await one.flush()
        request = body()
        await conflict(notes.append(two, order.id, line.id, a.helper, request), 'another workflow')
        await two.rollback(); await one.commit()
        with pytest.raises(HTTPException) as rejected:
            await notes.append(two, order.id, line.id, a.helper, request)
        assert rejected.value.status_code == expected
        assert await two.scalar(select(func.count(Event.id)).where(Event.event_type == notes.EVENT_TYPE, Event.repair_order_id == order.id)) == 0


async def test_note_wins_finalization_preserves_note_and_finalized_retry(pg_case):
    factory, a = pg_case
    request = body()
    async with factory() as one, factory() as two:
        first, _ = await notes.append(one, a.order.id, a.lines[0].id, a.owner, request)
        await conflict(ops.load_order(two, a.order.id, a.owner, write=True), 'another workflow')
        await two.rollback(); await one.commit()
        order = await ops.load_order(two, a.order.id, a.owner, write=True)
        order.status = Status.COMPLETED
        await two.commit()
        replay, created = await notes.append(one, a.order.id, a.lines[0].id, a.owner, request)
        assert replay == first and not created
        await conflict(notes.append(one, a.order.id, a.lines[0].id, a.owner, body()), 'read-only')


async def test_cross_tenant_primary_key_insert_race_is_safe_and_outer_transaction_survives(pg_case):
    factory, a = pg_case
    async with factory() as db:
        b = await seed(db)
    request = body('Different tenants must never receive each others note')
    try:
        async with factory() as one, factory() as two:
            first, _ = await notes.append(one, a.order.id, a.lines[0].id, a.owner, request)
            # Signal just before the competing note flush. Its initial UUID
            # lookup cannot see the first transaction's uncommitted insert.
            flushing = asyncio.Event()
            def before_flush(session, context, instances):
                if any(isinstance(obj, Event) and obj.id == request.id for obj in session.new):
                    flushing.set()
            event.listen(two.sync_session, 'before_flush', before_flush)
            pending = asyncio.create_task(notes.append(two, b.order.id, b.lines[0].id, b.owner, request))
            try:
                await asyncio.wait_for(flushing.wait(), timeout=5)
                assert not pending.done()
                await one.commit()
                with pytest.raises(HTTPException) as rejected:
                    await asyncio.wait_for(pending, timeout=5)
                assert rejected.value.status_code == 409 and rejected.value.detail == notes.COLLISION_REASON
                # Savepoint rollback leaves the second transaction usable.
                second, created = await notes.append(two, b.order.id, b.lines[0].id, b.owner, body('Second shop private note'))
                assert created and second.id != first.id
                await two.commit()
                b_notes = await notes.page(two, b.order.id, b.lines[0].id, b.owner)
                assert b_notes.items == [second]
            finally:
                event.remove(two.sync_session, 'before_flush', before_flush)
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
    finally:
        async with factory() as db:
            for table in reversed(Base.metadata.sorted_tables):
                if 'tenant_id' in table.c:
                    await db.execute(delete(table).where(table.c.tenant_id == b.tenant.id))
            await db.execute(delete(Tenant).where(Tenant.id == b.tenant.id))
            await db.commit()
