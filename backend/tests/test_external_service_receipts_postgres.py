"""DB128 two-connection races and database-enforced private receipt linkage."""
import asyncio
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.db.models.external_service_receipt import ExternalServiceReceipt as Receipt, ExternalServiceReceiptBlob as Blob, ExternalServiceReceiptEvent as Event
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.schemas.external_service import ExternalServiceVoid
from app.schemas.external_service_receipt import ReceiptRemove
from app.services import external_service as records, external_service_receipt as receipts
from app.services.vehicle_merge import merge_vehicles
from test_external_service import add_vehicle, create
from test_external_service_postgres import blocked_call
from test_external_service_receipts import PDF, error, upload, upload_file, upload_request
from test_operation_execution_postgres import pg_case  # noqa: F401

pytestmark = pytest.mark.asyncio


async def prepare(factory, a):
    async with factory() as db:
        a.record = (await records.mutate(db, a.vehicle.id, a.owner, create())).record
        await db.commit()


async def durable_counts(db, tenant_id, expected):
    for model in (Receipt, Blob, Event):
        assert await db.scalar(select(func.count(model.id)).where(model.tenant_id == tenant_id)) == expected


@pytest.mark.parametrize("same_request", [False, True])
async def test_concurrent_identical_upload_has_one_blob_and_event(pg_case, same_request):
    factory, a = pg_case
    await prepare(factory, a)
    body = upload_request()
    async with factory() as one, factory() as two:
        first = await upload(one, a, body)
        call = upload(two, a, body if same_request else upload_request())
        if same_request:
            second = await blocked_call(two, call, one.commit)
            assert second.replayed and second.receipt.id == first.receipt.id
        else:
            await error("duplicate_receipt", blocked_call(two, call, one.commit))
        await durable_counts(two, a.tenant.id, 1)


async def test_cross_vehicle_request_collision_rolls_back_all_losing_rows(pg_case):
    factory, a = pg_case
    await prepare(factory, a)
    async with factory() as db:
        other = await add_vehicle(db, a)
        other_record = (await records.mutate(db, other.id, a.owner, create())).record
        await db.commit()
    body = upload_request()
    async with factory() as one, factory() as two:
        await upload(one, a, body)
        flushing = asyncio.Event()
        def before_flush(session, context, instances):
            if any(isinstance(row, Event) and row.request_id == body.request_id for row in session.new):
                flushing.set()
        event.listen(two.sync_session, "before_flush", before_flush)
        pending = asyncio.create_task(receipts.mutate(two, other.id, other_record.id, a.owner, body, upload=upload_file()))
        try:
            await asyncio.wait_for(flushing.wait(), 5)
            assert not pending.done()
            await one.commit()
            await error("request_id_conflict", asyncio.wait_for(pending, 5))
            await durable_counts(two, a.tenant.id, 1)
            await receipts.mutate(two, other.id, other_record.id, a.owner, upload_request(), upload=upload_file())
            await two.commit()
            await durable_counts(two, a.tenant.id, 2)
        finally:
            event.remove(two.sync_session, "before_flush", before_flush)
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


async def test_capacity_boundary_serializes_counting_removed_files(pg_case):
    factory, a = pg_case
    await prepare(factory, a)
    async with factory() as db:
        for index in range(9):
            await upload(db, a, file=upload_file(PDF + b" " * index))
        first = (await receipts.page(db, a.vehicle.id, a.record.id, a.owner)).items[0]
        await receipts.mutate(db, a.vehicle.id, a.record.id, a.owner,
            ReceiptRemove(request_id=uuid4(), expected_record_version=1, expected_version=1, reason="Retained"), action="remove", receipt_id=first.id)
        await db.commit()
    async with factory() as one, factory() as two:
        await upload(one, a, file=upload_file(PDF + b" " * 9))
        await error("receipt_capacity", blocked_call(two, upload(two, a, file=upload_file(PDF + b" " * 10)), one.commit))
        assert await two.scalar(select(func.count(Blob.id)).where(Blob.tenant_id == a.tenant.id)) == 10
        assert (await receipts.page(two, a.vehicle.id, a.record.id, a.owner)).retained_count == 10


async def test_receipt_revision_has_one_winner_and_replay_returns_current(pg_case):
    factory, a = pg_case
    await prepare(factory, a)
    async with factory() as db:
        saved = await upload(db, a)
        await db.commit()
    first = ReceiptRemove(request_id=uuid4(), expected_record_version=1, expected_version=1, reason="First")
    second = first.model_copy(update={"request_id": uuid4(), "reason": "Second"})
    async with factory() as one, factory() as two:
        await receipts.mutate(one, a.vehicle.id, a.record.id, a.owner, first, action="remove", receipt_id=saved.receipt.id)
        await error("receipt_changed", blocked_call(two, receipts.mutate(two, a.vehicle.id, a.record.id, a.owner, second, action="remove", receipt_id=saved.receipt.id), one.commit))
        assert (await receipts.history(two, a.vehicle.id, a.record.id, saved.receipt.id, a.owner)).total == 2
        replayed = await receipts.mutate(two, a.vehicle.id, a.record.id, a.owner, first, action="remove", receipt_id=saved.receipt.id)
        assert replayed.replayed and replayed.receipt.version == 2


@pytest.mark.parametrize("void_first", [True, False])
async def test_upload_and_void_obey_locked_record_version(pg_case, void_first):
    factory, a = pg_case
    await prepare(factory, a)
    async with factory() as one, factory() as two:
        async def void(db):
            return await records.mutate(db, a.vehicle.id, a.owner, ExternalServiceVoid(request_id=uuid4(), expected_version=1, reason="QA"), action="void", record_id=a.record.id)
        if void_first:
            await void(one)
            await error("record_changed", blocked_call(two, upload(two, a), one.commit))
            await durable_counts(two, a.tenant.id, 0)
        else:
            await upload(one, a)
            await blocked_call(two, void(two), one.commit)
            await two.commit()
            await durable_counts(two, a.tenant.id, 1)
            assert (await receipts.page(two, a.vehicle.id, a.record.id, a.owner)).record_voided_at


@pytest.mark.parametrize("merge_first", [True, False])
async def test_merge_and_upload_preserve_original_audit_and_current_route(pg_case, merge_first):
    factory, a = pg_case
    await prepare(factory, a)
    async with factory() as db:
        canonical = await add_vehicle(db, a)
        await db.execute(update(Vehicle).where(Vehicle.id == a.vehicle.id).values(vin=canonical.vin))
        await db.commit()
    async with factory() as one, factory() as two:
        async def merge(db):
            return await merge_vehicles(db, tenant_id=a.tenant.id, canonical_id=canonical.id, duplicate_id=a.vehicle.id, merged_by_user_id=a.owner.id, confirm_vin=canonical.vin)
        if merge_first:
            await merge(one)
            await error("receipt_not_found", blocked_call(two, upload(two, a), one.commit))
            await durable_counts(two, a.tenant.id, 0)
        else:
            saved = await upload(one, a)
            await blocked_call(two, merge(two), one.commit)
            await two.commit()
            current = (await receipts.page(two, canonical.id, a.record.id, a.owner)).items[0]
            assert current.vehicle_id == canonical.id and current.uploaded_vehicle_id == a.vehicle.id
            audit = await receipts.history(two, canonical.id, a.record.id, saved.receipt.id, a.owner)
            assert audit.items[0].snapshot.vehicle_id == a.vehicle.id
            assert (await receipts.download(two, canonical.id, a.record.id, saved.receipt.id, a.owner))[0] == PDF
            await error("receipt_not_found", receipts.download(two, a.vehicle.id, a.record.id, saved.receipt.id, a.owner))
            await durable_counts(two, a.tenant.id, 1)


async def test_postgres_head_and_composite_fk_unique_size_constraints(pg_case):
    factory, a = pg_case
    await prepare(factory, a)
    async with factory() as db:
        assert await db.scalar(text("select version_num from alembic_version")) == "172_external_service_receipts"
        saved = await upload(db, a)
        another_record = (await records.mutate(db, a.vehicle.id, a.owner, create())).record
        other = Tenant(id=uuid4(), name="DB128 constraint QA", slug=f"db128-{uuid4().hex}")
        db.add(other)
        await db.commit()
        receipt = await db.scalar(select(Receipt).where(Receipt.id == saved.receipt.id))
        blob = await db.scalar(select(Blob).where(Blob.receipt_id == receipt.id))
        evidence = await db.scalar(select(Event).where(Event.receipt_id == receipt.id))
        for model, identity, changes in [
            (Receipt, receipt.id, dict(tenant_id=other.id)),
            (Receipt, receipt.id, dict(record_id=uuid4())),
            (Receipt, receipt.id, dict(size_bytes=0)),
            (Receipt, receipt.id, dict(size_bytes=5242881)),
            (Receipt, receipt.id, dict(version=0)),
            (Receipt, receipt.id, dict(media_type="text/html")),
            (Blob, blob.id, dict(tenant_id=other.id)),
            (Blob, blob.id, dict(receipt_id=uuid4())),
            (Blob, blob.id, dict(content=b"")),
            (Blob, blob.id, dict(content=b"x" * 5242881)),
            (Event, evidence.id, dict(tenant_id=other.id)),
            (Event, evidence.id, dict(record_id=another_record.id)),
            (Event, evidence.id, dict(version=0)),
            (Event, evidence.id, dict(action="delete")),
        ]:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(update(model).where(model.id == identity).values(**changes))
        for model, original, changes in [
            (Receipt, receipt, {}),
            (Blob, blob, {"content": PDF}),
            (Event, evidence, {"version": 2}),
            (Event, evidence, {"request_id": uuid4()}),
        ]:
            values = {column.name: getattr(original, column.name) for column in model.__table__.columns if column.name not in {"id", "content"}}
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(model(id=uuid4(), **(values | changes)))
                    await db.flush()
        # Same bytes on another authorized record are valid, no cross-record dedupe.
        await receipts.mutate(db, a.vehicle.id, another_record.id, a.owner, upload_request(), upload=upload_file())
        await db.execute(delete(Tenant).where(Tenant.id == other.id))
        await db.commit()
        await durable_counts(db, a.tenant.id, 2)
