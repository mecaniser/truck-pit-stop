from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import Response

from app.api.v1.endpoints import customers, fleet_invoice_exports as exports
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.customer import CustomerMergeRequest


async def _seed(db, slug, *, other_customer=False):
    tenant = Tenant(name=slug, slug=slug)
    owner = User(tenant=tenant, email=f"{slug}@example.com", hashed_password="x",
                 first_name="Owner", last_name="Test", role=UserRole.GARAGE_OWNER,
                 is_active=True, is_verified=True)
    customer = Customer(tenant=tenant, first_name="ELIS", last_name="Fleet",
                        email=f"fleet-{slug}@example.com")
    another = Customer(tenant=tenant, first_name="Other", last_name="Company",
                       email=f"other-{slug}@example.com")
    vehicle = Vehicle(tenant=tenant, customer=customer, vin="1HGBH41JXMN109186",
                      unit_number="Truck 1", make="Freightliner", model="Cascadia")
    order = RepairOrder(tenant=tenant, customer=another if other_customer else customer,
                        vehicle=vehicle, order_number=f"RO-{uuid4().hex}")
    db.add_all([tenant, owner, customer, another, vehicle, order])
    await db.flush()
    invoice = Invoice(tenant=tenant, repair_order=order,
                      billed_customer_id=another.id if other_customer else customer.id,
                      invoice_number=f"INV-{uuid4().hex}",
                      status=InvoiceStatus.SENT, subtotal=Decimal("100.00"),
                      tax_amount=Decimal("0.00"), discount_amount=Decimal("0.00"),
                      total_amount=Decimal("100.00"),
                      line_items_snapshot={"labor": [{"description": "Oil change", "total_cost": "100.00"}], "parts": []})
    db.add(invoice)
    await db.commit()
    return owner, customer, invoice, vehicle


@pytest.mark.asyncio
async def test_bill_to_scope_excludes_other_customer_even_on_same_vehicle(client, db_session):
    owner, customer, included, vehicle = await _seed(db_session, f"elis-{uuid4().hex}")
    _owner, _customer, excluded, _vehicle = await _seed(db_session, f"different-shop-{uuid4().hex}")
    # A second invoice uses the same shop and truck but a different historical bill-to.
    another = Customer(tenant_id=owner.tenant_id, first_name="Other", last_name="Bill-To",
                       email=f"different-bill-to-{uuid4().hex}@example.com")
    order = RepairOrder(tenant_id=owner.tenant_id, customer=another, vehicle=vehicle,
                        order_number=f"RO-{uuid4().hex}")
    db_session.add_all([another, order]); await db_session.flush()
    wrong_bill_to = Invoice(tenant_id=owner.tenant_id, repair_order=order,
                            billed_customer_id=another.id,
                            invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.SENT,
                            subtotal=Decimal("30"), tax_amount=Decimal("0"),
                            discount_amount=Decimal("0"), total_amount=Decimal("30"))
    db_session.add(wrong_bill_to); await db_session.commit()

    created = await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="ELIS"), Response(),
                                       db=db_session, user=owner)
    before = datetime.now(timezone.utc)
    response = await client.get("/api/v1/fleet-invoice-exports/invoices",
                                headers={"X-API-Key": created["api_key"]},
                                params={"updated_since": (before - timedelta(days=1)).isoformat(),
                                        "updated_before": before.isoformat()})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["invoice_id"] for item in items] == [str(included.id)]
    assert items[0]["total_amount"] == "100.00"
    assert "customer" not in items[0]
    assert "no-store" in response.headers["cache-control"]

    for hidden in (wrong_bill_to, excluded):
        pdf = await client.get(f"/api/v1/fleet-invoice-exports/invoices/{hidden.id}/pdf",
                               headers={"X-API-Key": created["api_key"]})
        assert pdf.status_code == 404


@pytest.mark.asyncio
async def test_revocation_and_wrong_tenant_customer_provisioning(client, db_session):
    owner, customer, _invoice, _vehicle = await _seed(db_session, f"owner-{uuid4().hex}")
    _other_owner, other_customer, _, _vehicle2 = await _seed(db_session, f"other-{uuid4().hex}")
    with pytest.raises(Exception) as error:
        await exports.create_key(exports.KeyRequest(customer_id=other_customer.id, name="Bad"), Response(),
                                 db=db_session, user=owner)
    assert error.value.status_code == 404
    created = await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="ELIS"), Response(),
                                       db=db_session, user=owner)
    listed = await exports.list_keys(Response(), db=db_session, user=owner)
    assert len(listed) == 1 and "api_key" not in listed[0]
    await exports.revoke_key(created["id"], db=db_session, user=owner)
    now = datetime.now(timezone.utc)
    response = await client.get("/api/v1/fleet-invoice-exports/invoices",
                                headers={"X-API-Key": created["api_key"]},
                                params={"updated_since": (now - timedelta(days=1)).isoformat(),
                                        "updated_before": now.isoformat()})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cursor_pages_and_bill_to_snapshot_survives_order_reassignment(client, db_session):
    owner, customer, first, vehicle = await _seed(db_session, f"pages-{uuid4().hex}")
    order = RepairOrder(tenant_id=owner.tenant_id, customer_id=customer.id,
                        vehicle_id=vehicle.id, order_number=f"RO-{uuid4().hex}")
    second = Invoice(tenant_id=owner.tenant_id, repair_order=order,
                     billed_customer_id=customer.id, invoice_number=f"INV-{uuid4().hex}",
                     status=InvoiceStatus.CANCELLED, subtotal=Decimal("20"),
                     tax_amount=Decimal("0"), discount_amount=Decimal("0"),
                     total_amount=Decimal("20"))
    db_session.add_all([order, second]); await db_session.commit()
    # SQLite's CURRENT_TIMESTAMP has second precision; persist a fractional
    # timestamp so its text comparison matches PostgreSQL's timestamp semantics.
    shared_stamp = datetime.now(timezone.utc) - timedelta(seconds=10)
    first.updated_at = shared_stamp
    second.updated_at = shared_stamp
    (await db_session.get(RepairOrder, first.repair_order_id)).updated_at = shared_stamp
    order.updated_at = shared_stamp
    vehicle.updated_at = shared_stamp
    await db_session.commit()
    created = await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="ELIS"), Response(),
                                       db=db_session, user=owner)
    now = datetime.now(timezone.utc)
    params = {"updated_since": (now - timedelta(days=1)).isoformat(),
              "updated_before": now.isoformat(), "limit": 1}
    url = "/api/v1/fleet-invoice-exports/invoices"
    headers = {"X-API-Key": created["api_key"]}
    one = await client.get(url, headers=headers, params=params)
    assert one.status_code == 200, one.text
    cursor = one.json()["next_cursor"]
    assert cursor
    two = await client.get(url, headers=headers, params={**params, "cursor": cursor})
    assert two.status_code == 200, two.text
    items = one.json()["items"] + two.json()["items"]
    assert {item["invoice_id"] for item in items} == {str(first.id), str(second.id)}
    assert {item["status"] for item in items} == {"sent", "cancelled"}
    assert two.json()["next_cursor"] is None

    # The invoice remains scoped to its original bill-to after an RO correction.
    new_customer = Customer(tenant_id=owner.tenant_id, first_name="New", last_name="Payer",
                            email=f"new-{uuid4().hex}@example.com")
    db_session.add(new_customer); await db_session.flush()
    first_order = await db_session.get(RepairOrder, first.repair_order_id)
    first_order.customer_id = new_customer.id
    await db_session.commit()
    pdf = await client.get(f"{url}/{first.id}/pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"

    reused = await client.get(url, headers=headers, params={
        **params, "updated_before": (now + timedelta(seconds=1)).isoformat(), "cursor": cursor,
    })
    assert reused.status_code == 422


@pytest.mark.asyncio
async def test_active_connection_blocks_bill_to_merge(db_session):
    owner, customer, _invoice, _vehicle = await _seed(db_session, f"merge-{uuid4().hex}")
    winner = Customer(tenant_id=owner.tenant_id, first_name="Winner", last_name="Company",
                      email=f"winner-{uuid4().hex}@example.com")
    db_session.add(winner); await db_session.commit()
    await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="ELIS"), Response(),
                             db=db_session, user=owner)
    with pytest.raises(Exception) as error:
        await customers.merge_customers(CustomerMergeRequest(winner_id=winner.id, loser_id=customer.id),
                                        db=db_session, current_user=owner)
    assert error.value.status_code == 409
    assert await db_session.get(Customer, customer.id) is not None


@pytest.mark.asyncio
async def test_vehicle_vin_correction_reappears_in_incremental_feed(client, db_session):
    owner, customer, invoice, vehicle = await _seed(db_session, f"vin-{uuid4().hex}")
    created = await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="ELIS"), Response(),
                                       db=db_session, user=owner)
    first_watermark = datetime.now(timezone.utc)
    vehicle.vin = "1HGBH41JXMN109187"
    vehicle.updated_at = datetime.now(timezone.utc)
    await db_session.commit()
    second_watermark = datetime.now(timezone.utc)
    response = await client.get("/api/v1/fleet-invoice-exports/invoices",
                                headers={"X-API-Key": created["api_key"]},
                                params={"updated_since": first_watermark.isoformat(),
                                        "updated_before": second_watermark.isoformat()})
    assert response.status_code == 200, response.text
    assert [item["invoice_id"] for item in response.json()["items"]] == [str(invoice.id)]
    assert response.json()["items"][0]["vin"] == "1HGBH41JXMN109187"


@pytest.mark.asyncio
async def test_legacy_invoice_without_verified_bill_to_is_not_exported(client, db_session):
    owner, customer, invoice, _vehicle = await _seed(db_session, f"legacy-{uuid4().hex}")
    invoice.billed_customer_id = None
    await db_session.commit()
    created = await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="ELIS"), Response(),
                                       db=db_session, user=owner)
    now = datetime.now(timezone.utc)
    response = await client.get("/api/v1/fleet-invoice-exports/invoices",
                                headers={"X-API-Key": created["api_key"]},
                                params={"updated_since": (now - timedelta(days=1)).isoformat(),
                                        "updated_before": now.isoformat()})
    assert response.status_code == 200
    assert response.json()["items"] == []
    pdf = await client.get(f"/api/v1/fleet-invoice-exports/invoices/{invoice.id}/pdf",
                           headers={"X-API-Key": created["api_key"]})
    assert pdf.status_code == 404


def test_integration_pdf_omits_contacts_notes_and_payment_rails(monkeypatch):
    captured = {}

    def render(**kwargs):
        captured.update(kwargs)
        return b"%PDF-test"

    monkeypatch.setattr(exports, "generate_invoice_pdf", render)
    invoice = Invoice(invoice_number="INV-1", status=InvoiceStatus.SENT,
                      created_at=datetime.now(timezone.utc), notes="PRIVATE NOTE",
                      subtotal=Decimal("1"), tax_amount=Decimal("0"),
                      discount_amount=Decimal("0"), total_amount=Decimal("1"),
                      shop_supplies_amount=Decimal("0"), service_fee_amount=Decimal("0"))
    order = RepairOrder(order_number="RO-1", mileage_in=100)
    customer = Customer(first_name="ELIS", last_name="Fleet", email="private@example.com",
                        phone="5550000000")
    vehicle = Vehicle(make="A", model="B", vin="1HGBH41JXMN109186")
    tenant = Tenant(name="Shop", zelle_email="payments@example.com",
                    zelle_phone="5551111111")
    assert exports._integration_pdf(invoice, order, customer, vehicle, tenant, [], []) == b"%PDF-test"
    for field in ("notes", "customer_email", "customer_phone", "zelle_email",
                  "zelle_phone", "invoice_access_url"):
        assert captured[field] is None


def test_cursor_rejects_bad_input_and_round_trips():
    now = datetime.now(timezone.utc)
    invoice_id = uuid4()
    key = exports.FleetInvoiceApiKey(id=uuid4(), key_hash="a" * 64)
    since = now - timedelta(days=1)
    before = now + timedelta(days=1)
    cursor = exports._cursor_encode(key, since, before, now, 0, invoice_id)
    assert exports._cursor_decode(cursor, key, since, before) == (now, 0, invoice_id)
    with pytest.raises(Exception) as error:
        exports._cursor_decode("not-a-valid-cursor", key, since, before)
    assert error.value.status_code == 422
    with pytest.raises(Exception) as error:
        exports._cursor_decode(cursor, key, since, before + timedelta(seconds=1))
    assert error.value.status_code == 422
    different_key = exports.FleetInvoiceApiKey(id=uuid4(), key_hash="b" * 64)
    with pytest.raises(Exception) as error:
        exports._cursor_decode(cursor, different_key, since, before)
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_export_pdf_includes_only_own_shop_review_url(db_session):
    owner, customer, invoice, vehicle = await _seed(db_session, f"review-export-{uuid4().hex}")
    tenant = await db_session.get(Tenant, owner.tenant_id)
    tenant.review_url = "https://example.com/fleet-review"
    order = await db_session.get(RepairOrder, invoice.repair_order_id)
    pdf = exports._integration_pdf(invoice, order, customer, vehicle, tenant, [], [])
    assert b"/URI (https://example.com/fleet-review)" in pdf
    tenant.id = uuid4()  # a mismatched shop must never supply its review URL
    assert b"fleet-review" not in exports._integration_pdf(invoice, order, customer, vehicle, tenant, [], [])


@pytest.mark.asyncio
async def test_customer_invoice_responses_use_invoice_shop_review_url(client, db_session, monkeypatch):
    from app.core.security import create_access_token
    owner, customer, invoice, vehicle = await _seed(db_session, f"review-response-{uuid4().hex}")
    tenant = await db_session.get(Tenant, invoice.tenant_id)
    tenant.review_url = "https://example.com/own-shop-review"
    from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
    db_session.add(Payment(tenant_id=tenant.id,invoice_id=invoice.id,payment_number=f"summary-{uuid4().hex}",amount=Decimal("40"),method=PaymentMethod.CHECK,status=PaymentStatus.COMPLETED))
    await db_session.commit()
    token = create_access_token({"sub": str(owner.id)})
    response = await client.get(f"/api/v1/invoices/{invoice.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert response.json()["review_url"] == tenant.review_url
    payload = {"invoice_id": str(invoice.id), "tenant_id": str(invoice.tenant_id), "customer_id": str(customer.id), "email": customer.email}
    from unittest.mock import AsyncMock
    from app.api.v1.endpoints import invoice_access
    monkeypatch.setattr(invoice_access, "_get_active_invoice_payload_or_400", AsyncMock(return_value=payload))
    guest = await client.post("/api/v1/invoice-access/resolve", json={"token": "fictional-test-token"})
    assert guest.status_code == 200, guest.text
    assert guest.json()["review_url"] == tenant.review_url
    assert guest.json()["payment_summary"] == response.json()["payment_summary"]
    assert guest.json()["payment_summary"]["state"] == "partially_paid"
    assert guest.json()["payment_summary"]["balance_due"] == "60.00"
    invoice.is_internal = True
    await db_session.commit()
    response = await client.get(f"/api/v1/invoices/{invoice.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.json()["review_url"] is None


@pytest.mark.asyncio
async def test_guest_print_opens_same_invoice_pdf_with_existing_token_guards(client, db_session, monkeypatch):
    from unittest.mock import AsyncMock
    from app.api.v1.endpoints import invoice_access
    owner, customer, invoice, vehicle = await _seed(db_session, f"print-view-{uuid4().hex}")
    payload = {"invoice_id": str(invoice.id), "tenant_id": str(invoice.tenant_id), "customer_id": str(customer.id)}
    monkeypatch.setattr(invoice_access, "get_invoice_access_payload", AsyncMock(return_value=payload))
    base = "/api/v1/invoice-access/pdf/fictional-print-token"
    download = await client.get(base)
    printed = await client.get(base + "?print_view=true")
    assert download.status_code == printed.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment;")
    assert printed.headers["content-disposition"].startswith("inline;")
    assert printed.headers["content-type"] == "application/pdf"
    assert printed.content.startswith(b"%PDF-")
    assert {part.strip() for part in printed.headers["cache-control"].split(",")} == {"private", "no-store"}
    payload["tenant_id"] = str(uuid4())
    assert (await client.get(base + "?print_view=true")).status_code == 400
    monkeypatch.setattr(invoice_access, "get_invoice_access_payload", AsyncMock(return_value=None))
    monkeypatch.setattr(invoice_access, "is_invoice_access_token_consumed", AsyncMock(return_value=False))
    assert (await client.get(base + "?print_view=true")).status_code == 400
