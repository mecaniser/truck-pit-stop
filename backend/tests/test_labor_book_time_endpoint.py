from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints import labor_book_time
from app.api.v1.endpoints.labor_book_time import LaborBookTimeEntryCreate, LaborBookTimeEntryUpdate
from app.db.models.labor_operation_memory import LaborOperationMemory
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


async def _garage_user(db, role: UserRole = UserRole.GARAGE_OWNER):
    tenant = Tenant(id=uuid4(), name="Book Time Garage", slug=f"btg-{uuid4().hex[:8]}")
    db.add(tenant)
    await db.commit()
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"user-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        first_name="Owner",
        last_name="User",
        role=role,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.commit()
    return tenant, user


async def _memory_row(db, tenant_id, *, name: str = "DPF Cleaning", hours: Decimal = Decimal("3.00")):
    row = LaborOperationMemory(
        tenant_id=tenant_id,
        vehicle_signature="2020-volvo-vnr",
        component_signature="volvo-vnr",
        operation_key=f"custom:{name.lower().replace(' ', '-')}",
        operation_name=name,
        operation_description=f"{name} learned time",
        provider_operation_id=f"custom:{name.lower().replace(' ', '-')}",
        source_provider="internal_memory",
        normalized_hours=hours,
        usage_count=2,
        last_used_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@pytest.mark.asyncio
async def test_list_labor_book_time_entries_is_tenant_scoped(db_session):
    tenant, owner = await _garage_user(db_session)
    other_tenant, _ = await _garage_user(db_session)
    await _memory_row(db_session, tenant.id, name="DPF Cleaning")
    await _memory_row(db_session, other_tenant.id, name="Wheel Seal")

    entries = await labor_book_time.list_labor_book_time_entries(
        q="",
        db=db_session,
        current_user=owner,
    )

    assert [entry.operation_name for entry in entries] == ["DPF Cleaning"]
    assert entries[0].normalized_hours == "3.00"


@pytest.mark.asyncio
async def test_update_labor_book_time_entry_edits_name_description_and_hours(db_session):
    tenant, owner = await _garage_user(db_session)
    row = await _memory_row(db_session, tenant.id, name="DPF Cleaning")

    updated = await labor_book_time.update_labor_book_time_entry(
        entry_id=row.id,
        body=LaborBookTimeEntryUpdate(
            operation_name="DPF Filter Cleaning",
            operation_description="Updated reusable shop book time",
            normalized_hours=Decimal("2.75"),
        ),
        db=db_session,
        current_user=owner,
    )

    assert updated.operation_name == "DPF Filter Cleaning"
    assert updated.operation_description == "Updated reusable shop book time"
    assert updated.normalized_hours == "2.75"

    stored = (await db_session.execute(select(LaborOperationMemory).where(LaborOperationMemory.id == row.id))).scalar_one()
    assert stored.operation_name == "DPF Filter Cleaning"
    assert Decimal(str(stored.normalized_hours)) == Decimal("2.75")


@pytest.mark.asyncio
async def test_create_labor_book_time_entry_stores_structured_truck_scope(db_session):
    _, owner = await _garage_user(db_session)

    created = await labor_book_time.create_labor_book_time_entry(
        body=LaborBookTimeEntryCreate(
            operation_name="Water Pump Replacement",
            operation_description="Book time verified from motor information system",
            normalized_hours=Decimal("8.00"),
            vehicle_year=2020,
            vehicle_make="Freightliner",
            vehicle_model="Cascadia",
            engine="Detroit DD15",
            fuel_type="Diesel",
            engine_displacement_l=14.8,
            gvwr="Class 8",
        ),
        db=db_session,
        current_user=owner,
    )

    assert created.operation_name == "Water Pump Replacement"
    assert created.normalized_hours == "8.00"
    assert created.vehicle_year == 2020
    assert created.vehicle_make == "Freightliner"
    assert created.vehicle_model == "Cascadia"
    assert created.engine == "Detroit DD15"
    assert created.vehicle_signature == "year:2020|make:freightliner|model:cascadia"
    assert created.operation_key == "custom:water-pump-replacement:detroit-dd15-freightliner-cascadia-2020"

    rows = (await db_session.execute(select(LaborOperationMemory))).scalars().all()
    assert len(rows) == 1
    assert rows[0].source_provider == "manual_book_time"


@pytest.mark.asyncio
async def test_create_labor_book_time_entry_rejects_missing_application_scope(db_session):
    _, owner = await _garage_user(db_session)

    with pytest.raises(HTTPException) as exc:
        await labor_book_time.create_labor_book_time_entry(
            body=LaborBookTimeEntryCreate(
                operation_name="Water Pump Replacement",
                normalized_hours=Decimal("8.00"),
                vehicle_make="Freightliner",
            ),
            db=db_session,
            current_user=owner,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_labor_book_time_entry_removes_tenant_row(db_session):
    tenant, owner = await _garage_user(db_session)
    row = await _memory_row(db_session, tenant.id, name="DPF Cleaning")

    await labor_book_time.delete_labor_book_time_entry(
        entry_id=row.id,
        db=db_session,
        current_user=owner,
    )

    stored = (await db_session.execute(select(LaborOperationMemory).where(LaborOperationMemory.id == row.id))).scalar_one_or_none()
    assert stored is None


@pytest.mark.asyncio
async def test_labor_book_time_rejects_non_admin_user(db_session):
    tenant, mechanic = await _garage_user(db_session, role=UserRole.MECHANIC)
    await _memory_row(db_session, tenant.id, name="DPF Cleaning")

    with pytest.raises(HTTPException) as exc:
        await labor_book_time.list_labor_book_time_entries(
            q="",
            db=db_session,
            current_user=mechanic,
        )

    assert exc.value.status_code == 403
