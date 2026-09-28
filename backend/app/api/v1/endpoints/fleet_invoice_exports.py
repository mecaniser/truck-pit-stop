"""Read-only, bill-to scoped invoice feed for fleet accounting importers."""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.models.customer import Customer
from app.db.models.fleet_invoice_api_key import FleetInvoiceApiKey
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.api.v1.endpoints.invoices import _load_line_items
from app.services.invoice_charge_state import effective_tax_exempt
from app.services.pdf_service import generate_invoice_pdf
from app.services.conversion_export_audit_service import record_conversion_audit

router = APIRouter()


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _owner_tenant(user: User) -> UUID:
    if user.role != UserRole.GARAGE_OWNER or not user.tenant_id:
        raise HTTPException(status_code=403, detail="Shop owner required")
    return user.tenant_id


async def _active_key(
    x_api_key: str | None = Header(None, alias="X-API-Key", max_length=255),
    db: AsyncSession = Depends(get_db),
) -> FleetInvoiceApiKey:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    key = (await db.execute(select(FleetInvoiceApiKey).where(
        FleetInvoiceApiKey.key_hash == _hash_key(x_api_key),
        FleetInvoiceApiKey.revoked_at.is_(None),
    ))).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    tenant = await db.get(Tenant, key.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=401, detail="Shop is inactive")
    customer = await db.get(Customer, key.customer_id)
    if not customer or customer.tenant_id != key.tenant_id or customer.deleted_at is not None:
        raise HTTPException(status_code=401, detail="Bill-to account is inactive")
    return key


class KeyRequest(BaseModel):
    customer_id: UUID
    name: str = Field(min_length=1, max_length=120)


@router.post("/api-keys", status_code=201)
async def create_key(
    body: KeyRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant_id = _owner_tenant(user)
    # Serialize provisioning against customer merge and other key issuance.
    customer = (await db.execute(select(Customer).where(Customer.id == body.customer_id)
                                 .with_for_update())).scalar_one_or_none()
    if not customer or customer.tenant_id != tenant_id or customer.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Bill-to customer not found")
    existing = (await db.execute(select(FleetInvoiceApiKey.id).where(
        FleetInvoiceApiKey.tenant_id == tenant_id,
        FleetInvoiceApiKey.customer_id == customer.id,
        FleetInvoiceApiKey.revoked_at.is_(None),
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Active bill-to key already exists")
    raw = f"dbfi_{secrets.token_urlsafe(32)}"
    key = FleetInvoiceApiKey(
        tenant_id=tenant_id, customer_id=customer.id,
        name=body.name.strip(), key_prefix=raw[:12], key_hash=_hash_key(raw),
    )
    db.add(key)
    await db.flush()
    record_conversion_audit(db, tenant_id=tenant_id, actor_user_id=user.id,
                            action="fleet_invoice_key.created", target_type="fleet_invoice_api_key",
                            target_id=key.id, metadata={"key_prefix": key.key_prefix})
    await db.commit()
    await db.refresh(key)
    response.headers["Cache-Control"] = "no-store"
    return {"id": key.id, "customer_id": key.customer_id, "name": key.name,
            "key_prefix": key.key_prefix, "api_key": raw, "created_at": key.created_at}


@router.get("/api-keys")
async def list_keys(
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant_id = _owner_tenant(user)
    keys = (await db.execute(select(FleetInvoiceApiKey).where(
        FleetInvoiceApiKey.tenant_id == tenant_id,
    ).order_by(FleetInvoiceApiKey.created_at.desc()))).scalars().all()
    response.headers["Cache-Control"] = "no-store"
    return [{"id": k.id, "customer_id": k.customer_id, "name": k.name,
             "key_prefix": k.key_prefix, "last_used_at": k.last_used_at,
             "revoked_at": k.revoked_at} for k in keys]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant_id = _owner_tenant(user)
    key = await db.get(FleetInvoiceApiKey, key_id)
    if not key or key.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = datetime.now(timezone.utc)
    record_conversion_audit(db, tenant_id=tenant_id, actor_user_id=user.id,
                            action="fleet_invoice_key.revoked", target_type="fleet_invoice_api_key",
                            target_id=key.id, metadata={"key_prefix": key.key_prefix})
    await db.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


def _scope(key: FleetInvoiceApiKey):
    return (
        Invoice.tenant_id == key.tenant_id,
        RepairOrder.tenant_id == key.tenant_id,
        Invoice.billed_customer_id == key.customer_id,
        Customer.id == key.customer_id,
        Customer.tenant_id == key.tenant_id,
        Vehicle.tenant_id == key.tenant_id,
        Invoice.is_internal.is_(False),
        Invoice.status != InvoiceStatus.DRAFT,
        Invoice.deleted_at.is_(None),
    )


def _invoice_query(key: FleetInvoiceApiKey):
    return (select(Invoice, RepairOrder, Customer, Vehicle)
            .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
            .join(Customer, Invoice.billed_customer_id == Customer.id)
            .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
            .where(*_scope(key)))


def _effective_updated_at():
    invoice_or_order = case(
        (Invoice.updated_at >= RepairOrder.updated_at, Invoice.updated_at),
        else_=RepairOrder.updated_at,
    )
    return case((invoice_or_order >= Vehicle.updated_at, invoice_or_order),
                else_=Vehicle.updated_at)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _cursor_encode(key: FleetInvoiceApiKey, since: datetime, before: datetime,
                   updated_at: datetime, invoice_id: UUID) -> str:
    updated_at = _utc(updated_at)
    payload = json.dumps([str(key.id), since.isoformat(), before.isoformat(),
                          updated_at.isoformat(), str(invoice_id)], separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(key.key_hash.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _cursor_decode(value: str, key: FleetInvoiceApiKey,
                   since: datetime, before: datetime) -> tuple[datetime, UUID]:
    try:
        if len(value) > 512:
            raise ValueError("oversized cursor")
        encoded, signature = value.split(".", 1)
        expected = hmac.new(key.key_hash.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        key_id, saved_since, saved_before, timestamp, invoice_id = json.loads(raw)
        if (key_id != str(key.id) or saved_since != since.isoformat()
                or saved_before != before.isoformat()):
            raise ValueError("wrong cursor scope")
        dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:
            raise ValueError("timezone required")
        return dt, UUID(invoice_id)
    except (ValueError, TypeError, IndexError, UnicodeDecodeError, binascii.Error):
        raise HTTPException(status_code=422, detail="Invalid cursor") from None


def _money(value) -> str:
    return f"{value:.2f}"


def _integration_pdf(invoice: Invoice, order: RepairOrder, customer: Customer,
                     vehicle: Vehicle, tenant: Tenant, labor: list, parts: list) -> bytes:
    """Render financial invoice facts without contact, private notes or payment rails."""
    return generate_invoice_pdf(
        invoice_number=invoice.invoice_number,
        order_number=order.order_number,
        invoice_date=(invoice.ets_invoiced_at or invoice.created_at.date()).strftime("%m/%d/%Y"),
        service_completed=order.work_completed_at.strftime("%m/%d/%Y") if order.work_completed_at else None,
        due_date=invoice.due_date.strftime("%m/%d/%Y") if invoice.due_date else None,
        status=invoice.status.value,
        notes=None,
        customer_company=customer.company_name,
        customer_name=f"{customer.first_name} {customer.last_name}",
        customer_email=None,
        customer_phone=None,
        shop_name=tenant.name,
        shop_address=tenant.address,
        shop_email=tenant.email,
        shop_phone=tenant.phone,
        shop_logo_url=tenant.logo_url,
        vehicle_year=str(vehicle.year) if vehicle.year else None,
        vehicle_make=vehicle.make,
        vehicle_model=vehicle.model,
        vehicle_unit=vehicle.unit_number,
        vehicle_vin=vehicle.vin,
        vehicle_odometer=order.mileage_in,
        labor_items=labor,
        parts_items=parts,
        labor_total=sum((Decimal(str(item.get("total_cost", 0))) for item in labor), Decimal("0")),
        parts_total=sum((Decimal(str(item.get("total_price", 0))) for item in parts), Decimal("0")),
        shop_supplies_amount=invoice.shop_supplies_amount,
        service_fee_amount=invoice.service_fee_amount,
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        tax_rate=float(tenant.sales_tax_rate) if tenant.sales_tax_rate else None,
        tax_exempt=effective_tax_exempt(invoice),
        discount_amount=invoice.discount_amount,
        total_amount=invoice.total_amount,
        invoice_access_url=None,
        zelle_email=None,
        zelle_phone=None,
    )


def _item(invoice: Invoice, order: RepairOrder, vehicle: Vehicle,
          effective_updated_at: datetime) -> dict:
    return {
        "shop_id": str(invoice.tenant_id),
        "invoice_id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "repair_order_id": str(order.id),
        "vehicle_id": str(vehicle.id),
        "vin": vehicle.vin,
        "unit_number": vehicle.unit_number,
        "mileage_in": order.mileage_in,
        "mileage_in_carried": order.mileage_in_carried,
        "invoice_date": invoice.ets_invoiced_at.isoformat() if invoice.ets_invoiced_at else invoice.created_at.date().isoformat(),
        "invoice_date_source": "ets_invoice" if invoice.ets_invoiced_at else "dieselbridge_created",
        "effective_updated_at": _utc(effective_updated_at).isoformat(),
        "status": invoice.status.value,
        "voided_at": invoice.voided_at.isoformat() if invoice.voided_at else None,
        "supersedes_invoice_id": str(invoice.supersedes_invoice_id) if invoice.supersedes_invoice_id else None,
        "subtotal": _money(invoice.subtotal),
        "shop_supplies_amount": _money(invoice.shop_supplies_amount),
        "service_fee_amount": _money(invoice.service_fee_amount),
        "tax_amount": _money(invoice.tax_amount),
        "discount_amount": _money(invoice.discount_amount),
        "total_amount": _money(invoice.total_amount),
        "currency": "USD",
        "line_items": invoice.line_items_snapshot,
    }


@router.get("/invoices")
async def list_invoices(
    response: Response,
    updated_since: datetime = Query(...),
    updated_before: datetime = Query(...),
    limit: int = Query(100, ge=1, le=100),
    cursor: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    key: FleetInvoiceApiKey = Depends(_active_key),
):
    if (updated_since.tzinfo is None or updated_before.tzinfo is None
            or updated_before <= updated_since or updated_before > datetime.now(timezone.utc)):
        raise HTTPException(status_code=422, detail="Invalid UTC sync window")
    effective = _effective_updated_at()
    query = _invoice_query(key).add_columns(effective.label("effective_updated_at")).where(
        effective >= updated_since,
        effective < updated_before,
    )
    if cursor:
        cursor_at, cursor_id = _cursor_decode(cursor, key, updated_since, updated_before)
        if cursor_at < updated_since or cursor_at > updated_before:
            raise HTTPException(status_code=422, detail="Cursor outside sync window")
        query = query.where(or_(effective > cursor_at,
                                and_(effective == cursor_at, Invoice.id > cursor_id)))
    rows = (await db.execute(query.order_by(effective, Invoice.id).limit(limit + 1))).all()
    page = rows[:limit]
    next_cursor = _cursor_encode(key, updated_since, updated_before,
                                 page[-1][4], page[-1][0].id) if len(rows) > limit else None
    key.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"items": [_item(inv, order, vehicle, effective_at)
                      for inv, order, _customer, vehicle, effective_at in page],
            "next_cursor": next_cursor, "watermark": updated_before.isoformat()}


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    key: FleetInvoiceApiKey = Depends(_active_key),
):
    row = (await db.execute(_invoice_query(key).where(Invoice.id == invoice_id))).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice, order, customer, vehicle = row
    tenant = await db.get(Tenant, key.tenant_id)
    labor, parts = await _load_line_items(db, order.id, invoice)
    pdf = _integration_pdf(invoice, order, customer, vehicle, tenant, labor, parts)
    key.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="Invoice-{invoice.invoice_number}.pdf"',
        "Cache-Control": "no-store",
    })
