from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import customers as customers_endpoint
from app.api.v1.endpoints import vehicles as vehicles_endpoint
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleBase, VehicleCreate, VehicleUpdate


async def _seed_customer(db_session):
    tenant = Tenant(
        id=uuid4(),
        name="Snapshot Garage",
        slug=f"snapshot-garage-{uuid4().hex[:8]}",
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Pat",
        last_name="Owner",
        email=f"pat-{uuid4().hex[:8]}@example.com",
    )
    db_session.add_all([tenant, customer])
    await db_session.commit()
    return tenant, customer


def _staff_user(tenant_id):
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_id=None,
        role=UserRole.GARAGE_ADMIN,
    )


@pytest.mark.asyncio
async def test_create_customer_vehicle_persists_nhtsa_snapshot(db_session, monkeypatch):
    tenant, customer = await _seed_customer(db_session)

    async def _fake_sync(vehicle: Vehicle):
        vehicle.nhtsa_make = "FREIGHTLINER"
        vehicle.nhtsa_model = "CASCADIA"
        vehicle.nhtsa_model_year = 2021
        vehicle.nhtsa_body_class = "Truck-Tractor"
        vehicle.nhtsa_fuel_type = "Diesel"
        vehicle.nhtsa_engine_displacement_l = 14.8
        vehicle.nhtsa_decoded_at = datetime.now(timezone.utc)

    monkeypatch.setattr(customers_endpoint, "sync_vehicle_nhtsa_snapshot", _fake_sync)

    response = await customers_endpoint.create_customer_vehicle(
        customer_id=customer.id,
        vehicle_data=VehicleBase(
            vin="1FUJHHDR8LSLA7890",
            make="Manual Freightliner",
            model="Manual Cascadia",
            year=2021,
        ),
        db=db_session,
        current_user=_staff_user(tenant.id),
    )

    stored = (await db_session.execute(select(Vehicle).where(Vehicle.id == response.id))).scalar_one()
    assert stored.nhtsa_make == "FREIGHTLINER"
    assert stored.nhtsa_model == "CASCADIA"
    assert stored.nhtsa_body_class == "Truck-Tractor"
    assert stored.nhtsa_engine_displacement_l == 14.8
    assert stored.nhtsa_decoded_at is not None


@pytest.mark.asyncio
async def test_update_vehicle_refreshes_nhtsa_snapshot_when_vin_changes(db_session, monkeypatch):
    tenant, customer = await _seed_customer(db_session)
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vin="1FUJHHDR8LSLA1111",
        make="Freightliner",
        model="Cascadia",
        year=2020,
        nhtsa_make="FREIGHTLINER",
        nhtsa_model="CASCADIA",
        nhtsa_model_year=2020,
    )
    db_session.add(vehicle)
    await db_session.commit()

    async def _fake_sync(updated_vehicle: Vehicle):
        updated_vehicle.nhtsa_make = "KENWORTH"
        updated_vehicle.nhtsa_model = "T680"
        updated_vehicle.nhtsa_model_year = 2022
        updated_vehicle.nhtsa_body_class = "Truck-Tractor"
        updated_vehicle.nhtsa_decoded_at = datetime.now(timezone.utc)

    monkeypatch.setattr(vehicles_endpoint, "sync_vehicle_nhtsa_snapshot", _fake_sync)

    response = await vehicles_endpoint.update_vehicle(
        vehicle_id=vehicle.id,
        vehicle_data=VehicleUpdate(
            vin="1XKAD49X35J654321",
            make="Kenworth",
            model="T680",
            year=2022,
        ),
        db=db_session,
        current_user=_staff_user(tenant.id),
    )

    stored = (await db_session.execute(select(Vehicle).where(Vehicle.id == response.id))).scalar_one()
    assert stored.vin == "1XKAD49X35J654321"
    assert stored.nhtsa_make == "KENWORTH"
    assert stored.nhtsa_model == "T680"
    assert stored.nhtsa_model_year == 2022
    assert stored.nhtsa_decoded_at is not None


@pytest.mark.asyncio
async def test_global_vehicle_create_persists_nhtsa_snapshot(db_session, monkeypatch):
    tenant, customer = await _seed_customer(db_session)

    async def _fake_sync(vehicle: Vehicle):
        vehicle.nhtsa_make = "PETERBILT"
        vehicle.nhtsa_model = "579"
        vehicle.nhtsa_model_year = 2019
        vehicle.nhtsa_vehicle_type = "TRUCK"
        vehicle.nhtsa_decoded_at = datetime.now(timezone.utc)

    monkeypatch.setattr(vehicles_endpoint, "sync_vehicle_nhtsa_snapshot", _fake_sync)

    response = await vehicles_endpoint.create_vehicle(
        vehicle_data=VehicleCreate(
            customer_id=customer.id,
            vin="1XPBDP9X8JD123456",
            make="Peterbilt",
            model="579",
            year=2019,
        ),
        db=db_session,
        current_user=_staff_user(tenant.id),
    )

    stored = (await db_session.execute(select(Vehicle).where(Vehicle.id == response.id))).scalar_one()
    assert stored.nhtsa_make == "PETERBILT"
    assert stored.nhtsa_model == "579"
    assert stored.nhtsa_model_year == 2019
