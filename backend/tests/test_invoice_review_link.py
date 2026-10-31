from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.admin import GarageProfileUpdateRequest, get_garage_profile, update_garage_profile
from app.api.v1.endpoints.invoices import _build_invoice_email_html, _build_invoice_pdf_bytes
from app.db.models.tenant import Tenant
from app.services.invoice_review_service import normalize_review_url, invoice_review_url, invoice_review_html

URL = "https://g.page/r/example/review?source=invoice&lang=en"


@pytest.mark.parametrize("value", ["javascript:alert(1)", "http://example.com", "https://example.com:90", 'https://example.com/\"x', "https://example.com/\nx", "https://example.com/a b", "https://[invalid", "https://localhost", "https://example.com/" + "a" * 2048])
def test_rejects_unsafe_review_links(value):
    with pytest.raises((ValueError, ValidationError)):
        GarageProfileUpdateRequest(name="Shop", review_url=value)


def test_rejects_embedded_sign_in_details():
    from urllib.parse import urlunsplit
    authority = "@".join(["fixture-user:fixture-password", "example.com"])
    with pytest.raises(ValueError):
        normalize_review_url(urlunsplit(("https", authority, "/review", "", "")))


def test_normalizes_optional_link_and_fails_closed():
    assert normalize_review_url("  " + URL + "  ") == URL
    assert normalize_review_url("  ") is None
    tenant = Obj(id=uuid4(), review_url=URL)
    invoice = Obj(tenant_id=tenant.id, is_internal=False)
    assert invoice_review_url(tenant, invoice) == URL
    assert "source=invoice&amp;lang=en" in invoice_review_html(tenant, invoice)
    invoice.is_internal = True
    assert invoice_review_html(tenant, invoice) == ""
    invoice.is_internal = False
    invoice.tenant_id = uuid4()
    assert invoice_review_url(tenant, invoice) is None
    invoice.tenant_id = tenant.id
    tenant.review_url = "javascript:alert(1)"
    assert invoice_review_url(tenant, invoice) is None
    assert invoice_review_url(None, invoice) is None


@pytest.mark.asyncio
async def test_profile_save_omit_clear_and_tenant_isolation(db_session):
    shop = Tenant(name="Review shop", slug="review-shop")
    other = Tenant(name="Other shop", slug="other-shop", review_url="https://example.com/other")
    db_session.add_all([shop, other])
    await db_session.commit()
    user = Obj(tenant_id=shop.id)
    saved = await update_garage_profile(GarageProfileUpdateRequest(name=shop.name, review_url=URL), db_session, user)
    assert saved.review_url == URL
    saved = await update_garage_profile(GarageProfileUpdateRequest(name=shop.name), db_session, user)
    assert saved.review_url == URL  # older clients preserve this new field
    assert (await get_garage_profile(db_session, Obj(tenant_id=other.id))).review_url == "https://example.com/other"
    for clear in (None, "  "):
        await update_garage_profile(GarageProfileUpdateRequest(name=shop.name, review_url=URL), db_session, user)
        saved = await update_garage_profile(GarageProfileUpdateRequest(name=shop.name, review_url=clear), db_session, user)
        assert saved.review_url is None


def entities():
    tenant = Obj(id=uuid4(), review_url=URL, name="Example Shop", address=None, email=None, phone=None, logo_url=None, sales_tax_rate=0, zelle_email=None, zelle_phone=None)
    invoice = Obj(id=uuid4(), tenant_id=tenant.id, is_internal=False, invoice_number="INV-DEMO", status="paid", created_at=datetime.now(timezone.utc), paid_at=datetime.now(timezone.utc), due_date=None, notes=None, subtotal=Decimal("100"), tax_amount=Decimal("0"), tax_exempt=False, discount_amount=0, shop_supplies_amount=0, service_fee_amount=0, total_amount=Decimal("100"))
    order = Obj(id=uuid4(), order_number="RO-DEMO", work_completed_at=None)
    customer = Obj(first_name="Example", last_name="Customer", email="example@example.com", phone=None, company_name=None)
    return tenant, invoice, order, customer


@pytest.mark.parametrize("status", ["paid", "pending", "overdue", "cancelled"])
def test_invoice_email_includes_neutral_link_at_every_status(status):
    tenant, invoice, order, customer = entities()
    invoice.status = status
    kwargs = dict(customer=customer, vehicle_info="Demo truck", invoice=invoice, order=order, labor_items=[], parts_items=[], invoice_access_url="https://example.com/invoice", tenant=tenant)
    html = _build_invoice_email_html(**kwargs)
    assert "Leave a review" in html
    assert 'href="https://g.page/r/example/review?source=invoice&amp;lang=en"' in html
    invoice.is_internal = True
    assert "Leave a review" not in _build_invoice_email_html(**kwargs)


def test_pdf_has_real_hyperlink_and_internal_invoice_omits_it():
    tenant, invoice, order, customer = entities()
    pdf = _build_invoice_pdf_bytes(invoice, order, customer, None, tenant, [], [], None)
    assert b"/URI (https://g.page/r/example/review?source=invoice&lang=en)" in pdf
    invoice.is_internal = True
    assert b"g.page" not in _build_invoice_pdf_bytes(invoice, order, customer, None, tenant, [], [], None)


@pytest.mark.asyncio
async def test_paid_confirmation_includes_link_in_email_and_pdf(monkeypatch):
    from app.services import invoice_notification_service as svc
    tenant, invoice, order, customer = entities()
    send = AsyncMock()
    monkeypatch.setattr(svc, "load_cash_receipt", AsyncMock(return_value=None))
    monkeypatch.setattr(svc, "generate_invoice_access_link", AsyncMock(return_value="https://example.com/invoice"))
    monkeypatch.setattr(svc, "_load_line_items", AsyncMock(return_value=([], [])))
    monkeypatch.setattr(svc, "send_email", send)
    await svc.send_invoice_payment_confirmation_email(None, invoice, order, customer, tenant, None)
    args, kwargs = send.call_args
    assert "Leave a review" in str(args) + str(kwargs)
    assert b"g.page" in kwargs["attachments"][0]["content"]
