"""Real row-lock/FK proof; only an explicitly disposable local C3 database."""

import asyncio
import os
from uuid import uuid4
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_issue import (
    VehicleIssue,
    VehicleIssueEvent,
    VehicleIssueRequest,
    VehicleIssueLink,
)
from app.schemas import vehicle_issue as wire
from app.services import vehicle_issues as service
from app.services.vehicle_merge import (
    merge_vehicles,
    VehicleMergeError,
    load_merge_pair,
    validate_merge_pair,
)
from tests.test_db099_recommended_work import customer, vehicle, order, actor

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def pg():
    raw = os.environ.get("DB146_POSTGRES_TEST_URL")
    if not raw:
        pytest.skip("requires disposable migrated PostgreSQL DB146 database")
    url = make_url(raw)
    if url.host not in ("localhost", "127.0.0.1") or not (
        url.database or ""
    ).startswith("db146_test_"):
        raise RuntimeError("Only an isolated local db146_test_ database is permitted")
    engine = create_async_engine(raw)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        tenant = Tenant(name="C3 PG Fiction", slug=f"c3-pg-{uuid4().hex}")
        other = Tenant(name="C3 PG Foreign", slug=f"c3-pg-{uuid4().hex}")
        db.add_all([tenant, other])
        await db.flush()
        payer = await customer(db, tenant)
        truck = await vehicle(db, tenant, payer)
        twin = await vehicle(db, tenant, payer)
        owner = await actor(db, tenant, UserRole.GARAGE_OWNER)
        target = await order(db, tenant, payer, truck)
        foreign_payer = await customer(db, other)
        foreign_truck = await vehicle(db, other, foreign_payer)
        foreign_order = await order(db, other, foreign_payer, foreign_truck)
        await db.commit()
    yield factory, dict(
        tenant=tenant,
        other=other,
        payer=payer,
        truck=truck,
        twin=twin,
        owner=owner,
        target=target,
        foreign_truck=foreign_truck,
        foreign_order=foreign_order,
    )
    await engine.dispose()


async def blocked(factory, pid):
    async def observe():
        async with factory() as monitor:
            while True:
                waiting = await monitor.scalar(
                    text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid}
                )
                if waiting:
                    return
                await asyncio.sleep(0.01)

    await asyncio.wait_for(observe(), timeout=5)


async def create(db, a, truck=None, key=None):
    return await service.mutate(
        db,
        (truck or a["truck"]).id,
        a["owner"],
        wire.IssueCreate(request_id=key or uuid4(), description="Fictional follow-up"),
        operation="create",
    )


async def merge(db, a):
    return await merge_vehicles(
        db,
        tenant_id=a["tenant"].id,
        canonical_id=a["truck"].id,
        duplicate_id=a["twin"].id,
        merged_by_user_id=a["owner"].id,
        confirm_vin=a["truck"].vin,
    )


async def test_create_first_blocks_merge_without_moving_history(pg):
    factory, a = pg
    async with factory() as preview:
        kept, losing = await load_merge_pair(
            preview, a["tenant"].id, a["truck"].id, a["twin"].id
        )
        await validate_merge_pair(preview, kept, losing)
        await service.guard_vehicle_merge(preview, kept, losing)
    async with factory() as first, factory() as second:
        result, _ = await create(first, a, a["twin"])
        pid = await second.scalar(text("SELECT pg_backend_pid()"))
        task = asyncio.create_task(merge(second, a))
        await blocked(factory, pid)
        await first.commit()
        with pytest.raises(VehicleMergeError, match="Truck issue history"):
            await asyncio.wait_for(task, timeout=5)
        await second.rollback()
    async with factory() as db:
        assert (await db.get(Vehicle, a["twin"].id)).deleted_at is None
        assert (await db.get(VehicleIssue, result.issue.id)).vehicle_id == a["twin"].id


@pytest.mark.parametrize("destination", ["losing", "kept"])
async def test_merge_first_waiter_reloads_vehicle(pg, destination):
    factory, a = pg
    target = a["twin"] if destination == "losing" else a["truck"]
    async with factory() as first, factory() as second:
        # Prime the identity map before merge; populate_existing must replace it.
        cached = await second.get(Vehicle, target.id)
        assert cached.deleted_at is None
        await merge(first, a)
        pid = await second.scalar(text("SELECT pg_backend_pid()"))
        task = asyncio.create_task(create(second, a, target))
        await blocked(factory, pid)
        await first.commit()
        if destination == "losing":
            with pytest.raises(HTTPException) as error:
                await asyncio.wait_for(task, timeout=5)
            assert (
                error.value.status_code == 404
                and error.value.detail["code"] == "issue_context_not_found"
            )
            await second.rollback()
        else:
            result, _ = await asyncio.wait_for(task, timeout=5)
            assert result.issue.vehicle_id == a["truck"].id
            await second.commit()
    async with factory() as db:
        assert await db.scalar(
            select(func.count())
            .select_from(VehicleIssue)
            .where(VehicleIssue.tenant_id == a["tenant"].id)
        ) == (0 if destination == "losing" else 1)


@pytest.mark.parametrize(
    "scenario", ["same_key", "stale_edit", "two_link_targets", "cross_vehicle_key"]
)
async def test_metadata_concurrency_receipts_and_versions(pg, scenario):
    factory, a = pg
    key = uuid4()
    async with factory() as first, factory() as second:
        if scenario in ("same_key", "cross_vehicle_key"):
            first_result, _ = await create(first, a, key=key)
            call = lambda: create(
                second,
                a,
                a["twin"] if scenario == "cross_vehicle_key" else a["truck"],
                key,
            )
        else:
            created, _ = await create(first, a)
            await first.commit()
            identity = created.issue.id
            if scenario == "stale_edit":
                await service.mutate(
                    first,
                    a["truck"].id,
                    a["owner"],
                    wire.IssueEdit(
                        request_id=uuid4(),
                        expected_version=1,
                        description="First editor",
                    ),
                    operation="edit",
                    issue_id=identity,
                )
                call = lambda: service.mutate(
                    second,
                    a["truck"].id,
                    a["owner"],
                    wire.IssueEdit(
                        request_id=uuid4(),
                        expected_version=1,
                        description="Second editor",
                    ),
                    operation="edit",
                    issue_id=identity,
                )
            else:
                async with factory() as seed:
                    alternate = await order(seed, a["tenant"], a["payer"], a["truck"])
                    await seed.commit()
                await service.mutate(
                    first,
                    a["truck"].id,
                    a["owner"],
                    wire.IssueLinkCreate(
                        request_id=uuid4(),
                        expected_version=1,
                        target_order_id=a["target"].id,
                    ),
                    operation="link",
                    issue_id=identity,
                )
                call = lambda: service.mutate(
                    second,
                    a["truck"].id,
                    a["owner"],
                    wire.IssueLinkCreate(
                        request_id=uuid4(),
                        expected_version=1,
                        target_order_id=alternate.id,
                    ),
                    operation="link",
                    issue_id=identity,
                )
        pid = await second.scalar(text("SELECT pg_backend_pid()"))
        task = asyncio.create_task(call())
        await blocked(factory, pid)
        await first.commit()
        if scenario == "same_key":
            replayed, _ = await asyncio.wait_for(task, timeout=5)
            assert replayed.replayed and replayed.issue.id == first_result.issue.id
            await second.commit()
        else:
            with pytest.raises(HTTPException) as error:
                await asyncio.wait_for(task, timeout=5)
            assert error.value.detail["code"] == (
                "idempotency_key_reused"
                if scenario == "cross_vehicle_key"
                else "issue_changed"
            )
            await second.rollback()
    async with factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(VehicleIssue)
                .where(VehicleIssue.tenant_id == a["tenant"].id)
            )
            == 1
        )
        assert await db.scalar(
            select(func.count())
            .select_from(VehicleIssueEvent)
            .where(VehicleIssueEvent.tenant_id == a["tenant"].id)
        ) == (1 if scenario in ("same_key", "cross_vehicle_key") else 2)
        assert await db.scalar(
            select(func.count())
            .select_from(VehicleIssueRequest)
            .where(VehicleIssueRequest.tenant_id == a["tenant"].id)
        ) == (1 if scenario in ("same_key", "cross_vehicle_key") else 2)


async def test_database_foreign_keys_and_current_link_uniqueness(pg):
    factory, a = pg
    async with factory() as db:
        created, _ = await create(db, a)
        linked, _ = await service.mutate(
            db,
            a["truck"].id,
            a["owner"],
            wire.IssueLinkCreate(
                request_id=uuid4(), expected_version=1, target_order_id=a["target"].id
            ),
            operation="link",
            issue_id=created.issue.id,
        )
        await db.commit()
        invalid = [
            VehicleIssue(
                tenant_id=a["tenant"].id,
                vehicle_id=a["foreign_truck"].id,
                description="Cross-tenant",
                created_by=a["owner"].id,
            ),
            VehicleIssueEvent(
                tenant_id=a["other"].id,
                issue_id=created.issue.id,
                actor_id=a["owner"].id,
                operation="create",
                version=1,
                changes={},
            ),
            VehicleIssueLink(
                tenant_id=a["tenant"].id,
                vehicle_id=a["twin"].id,
                issue_id=created.issue.id,
                target_order_id=a["target"].id,
                order_number="Fiction",
                created_by=a["owner"].id,
            ),
            VehicleIssueLink(
                tenant_id=a["tenant"].id,
                vehicle_id=a["truck"].id,
                issue_id=created.issue.id,
                target_order_id=a["foreign_order"].id,
                order_number="Fiction",
                created_by=a["owner"].id,
            ),
            VehicleIssueLink(
                tenant_id=a["tenant"].id,
                vehicle_id=a["truck"].id,
                issue_id=created.issue.id,
                target_order_id=a["target"].id,
                order_number="Fiction",
                created_by=a["owner"].id,
            ),
            VehicleIssueRequest(
                tenant_id=a["tenant"].id,
                request_id=uuid4(),
                actor_id=a["owner"].id,
                operation="create",
                payload_hash="a" * 64,
                issue_id=uuid4(),
                accepted_version=1,
            ),
        ]
        for row in invalid:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(row)
                    await db.flush()
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text("DELETE FROM vehicle_issues WHERE id=:id"),
                    {"id": created.issue.id},
                )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(VehicleIssueLink)
                .where(VehicleIssueLink.issue_id == created.issue.id)
            )
            == 1
        )


async def test_all_preexisting_table_rows_retained_by_complete_issue_lifecycle(pg):
    from hashlib import sha256

    factory, a = pg

    async def snapshot(db):
        tables = (
            await db.scalars(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
                )
            )
        ).all()
        hashes = {}
        for table in tables:
            if table.startswith("vehicle_issue"):
                continue
            safe = '"' + table.replace('"', '""') + '"'
            rows = (
                await db.scalars(
                    text(
                        f"SELECT to_jsonb(t)::text FROM {safe} t ORDER BY to_jsonb(t)::text"
                    )
                )
            ).all()
            hashes[table] = (len(rows), sha256("\n".join(rows).encode()).hexdigest())
        return hashes

    async with factory() as db:
        before = await snapshot(db)
        first, _ = await create(db, a)
        identity = first.issue.id
        await service.mutate(
            db,
            a["truck"].id,
            a["owner"],
            wire.IssueEdit(
                request_id=uuid4(),
                expected_version=1,
                description="Staff follow-up detail",
                responsible_user_id=a["owner"].id,
            ),
            operation="edit",
            issue_id=identity,
        )
        linked, _ = await service.mutate(
            db,
            a["truck"].id,
            a["owner"],
            wire.IssueLinkCreate(
                request_id=uuid4(), expected_version=2, target_order_id=a["target"].id
            ),
            operation="link",
            issue_id=identity,
        )
        await service.mutate(
            db,
            a["truck"].id,
            a["owner"],
            wire.IssueStateChange(
                request_id=uuid4(),
                expected_version=3,
                state="resolved",
                reason="Staff assertion",
            ),
            operation="state",
            issue_id=identity,
        )
        await service.mutate(
            db,
            a["truck"].id,
            a["owner"],
            wire.IssueReason(
                request_id=uuid4(), expected_version=4, reason="Retire visit reference"
            ),
            operation="end_link",
            issue_id=identity,
            link_id=linked.issue.current_link.id,
        )
        await db.commit()
        assert await snapshot(db) == before
        assert len(before) >= 180
