from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.api.v1.endpoints import customers
from app.db.models.invoice import Invoice
from app.db.models.repair_order import RepairOrder
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleBase, VehicleUpdate
from app.services.vehicle_merge import validate_same_physical_vehicle, VehicleMergeError


def test_equipment_type_contract():
    assert VehicleBase(make="Mack", model="Pinnacle").equipment_type == "unknown"
    assert VehicleUpdate(notes="changed").model_dump(exclude_unset=True) == {"notes": "changed"}
    for value in (None, "boat", "", 1):
        with pytest.raises(ValidationError):
            VehicleBase(make="x", model="y", equipment_type=value)
        with pytest.raises(ValidationError):
            VehicleUpdate(equipment_type=value)


@pytest.mark.parametrize("first,second", [("tractor", "trailer"), ("unknown", "trailer"), ("other", "tractor")])
def test_different_types_cannot_merge_on_shared_unit_or_vin(first, second):
    a = Vehicle(equipment_type=first, make="x", model="y", unit_number="3130", vin="1M1AW07Y1FM123456")
    b = Vehicle(equipment_type=second, make="x", model="y", unit_number="3130", vin="1M1AW07Y1FM123456")
    with pytest.raises(VehicleMergeError, match="Equipment types"):
        validate_same_physical_vehicle(a, b)


@pytest.mark.asyncio
async def test_company_mixed_equipment_create_update_and_tenant_denial(db_session, monkeypatch):
    async def no_decode(_vehicle):
        pass
    monkeypatch.setattr(customers, "sync_vehicle_nhtsa_snapshot", no_decode)
    tenant = Tenant(id=uuid4(), name="Equipment shop", slug=uuid4().hex, labor_rate=Decimal("100"))
    foreign = Tenant(id=uuid4(), name="Other shop", slug=uuid4().hex, labor_rate=Decimal("100"))
    company = Customer(id=uuid4(), tenant_id=tenant.id, first_name="Ellis", last_name="Logistics", company_name="Ellis Logistics", email=f"{uuid4()}@example.com")
    owner = User(id=uuid4(), tenant_id=tenant.id, email=f"{uuid4()}@example.com", hashed_password="x", first_name="Shop", last_name="Owner", role=UserRole.GARAGE_OWNER)
    outsider = User(id=uuid4(), tenant_id=foreign.id, email=f"{uuid4()}@example.com", hashed_password="x", first_name="Other", last_name="Owner", role=UserRole.GARAGE_OWNER)
    db_session.add_all([tenant, foreign, company, owner, outsider])
    await db_session.commit()
    created = []
    for kind, unit in [("tractor", "603"), ("tractor", "609"), ("trailer", "T1003130"), ("trailer", "T1003142"), ("other", "generator")]:
        item = await customers.create_customer_vehicle(company.id, VehicleBase(make="Test", model="Equipment", equipment_type=kind, unit_number=unit), db_session, owner)
        assert item.equipment_type == kind
        assert item.customer_id == company.id
        created.append(item)
    assert len({item.id for item in created}) == 5
    # Each equipment record keeps a separate job and invoice, even when bill-to
    # is the same company and unit numbers could be similar.
    invoices = []
    for item in created[:4]:
        order = RepairOrder(tenant_id=tenant.id, customer_id=company.id, vehicle_id=item.id, order_number=f"RO-{uuid4()}")
        db_session.add(order)
        await db_session.flush()
        invoice = Invoice(tenant_id=tenant.id, repair_order_id=order.id, billed_customer_id=company.id, invoice_number=f"INV-{uuid4()}", subtotal=Decimal("100"), total_amount=Decimal("100"))
        db_session.add(invoice)
        invoices.append((invoice, item.id))
    await db_session.commit()
    for invoice, asset_id in invoices:
        linked = (await db_session.execute(select(RepairOrder.vehicle_id).join(Invoice, Invoice.repair_order_id == RepairOrder.id).where(Invoice.id == invoice.id))).scalar_one()
        assert linked == asset_id
    trailer = created[2]
    updated = await customers.update_customer_vehicle(company.id, trailer.id, VehicleUpdate(notes="Six Aufine tires"), db_session, owner)
    assert updated.equipment_type == "trailer"
    assert updated.unit_number == "T1003130"
    changed = await customers.update_customer_vehicle(company.id, trailer.id, VehicleUpdate(equipment_type="other"), db_session, owner)
    assert changed.equipment_type == "other"
    for action in (
        customers.create_customer_vehicle(company.id, VehicleBase(make="x", model="y", equipment_type="trailer"), db_session, outsider),
        customers.update_customer_vehicle(company.id, trailer.id, VehicleUpdate(equipment_type="tractor"), db_session, outsider),
    ):
        with pytest.raises(HTTPException) as exc:
            await action
        assert exc.value.status_code in (403, 404)
    persisted = (await db_session.execute(select(Vehicle).where(Vehicle.id == trailer.id))).scalar_one()
    assert persisted.equipment_type == "other"
