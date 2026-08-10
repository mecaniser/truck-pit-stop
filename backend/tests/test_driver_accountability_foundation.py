from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.workos_auth import CurrentPrincipal
from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.driver_accountability import (
    DriverProfile,
    EquipmentCustodyAsset,
    FleetIncidentEvent,
    FleetTrailer,
)
from app.db.models.fleet import (
    FleetIncident,
    FleetInspectionItem,
    IncidentSeverity,
    IncidentStatus,
    InspectionItemResult,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.driver_accountability_service import (
    acknowledge_own_custody,
    close_custody_session,
    create_driver_profile,
    get_driver_for_principal,
    release_vehicle_custody,
    replace_vehicle_custody,
    start_custody_session,
)
from app.api.v1.endpoints.fleet import (
    DirectFleetIncidentPhotoCreate,
    create_incident,
    create_incident_photo_from_direct_upload,
    delete_incident,
    delete_incident_photo,
    list_incident_events,
    update_incident,
)
from app.schemas.fleet import IncidentCreate, IncidentUpdate


async def _seed_fleet(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(
        name="Driver Test Garage",
        slug=f"driver-test-{suffix}",
        workos_organization_id=f"org_driver_test_{suffix}",
    )
    other_tenant = Tenant(name="Other Garage", slug=f"other-driver-test-{suffix}")
    db_session.add_all([tenant, other_tenant])
    await db_session.flush()

    employer = Customer(
        tenant_id=tenant.id,
        first_name="Elis",
        last_name="Logistics",
        company_name="ELIS LOGISTICS LLC",
        email=f"elis-{suffix}@example.test",
        is_internal_fleet=True,
    )
    other_employer = Customer(
        tenant_id=other_tenant.id,
        first_name="Other",
        last_name="Carrier",
        company_name="OTHER CARRIER LLC",
        email=f"other-{suffix}@example.test",
    )
    manager = User(
        tenant_id=tenant.id,
        email=f"manager-{suffix}@example.test",
        hashed_password="x",
        first_name="Fleet",
        last_name="Manager",
        role=UserRole.FLEET_MANAGER,
        is_active=True,
        workos_user_id=f"workos_manager_{suffix}",
    )
    driver_user = User(
        tenant_id=tenant.id,
        email=f"driver-{suffix}@example.test",
        hashed_password="workos-only",
        first_name="Dana",
        last_name="Driver",
        role=UserRole.DRIVER,
        is_active=True,
        workos_user_id=f"workos_driver_{suffix}",
    )
    db_session.add_all([employer, other_employer, manager, driver_user])
    await db_session.flush()

    truck = Vehicle(
        tenant_id=tenant.id,
        customer_id=employer.id,
        make="Volvo",
        model="VNR",
        vin="4V4WC9EG2LN250024",
        unit_number="609",
        mileage=625900,
    )
    trailer = FleetTrailer(
        tenant_id=tenant.id,
        owner_customer_id=employer.id,
        unit_number="T-609",
        body_type="Dry van",
    )
    db_session.add_all([truck, trailer])
    await db_session.flush()
    return tenant, other_tenant, employer, other_employer, manager, driver_user, truck, trailer


@pytest.mark.asyncio
async def test_driver_profile_is_durable_and_login_link_is_optional(db_session):
    tenant, _, employer, _, _, driver_user, _, _ = await _seed_fleet(db_session)

    imported_driver = await create_driver_profile(
        db_session,
        tenant_id=tenant.id,
        first_name="Legacy",
        last_name="Driver",
        employer_customer_id=employer.id,
    )
    linked_driver = await create_driver_profile(
        db_session,
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Driver",
        employer_customer_id=employer.id,
        user_id=driver_user.id,
    )

    assert imported_driver.user_id is None
    assert linked_driver.user_id == driver_user.id
    assert linked_driver.employer_customer_id == employer.id

    # Removing login access does not delete or rewrite the domain profile.
    driver_user.is_active = False
    await db_session.flush()
    persisted = await db_session.get(DriverProfile, linked_driver.id)
    assert persisted is not None
    assert persisted.first_name == "Dana"


@pytest.mark.asyncio
async def test_driver_profile_rejects_cross_tenant_employer(db_session):
    tenant, _, _, other_employer, _, _, _, _ = await _seed_fleet(db_session)

    with pytest.raises(HTTPException) as exc:
        await create_driver_profile(
            db_session,
            tenant_id=tenant.id,
            first_name="Cross",
            last_name="Tenant",
            employer_customer_id=other_employer.id,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_custody_links_truck_and_trailer_and_blocks_double_assignment(db_session):
    tenant, _, employer, _, manager, driver_user, truck, trailer = await _seed_fleet(db_session)
    driver = await create_driver_profile(
        db_session,
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Driver",
        employer_customer_id=employer.id,
        user_id=driver_user.id,
    )

    session = await start_custody_session(
        db_session,
        tenant_id=tenant.id,
        driver_id=driver.id,
        assigned_by_user_id=manager.id,
        vehicle_id=truck.id,
        trailer_ids=[trailer.id],
        start_odometer=truck.mileage,
        dispatch_reference="LOAD-1001",
    )
    assert session.status == "assigned"
    assert {asset.equipment_role for asset in session.assets} == {"power_unit", "trailer"}

    with pytest.raises(HTTPException) as exc:
        await start_custody_session(
            db_session,
            tenant_id=tenant.id,
            driver_id=driver.id,
            assigned_by_user_id=manager.id,
            vehicle_id=truck.id,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_driver_can_acknowledge_only_own_custody_and_close_releases_assets(db_session):
    tenant, _, employer, _, manager, driver_user, truck, trailer = await _seed_fleet(db_session)
    driver = await create_driver_profile(
        db_session,
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Driver",
        employer_customer_id=employer.id,
        user_id=driver_user.id,
    )
    session = await start_custody_session(
        db_session,
        tenant_id=tenant.id,
        driver_id=driver.id,
        assigned_by_user_id=manager.id,
        vehicle_id=truck.id,
        trailer_ids=[trailer.id],
        start_odometer=truck.mileage,
    )
    principal = CurrentPrincipal(
        local_user_id=driver_user.id,
        workos_user_id=driver_user.workos_user_id,
        workos_org_id="org_driver_test",
        tenant_id=tenant.id,
        permissions=frozenset({"driver_portal:use", "inspections:perform"}),
    )

    resolved_driver = await get_driver_for_principal(db_session, principal)
    assert resolved_driver.id == driver.id
    acknowledged = await acknowledge_own_custody(
        db_session,
        principal=principal,
        custody_session_id=session.id,
    )
    assert acknowledged.status == "active"
    assert acknowledged.acknowledged_at is not None

    closed = await close_custody_session(
        db_session,
        tenant_id=tenant.id,
        custody_session_id=session.id,
        released_by_user_id=manager.id,
        end_odometer=626150,
        ended_at=datetime.now(timezone.utc),
    )
    assert closed.status == "closed"
    assets = list(
        (
            await db_session.execute(
                select(EquipmentCustodyAsset).where(
                    EquipmentCustodyAsset.custody_session_id == session.id
                )
            )
        ).scalars()
    )
    assert all(asset.released_at is not None for asset in assets)
    truck_asset = next(asset for asset in assets if asset.vehicle_id == truck.id)
    trailer_asset = next(asset for asset in assets if asset.trailer_id == trailer.id)
    assert truck_asset.end_odometer == 626150
    assert trailer_asset.end_odometer is None


@pytest.mark.asyncio
async def test_replacing_vehicle_driver_preserves_prior_custody_and_updates_board_projection(db_session):
    tenant, _, employer, _, manager, driver_user, truck, trailer = await _seed_fleet(db_session)
    first = await create_driver_profile(
        db_session, tenant_id=tenant.id, first_name="Dana", last_name="Driver",
        employer_customer_id=employer.id, user_id=driver_user.id,
    )
    second = await create_driver_profile(
        db_session, tenant_id=tenant.id, first_name="Morgan", last_name="Miles",
        employer_customer_id=employer.id, phone="7045551212",
    )
    prior = await start_custody_session(
        db_session, tenant_id=tenant.id, driver_id=first.id,
        assigned_by_user_id=manager.id, vehicle_id=truck.id,
        trailer_ids=[trailer.id], start_odometer=truck.mileage,
    )

    replacement = await replace_vehicle_custody(
        db_session, tenant_id=tenant.id, driver_id=second.id,
        assigned_by_user_id=manager.id, vehicle_id=truck.id,
        start_odometer=truck.mileage,
    )
    await db_session.flush()

    assert prior.status == "closed"
    assert prior.ends_at is not None
    assert all(asset.released_at is not None for asset in prior.assets)
    assert replacement.driver_id == second.id
    assert truck.driver_name == "Morgan Miles"
    assert truck.driver_phone == "7045551212"

    await release_vehicle_custody(
        db_session, tenant_id=tenant.id, vehicle_id=truck.id,
        released_by_user_id=manager.id,
    )
    assert replacement.status == "closed"
    assert truck.driver_name is None
    assert truck.driver_phone is None


def _workos_token(user: User, tenant: Tenant, permissions: set[str]) -> str:
    return create_access_token(
        data={
            "sub": str(user.id),
            "auth_provider": "workos",
            "workos_user_id": user.workos_user_id,
            "workos_org_id": tenant.workos_organization_id,
            "permissions": sorted(permissions),
        },
        tenant_id=str(tenant.id),
        expires_delta=timedelta(minutes=5),
    )


@pytest.mark.asyncio
async def test_workos_permissions_and_self_scope_protect_driver_routes(client, db_session):
    tenant, _, employer, _, manager, driver_user, _, _ = await _seed_fleet(db_session)
    driver = await create_driver_profile(
        db_session,
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Driver",
        employer_customer_id=employer.id,
        user_id=driver_user.id,
    )
    await db_session.commit()

    manager_without_assignment = _workos_token(manager, tenant, {"fleet:view"})
    denied = await client.post(
        "/api/v1/fleet-identity/drivers",
        json={"first_name": "New", "last_name": "Driver"},
        headers={"Authorization": f"Bearer {manager_without_assignment}"},
    )
    assert denied.status_code == 403

    manager_with_assignment = _workos_token(manager, tenant, {"fleet:view", "fleet:assign"})
    created = await client.post(
        "/api/v1/fleet-identity/drivers",
        json={"first_name": "New", "last_name": "Driver"},
        headers={"Authorization": f"Bearer {manager_with_assignment}"},
    )
    assert created.status_code == 201
    assert created.json()["tenant_id"] == str(tenant.id)

    driver_token = _workos_token(driver_user, tenant, {"driver_portal:use"})
    me = await client.get(
        "/api/v1/fleet-identity/me",
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert me.status_code == 200
    assert me.json()["id"] == str(driver.id)

    # Fleet-view permission alone does not grant access to the self portal.
    wrong_permission = _workos_token(driver_user, tenant, {"fleet:view"})
    denied_self = await client.get(
        "/api/v1/fleet-identity/me",
        headers={"Authorization": f"Bearer {wrong_permission}"},
    )
    assert denied_self.status_code == 403


@pytest.mark.asyncio
async def test_manager_assigns_and_releases_driver_profile_through_vehicle_contract(client, db_session):
    tenant, _, employer, _, manager, _, truck, _ = await _seed_fleet(db_session)
    driver = await create_driver_profile(
        db_session, tenant_id=tenant.id, first_name="Morgan", last_name="Miles",
        employer_customer_id=employer.id, phone="7045551212",
    )
    await db_session.commit()
    token = _workos_token(manager, tenant, {"fleet:view", "fleet:assign"})
    headers = {"Authorization": f"Bearer {token}"}

    assigned = await client.put(
        f"/api/v1/fleet-identity/vehicles/{truck.id}/driver",
        json={"driver_id": str(driver.id), "vehicle_id": str(truck.id), "start_odometer": truck.mileage},
        headers=headers,
    )
    assert assigned.status_code == 200
    assert assigned.json()["driver"]["id"] == str(driver.id)
    assert assigned.json()["custody_status"] == "assigned"

    current = await client.get(
        f"/api/v1/fleet-identity/vehicles/{truck.id}/driver", headers=headers,
    )
    assert current.status_code == 200
    assert current.json()["driver"]["first_name"] == "Morgan"

    released = await client.delete(
        f"/api/v1/fleet-identity/vehicles/{truck.id}/driver", headers=headers,
    )
    assert released.status_code == 204
    after_release = await client.get(
        f"/api/v1/fleet-identity/vehicles/{truck.id}/driver", headers=headers,
    )
    assert after_release.status_code == 200
    assert after_release.json() is None


@pytest.mark.asyncio
async def test_manager_can_find_unconverted_legacy_driver_contacts(client, db_session):
    tenant, _, _, _, manager, _, truck, _ = await _seed_fleet(db_session)
    truck.driver_name = "Marcus Jones"
    truck.driver_phone = "(910) 301-3928"
    await db_session.commit()
    token = _workos_token(manager, tenant, {"fleet:view"})

    response = await client.get(
        "/api/v1/fleet-identity/drivers/legacy-contacts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == [{
        "name": "Marcus Jones",
        "phone": "(910) 301-3928",
        "vehicle_count": 1,
    }]


@pytest.mark.asyncio
async def test_manager_cannot_move_driver_profile_to_another_tenant_customer(client, db_session):
    tenant, _, employer, other_employer, manager, _, _, _ = await _seed_fleet(db_session)
    driver = await create_driver_profile(
        db_session,
        tenant_id=tenant.id,
        first_name="Morgan",
        last_name="Miles",
        employer_customer_id=employer.id,
    )
    await db_session.commit()
    token = _workos_token(manager, tenant, {"fleet:assign"})
    headers = {"Authorization": f"Bearer {token}"}

    cross_tenant = await client.patch(
        f"/api/v1/fleet-identity/drivers/{driver.id}",
        json={"employer_customer_id": str(other_employer.id)},
        headers=headers,
    )
    assert cross_tenant.status_code == 404

    missing_name = await client.patch(
        f"/api/v1/fleet-identity/drivers/{driver.id}",
        json={"first_name": None},
        headers=headers,
    )
    assert missing_name.status_code == 422


@pytest.mark.asyncio
async def test_driver_portal_pti_and_incident_are_bound_to_active_custody(client, db_session):
    tenant, _, employer, _, manager, driver_user, truck, trailer = await _seed_fleet(db_session)
    driver = await create_driver_profile(
        db_session,
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Driver",
        employer_customer_id=employer.id,
        user_id=driver_user.id,
    )
    custody = await start_custody_session(
        db_session,
        tenant_id=tenant.id,
        driver_id=driver.id,
        assigned_by_user_id=manager.id,
        vehicle_id=truck.id,
        trailer_ids=[trailer.id],
        start_odometer=truck.mileage,
    )
    await db_session.commit()
    token = _workos_token(
        driver_user,
        tenant,
        {"driver_portal:use", "inspections:perform", "incidents:report"},
    )
    headers = {"Authorization": f"Bearer {token}"}

    equipment = await client.get("/api/v1/fleet-identity/me/equipment", headers=headers)
    assert equipment.status_code == 200
    assert {item["equipment_role"] for item in equipment.json()} == {"power_unit", "trailer"}

    unconfirmed = await client.post(
        "/api/v1/fleet-identity/me/inspections",
        json={"vehicle_id": str(truck.id)},
        headers=headers,
    )
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["detail"] == "Confirm custody before using this equipment"

    acknowledged = await client.post(
        f"/api/v1/fleet-identity/me/custody/{custody.id}/acknowledge",
        headers=headers,
    )
    assert acknowledged.status_code == 200

    started = await client.post(
        "/api/v1/fleet-identity/me/inspections",
        json={"vehicle_id": str(truck.id)},
        headers=headers,
    )
    assert started.status_code == 201
    inspection_id = started.json()["id"]
    assert len(started.json()["items"]) == 19
    first_item_id = started.json()["items"][0]["id"]

    await db_session.execute(
        update(FleetInspectionItem)
        .where(FleetInspectionItem.inspection_id == inspection_id)
        .values(result=InspectionItemResult.PASS)
    )
    await db_session.execute(
        update(FleetInspectionItem)
        .where(FleetInspectionItem.id == first_item_id)
        .values(result=InspectionItemResult.FAIL, note=None)
    )
    await db_session.commit()
    missing_failure_note = await client.post(
        f"/api/v1/fleet-identity/me/inspections/{inspection_id}/complete",
        json={"odometer": 626001},
        headers=headers,
    )
    assert missing_failure_note.status_code == 400
    assert missing_failure_note.json()["detail"] == "Describe each failed check before submitting"

    await db_session.execute(
        update(FleetInspectionItem)
        .where(FleetInspectionItem.id == first_item_id)
        .values(result=InspectionItemResult.PASS)
    )
    await db_session.commit()
    completed = await client.post(
        f"/api/v1/fleet-identity/me/inspections/{inspection_id}/complete",
        json={"odometer": 626001},
        headers=headers,
    )
    assert completed.status_code == 200
    assert completed.json()["result"] == "pass"
    assert completed.json()["inspector_id"] == str(driver_user.id)

    reported = await client.post(
        "/api/v1/fleet-identity/me/incidents",
        json={
            "vehicle_id": str(truck.id),
            "trailer_id": str(trailer.id),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "incident_type": "mechanical",
            "severity": "medium",
            "location": "I-85 mile 42",
            "description": "Air line began leaking while under load.",
        },
        headers=headers,
    )
    assert reported.status_code == 201
    incident = await db_session.get(FleetIncident, reported.json()["id"])
    assert incident.driver_id_at_occurrence == driver.id
    assert incident.custody_session_id == custody.id
    assert incident.reported_by_id == driver_user.id
    event = (
        await db_session.execute(
            select(FleetIncidentEvent).where(FleetIncidentEvent.incident_id == incident.id)
        )
    ).scalar_one()
    assert event.data_json["source"] == "driver_portal"

    scorecard = await client.get("/api/v1/fleet-identity/me/scorecard", headers=headers)
    assert scorecard.status_code == 200
    assert scorecard.json()["incidents_during_custody"] == 1
    assert scorecard.json()["confirmed_driver_duty_issues"] == 0
    assert scorecard.json()["disputed_or_pending_reviews"] == 1
    assert scorecard.json()["scoring_ready"] is False


@pytest.mark.asyncio
async def test_incident_actions_append_history_and_void_instead_of_erasing(db_session):
    tenant, _, _, _, manager, _, truck, _ = await _seed_fleet(db_session)
    occurred_at = datetime.now(timezone.utc)
    created = await create_incident(
        IncidentCreate(
            vehicle_id=truck.id,
            occurred_at=occurred_at,
            severity=IncidentSeverity.MEDIUM,
            description="Road debris damaged the trailer connection.",
        ),
        db_session,
        manager,
    )
    incident_id = created.id

    await update_incident(
        incident_id,
        IncidentUpdate(
            status=IncidentStatus.RESOLVED,
            resolution_notes="Connection inspected and secured.",
        ),
        db_session,
        manager,
    )
    photo = await create_incident_photo_from_direct_upload(
        incident_id,
        DirectFleetIncidentPhotoCreate(
            image_url="https://res.cloudinary.com/demo/image/upload/evidence.jpg",
            public_id=f"work_photos/fleet_incidents/{incident_id}/evidence",
            caption="Connection after inspection",
        ),
        db_session,
        manager,
    )
    await delete_incident_photo(incident_id, photo.id, db_session, manager)
    await delete_incident(incident_id, db_session, manager)

    incident = await db_session.get(FleetIncident, incident_id)
    assert incident is not None
    assert incident.status == IncidentStatus.VOIDED

    event_rows = list(
        (
            await db_session.execute(
                select(FleetIncidentEvent)
                .where(FleetIncidentEvent.incident_id == incident_id)
                .order_by(FleetIncidentEvent.occurred_at)
            )
        ).scalars()
    )
    assert [event.event_type for event in event_rows] == [
        "reported",
        "operationally_resolved",
        "evidence_added",
        "evidence_voided",
        "voided",
    ]

    timeline = await list_incident_events(incident_id, db_session, manager)
    assert {entry.event_type for entry in timeline} == {
        "reported",
        "operationally_resolved",
        "evidence_added",
        "evidence_voided",
        "voided",
    }
