from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import hashlib

import pytest

from app.db.models.conversion_api_key import ConversionApiKey
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant


async def _seed(db, *, slug: str, raw_key: str, campaign: str):
    tenant = Tenant(name=slug, slug=slug)
    customer = Customer(tenant=tenant, first_name="Test", last_name="Customer", email=f"{slug}@example.com", phone="+15555550000")
    order = RepairOrder(tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"TPS-{uuid4().hex[:8]}", status=RepairOrderStatus.PAID, utm_campaign=campaign)
    invoice = Invoice(tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID, subtotal=Decimal("50"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("50"), paid_at=datetime.now(timezone.utc), line_items_snapshot={"labor": [{"description": "Diagnostic", "hours": "1", "total_cost": "50"}], "parts": []})
    key = ConversionApiKey(tenant=tenant, name="CallRail", key_prefix=raw_key[:12], key_hash=hashlib.sha256(raw_key.encode()).hexdigest())
    db.add_all([tenant, customer, order, invoice, key]); await db.commit()
    return tenant, key


@pytest.mark.asyncio
async def test_export_api_is_tenant_isolated_and_contains_attribution(client, db_session):
    raw_key = "dbce_tenant_one_secret"
    await _seed(db_session, slug=f"one-{uuid4().hex}", raw_key=raw_key, campaign="campaign-one")
    await _seed(db_session, slug=f"two-{uuid4().hex}", raw_key="dbce_tenant_two_secret", campaign="campaign-two")
    now = datetime.now(timezone.utc)
    response = await client.get("/api/v1/conversion-exports/paid-repair-orders", headers={"X-API-Key": raw_key}, params={"paid_from": (now - timedelta(days=1)).isoformat(), "paid_to": (now + timedelta(days=1)).isoformat()})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["attribution"]["utm_campaign"] == "campaign-one"
    assert body["items"][0]["customer"]["phone"] == "+15555550000"


@pytest.mark.asyncio
async def test_revoked_api_key_is_rejected(client, db_session):
    raw_key = "dbce_revoked_secret"
    _tenant, key = await _seed(db_session, slug=f"revoked-{uuid4().hex}", raw_key=raw_key, campaign="x")
    key.revoked_at = datetime.now(timezone.utc); await db_session.commit()
    now = datetime.now(timezone.utc)
    response = await client.get("/api/v1/conversion-exports/paid-repair-orders", headers={"X-API-Key": raw_key}, params={"paid_from": (now - timedelta(days=1)).isoformat(), "paid_to": now.isoformat()})
    assert response.status_code == 401
