from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from tempfile import SpooledTemporaryFile
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.api.v1.endpoints import mechanics
from app.api.v1.endpoints import repair_orders
from app.db.models.customer import Customer
from app.db.models.labor import Labor, LaborLineType
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


def _upload_file(name: str, content_type: str, data: bytes) -> UploadFile:
    file_obj = SpooledTemporaryFile()
    file_obj.write(data)
    file_obj.seek(0)
    return UploadFile(filename=name, file=file_obj, headers=Headers({"content-type": content_type}))


async def _seed_mechanic_job(db_session, *, status=RepairOrderStatus.ASSIGNED):
    tenant_id = uuid4()
    customer_id = uuid4()
    vehicle_id = uuid4()
    mechanic_id = uuid4()
    order_id = uuid4()
    now = datetime.now(timezone.utc)

    tenant = Tenant(id=tenant_id, name="Mechanic Garage", slug=f"mech-{uuid4().hex[:8]}")
    customer = Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Fleet",
        last_name="Owner",
        email=f"fleet-{uuid4().hex[:8]}@example.com",
    )
    vehicle = Vehicle(
        id=vehicle_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        year=2021,
        make="Freightliner",
        model="Cascadia",
    )
    mechanic = User(
        id=mechanic_id,
        tenant_id=tenant_id,
        email=f"tech-{uuid4().hex[:8]}@example.com",
        first_name="Taylor",
        last_name="Tech",
        role=UserRole.MECHANIC,
        hashed_password="hashed",
        is_active=True,
        is_verified=True,
    )
    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=status,
        assigned_mechanic_id=mechanic_id,
        description="Customer complaint: low air pressure",
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("250.00"),
        total_cost=Decimal("250.00"),
        created_at=now,
        updated_at=now,
    )

    db_session.add_all([tenant, customer, vehicle, mechanic, order])
    await db_session.commit()
    return order, mechanic, customer


@pytest.mark.asyncio
async def test_mechanic_jobs_show_structured_labor_scope(db_session):
    tenant_id = uuid4()
    customer_id = uuid4()
    vehicle_id = uuid4()
    mechanic_id = uuid4()
    order_id = uuid4()
    now = datetime.now(timezone.utc)

    tenant = Tenant(id=tenant_id, name="Scope Garage", slug=f"scope-{uuid4().hex[:8]}")
    customer = Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Fleet",
        last_name="Owner",
        email="fleet@example.com",
    )
    vehicle = Vehicle(
        id=vehicle_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        year=2021,
        make="Freightliner",
        model="Cascadia",
    )
    mechanic = User(
        id=mechanic_id,
        tenant_id=tenant_id,
        email="tech@example.com",
        first_name="Taylor",
        last_name="Tech",
        role=UserRole.MECHANIC,
        hashed_password="hashed",
    )
    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-SCOPE-1",
        status=RepairOrderStatus.ASSIGNED,
        assigned_mechanic_id=mechanic_id,
        description="Customer complaint: low air pressure",
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("250.00"),
        total_cost=Decimal("250.00"),
        created_at=now,
        updated_at=now,
    )
    labor = Labor(
        id=uuid4(),
        tenant_id=tenant_id,
        repair_order_id=order_id,
        description="Diagnose and repair air brake leak",
        hours=Decimal("2.50"),
        hourly_rate=Decimal("100.00"),
        total_cost=Decimal("250.00"),
        line_type=LaborLineType.REPAIR_OPERATION,
    )

    db_session.add_all([tenant, customer, vehicle, mechanic, order, labor])
    await db_session.commit()

    jobs = await mechanics.get_my_jobs(skip=0, limit=100, paginated=False, db=db_session, current_user=mechanic)
    assert len(jobs) == 1
    assert jobs[0].services_count == 1

    detail = await mechanics.get_my_job_detail(order_id=order_id, db=db_session, current_user=mechanic)
    assert [service.name for service in detail.services] == ["Diagnose and repair air brake leak"]


@pytest.mark.asyncio
async def test_work_photo_upload_reports_missing_photo_service(db_session, monkeypatch):
    order, mechanic, _customer = await _seed_mechanic_job(db_session)
    monkeypatch.setattr(mechanics, "is_cloudinary_configured", lambda: False)

    with pytest.raises(HTTPException) as exc:
        await mechanics.upload_job_photo(
            job_id=order.id,
            body=mechanics.WorkPhotoUpload(image="data:image/jpeg;base64,aW1hZ2U=", caption=None),
            db=db_session,
            current_user=mechanic,
        )

    assert exc.value.status_code == 424
    assert "Photo upload service is not configured" in exc.value.detail


@pytest.mark.asyncio
async def test_work_photo_upload_reports_provider_failure(db_session, monkeypatch):
    order, mechanic, _customer = await _seed_mechanic_job(db_session)

    async def fail_upload_work_photo(*, base64_image, repair_order_id, mechanic_id):
        raise RuntimeError("bad cloudinary credentials")

    monkeypatch.setattr(mechanics, "is_cloudinary_configured", lambda: True)
    monkeypatch.setattr(mechanics, "upload_work_photo", fail_upload_work_photo)

    with pytest.raises(HTTPException) as exc:
        await mechanics.upload_job_photo(
            job_id=order.id,
            body=mechanics.WorkPhotoUpload(image="data:image/jpeg;base64,aW1hZ2U=", caption=None),
            db=db_session,
            current_user=mechanic,
        )

    assert exc.value.status_code == 424
    assert "Photo upload service failed" in exc.value.detail


@pytest.mark.asyncio
async def test_repair_order_photo_upload_is_stored(db_session, monkeypatch):
    from sqlalchemy import select
    from app.db.models.work_photo import WorkPhoto

    order, mechanic, _customer = await _seed_mechanic_job(db_session)
    captured = {}

    async def fake_upload_work_photo(*, base64_image, repair_order_id, mechanic_id):
        captured.update(
            {
                "base64_image": base64_image,
                "repair_order_id": repair_order_id,
                "mechanic_id": mechanic_id,
            }
        )
        return "https://res.cloudinary.com/demo/repair.jpg"

    monkeypatch.setattr(repair_orders, "is_cloudinary_configured", lambda: True)
    monkeypatch.setattr(repair_orders, "upload_work_photo", fake_upload_work_photo)

    photo = await repair_orders.upload_repair_order_photo(
        order_id=order.id,
        image=_upload_file("repair.jpg", "image/jpeg", b"repair-bytes"),
        caption="Before repair",
        db=db_session,
        current_user=mechanic,
    )

    assert photo.image_url == "https://res.cloudinary.com/demo/repair.jpg"
    assert photo.caption == "Before repair"
    assert captured["base64_image"].startswith("data:image/jpeg;base64,")
    assert captured["repair_order_id"] == str(order.id)
    assert captured["mechanic_id"] == str(mechanic.id)

    stored = (await db_session.execute(select(WorkPhoto).where(WorkPhoto.repair_order_id == order.id))).scalar_one()
    assert stored.image_url == photo.image_url


@pytest.mark.asyncio
async def test_repair_order_photo_upload_reports_missing_photo_service(db_session, monkeypatch):
    order, mechanic, _customer = await _seed_mechanic_job(db_session)
    monkeypatch.setattr(repair_orders, "is_cloudinary_configured", lambda: False)

    with pytest.raises(HTTPException) as exc:
        await repair_orders.upload_repair_order_photo(
            order_id=order.id,
            image=_upload_file("repair.jpg", "image/jpeg", b"repair-bytes"),
            caption=None,
            db=db_session,
            current_user=mechanic,
        )

    assert exc.value.status_code == 424
    assert "Photo upload service is not configured" in exc.value.detail


@pytest.mark.asyncio
async def test_repair_order_photo_upload_reports_provider_failure(db_session, monkeypatch):
    order, mechanic, _customer = await _seed_mechanic_job(db_session)

    async def fail_upload_work_photo(*, base64_image, repair_order_id, mechanic_id):
        raise RuntimeError("bad cloudinary credentials")

    monkeypatch.setattr(repair_orders, "is_cloudinary_configured", lambda: True)
    monkeypatch.setattr(repair_orders, "upload_work_photo", fail_upload_work_photo)

    with pytest.raises(HTTPException) as exc:
        await repair_orders.upload_repair_order_photo(
            order_id=order.id,
            image=_upload_file("repair.jpg", "image/jpeg", b"repair-bytes"),
            caption=None,
            db=db_session,
            current_user=mechanic,
        )

    assert exc.value.status_code == 424
    assert "Photo upload service failed" in exc.value.detail


@pytest.mark.asyncio
async def test_customer_can_view_active_repair_order_photos(db_session):
    from app.db.models.work_photo import WorkPhoto

    order, mechanic, customer = await _seed_mechanic_job(db_session, status=RepairOrderStatus.IN_PROGRESS)
    customer_user = User(
        id=uuid4(),
        tenant_id=order.tenant_id,
        customer_id=customer.id,
        email=f"customer-{uuid4().hex[:8]}@example.com",
        first_name="Customer",
        last_name="Viewer",
        role=UserRole.CUSTOMER,
        hashed_password="hashed",
        is_active=True,
        is_verified=True,
    )
    photo = WorkPhoto(
        repair_order_id=order.id,
        mechanic_id=mechanic.id,
        image_url="https://cdn.example.com/work.jpg",
        caption="Completed repair",
    )
    db_session.add_all([customer_user, photo])
    await db_session.commit()

    photos = await repair_orders.list_repair_order_photos(
        order_id=order.id,
        db=db_session,
        current_user=customer_user,
    )

    assert len(photos) == 1
    assert photos[0].image_url == "https://cdn.example.com/work.jpg"
    assert photos[0].uploader_name == "Taylor Tech"


@pytest.mark.asyncio
async def test_customer_does_not_view_quoted_repair_order_photos(db_session):
    from app.db.models.work_photo import WorkPhoto

    order, mechanic, customer = await _seed_mechanic_job(db_session, status=RepairOrderStatus.QUOTED)
    customer_user = User(
        id=uuid4(),
        tenant_id=order.tenant_id,
        customer_id=customer.id,
        email=f"customer-{uuid4().hex[:8]}@example.com",
        first_name="Customer",
        last_name="Viewer",
        role=UserRole.CUSTOMER,
        hashed_password="hashed",
        is_active=True,
        is_verified=True,
    )
    photo = WorkPhoto(
        repair_order_id=order.id,
        mechanic_id=mechanic.id,
        image_url="https://cdn.example.com/estimate.jpg",
        caption="Internal estimate photo",
    )
    db_session.add_all([customer_user, photo])
    await db_session.commit()

    photos = await repair_orders.list_repair_order_photos(
        order_id=order.id,
        db=db_session,
        current_user=customer_user,
    )

    assert photos == []
