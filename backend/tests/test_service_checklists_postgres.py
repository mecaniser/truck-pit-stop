"""Opt-in real PostgreSQL row-lock proof; never drops or rebuilds shared tables.

Set DB102_POSTGRES_TEST_URL to an isolated DB whose name contains db102_test.
Migration 165 must already be applied. Only freshly generated fixture tenants
are deleted at teardown. These tests never call payment or messaging providers.
"""

import asyncio
import os

import pytest
import pytest_asyncio
from app.db.base import Base
from app.db.models.labor import Labor
from app.db.models.repair_order import RepairOrderStatus
from app.db.models.service_checklist import RepairOrderChecklistItem
from app.db.models.tenant import Tenant
from app.schemas.service_checklist import ChecklistTaskUpdate, ChecklistTemplateUpdate
from app.services import service_checklist as checks
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_service_checklists import apply, seed

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def pg_case():
    url = os.environ.get("DB102_POSTGRES_TEST_URL")
    if not url:
        pytest.skip("DB102 isolated PostgreSQL test URL not configured")
    parsed = make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"} or "db102_test" not in (
        parsed.database or ""
    ):
        raise RuntimeError(
            "Only an explicitly isolated local DB102 test database is permitted"
        )
    engine = create_async_engine(
        url, connect_args={"server_settings": {"lock_timeout": "3000"}}
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        data = await seed(db)
        page = await apply(db, data)
        tenant_id = data.tenant.id
    try:
        yield factory, data, page
    finally:
        # All rows are synthetic and match this test's unpredictable tenant ID.
        async with factory() as db:
            for table in reversed(Base.metadata.sorted_tables):
                if "tenant_id" in table.c:
                    await db.execute(
                        delete(table).where(table.c.tenant_id == tenant_id)
                    )
            await db.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await db.commit()
        await engine.dispose()


async def expect_blocked(task):
    await asyncio.sleep(0.12)
    assert not task.done(), (
        "The competing transaction did not wait for the RO/template lock"
    )


async def finish(db, data):
    order = await checks.load_order(db, data.order.id, data.owner, for_update=True)
    await checks.guard_completion(db, order)
    order.status = RepairOrderStatus.COMPLETED
    await db.commit()


async def mark_required_complete(db, data, page):
    for item in page.items:
        if item.required:
            await checks.update_task(
                db,
                data.order.id,
                item.id,
                data.owner,
                ChecklistTaskUpdate(is_completed=True, expected_version=1),
            )
    await db.commit()


async def test_uncheck_wins_completion_race(pg_case):
    factory, data, page = pg_case
    async with factory() as first, factory() as second:
        await mark_required_complete(first, data, page)
        await checks.update_task(
            first,
            data.order.id,
            page.items[0].id,
            data.owner,
            ChecklistTaskUpdate(is_completed=False, expected_version=2),
        )
        contender = asyncio.create_task(finish(second, data))
        await expect_blocked(contender)
        await first.commit()
        with pytest.raises(HTTPException) as exc:
            await contender
        assert exc.value.status_code == 409 and "1 required" in exc.value.detail
        await second.rollback()


async def test_completion_wins_uncheck_race(pg_case):
    factory, data, page = pg_case
    async with factory() as first, factory() as second:
        await mark_required_complete(first, data, page)
        order = await checks.load_order(
            first, data.order.id, data.owner, for_update=True
        )
        await checks.guard_completion(first, order)
        order.status = RepairOrderStatus.COMPLETED
        contender = asyncio.create_task(
            checks.update_task(
                second,
                data.order.id,
                page.items[0].id,
                data.owner,
                ChecklistTaskUpdate(is_completed=False, expected_version=2),
            )
        )
        await expect_blocked(contender)
        await first.commit()
        with pytest.raises(HTTPException) as exc:
            await contender
        assert exc.value.status_code == 409 and "open work order" in exc.value.detail
        await second.rollback()


async def test_template_stale_save_serializes(pg_case):
    factory, data, _ = pg_case
    async with factory() as first, factory() as second:
        await checks.save_template(
            first,
            data.service.id,
            data.owner,
            ChecklistTemplateUpdate(
                expected_version=1, items=[{"label": "First revision"}]
            ),
        )
        contender = asyncio.create_task(
            checks.save_template(
                second,
                data.service.id,
                data.owner,
                ChecklistTemplateUpdate(
                    expected_version=1, items=[{"label": "Stale revision"}]
                ),
            )
        )
        await expect_blocked(contender)
        await first.commit()
        with pytest.raises(HTTPException) as exc:
            await contender
        assert exc.value.status_code == 409
        await second.rollback()
        saved = await checks.load_template(second, data.service.id, data.owner)
        assert (
            saved.checklist_template[0]["label"] == "First revision"
            and saved.checklist_version == 2
        )


async def test_line_delete_wins_check_race(pg_case):
    factory, data, page = pg_case
    async with factory() as first, factory() as second:
        order = await checks.load_order(
            first, data.order.id, data.owner, for_update=True
        )
        line = await first.get(Labor, page.items[0].labor_id)
        await checks.archive_labor(first, order, line, data.owner)
        await first.delete(line)
        contender = asyncio.create_task(
            checks.update_task(
                second,
                data.order.id,
                page.items[0].id,
                data.owner,
                ChecklistTaskUpdate(is_completed=True, expected_version=1),
            )
        )
        await expect_blocked(contender)
        await first.commit()
        with pytest.raises(HTTPException) as exc:
            await contender
        assert exc.value.status_code == 404
        await second.rollback()
        task = await second.get(RepairOrderChecklistItem, page.items[0].id)
        assert (
            task.labor_id is None
            and task.removed_at is not None
            and not task.is_completed
        )
