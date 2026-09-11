from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.db.models.customer_tax_exemption import CustomerTaxExemptionAudit
from app.db.models.invoice import InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.user import UserRole
from app.schemas.customer import CustomerTaxExemptionWrite
from app.services import customer_tax_exemption as tax
from app.services.invoice_settlement_service import SettlementDomainError, invoice_money_snapshot
from tests.test_db048_cash import context


async def set_default(db, ctx, enabled=True, version=0, key="customer-tax-default", reference=None):
    return await tax.update_setting(db, ctx[2].id, ctx[1], CustomerTaxExemptionWrite(
        tax_exempt=enabled, expected_version=version, support_reference=reference), key)


@pytest.mark.asyncio
async def test_default_optional_reference_audit_replay_and_existing_invoice_unchanged(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    assert tax.state(ctx[2]).model_dump() == dict(tax_exempt=False, support_reference=None, version=0, updated_at=None)
    before = (ctx[3].tax_amount, ctx[3].total_amount, ctx[3].tax_exemption, ctx[4].version)
    from app.services.invoice_cash_service import event_history_digest
    original_invoice_digest = event_history_digest(ctx[3])
    result = await set_default(db_session, ctx)
    assert result.tax_exempt and result.version == 1 and result.support_reference is None
    audit = await db_session.scalar(select(CustomerTaxExemptionAudit))
    assert audit.evidence["actor"]["id"] == str(ctx[1].id)
    assert not audit.evidence["before"]["tax_exempt"] and audit.evidence["after"]["tax_exempt"]
    assert (await set_default(db_session, ctx, reference=" \t ")).version == 1
    assert await db_session.scalar(select(func.count()).select_from(CustomerTaxExemptionAudit)) == 1
    assert before == (ctx[3].tax_amount, ctx[3].total_amount, ctx[3].tax_exemption, ctx[4].version)
    assert event_history_digest(ctx[3]) == original_invoice_digest
    from app.schemas.customer import CustomerResponse, CustomerUpdate
    public = CustomerResponse.model_validate(ctx[2]).model_dump()
    assert public["tax_exempt"] and "support_reference" not in public and "tax_exemption_support_reference" not in public
    assert CustomerUpdate(tax_exempt=False).model_dump(exclude_unset=True) == {}
    with pytest.raises(SettlementDomainError): await set_default(db_session, ctx, reference="different")
    with pytest.raises(SettlementDomainError): await set_default(db_session, ctx, key="new-key")


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["customer", "receptionist", "foreign", "deleted", "tenant_deleted", "inactive"])
async def test_setting_authorization(db_session, monkeypatch, defect):
    ctx = await context(db_session, monkeypatch)
    if defect == "customer": ctx[1].role = UserRole.CUSTOMER
    if defect == "receptionist": ctx[1].role = UserRole.RECEPTIONIST
    if defect == "foreign": ctx[1].tenant_id = uuid4()
    if defect == "deleted": ctx[2].deleted_at = datetime.now(timezone.utc)
    if defect == "tenant_deleted": ctx[0].deleted_at = datetime.now(timezone.utc)
    if defect == "inactive": ctx[0].is_active = False
    await db_session.flush()
    with pytest.raises(SettlementDomainError): await set_default(db_session, ctx)
    assert await db_session.scalar(select(func.count()).select_from(CustomerTaxExemptionAudit)) == 0


@pytest.mark.parametrize("extra", [{"reason": "not accepted"}, {"support_reference": "x"*256},
    {"expected_version": -1}, {"tax_exempt": "true"}])
def test_profile_request_validation(extra):
    with pytest.raises(ValidationError):
        CustomerTaxExemptionWrite(**{"tax_exempt": True, "expected_version": 0, **extra})


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "manual", "manual_other_payer"])
async def test_native_issuance_snapshots_customer_default(db_session, monkeypatch, mode):
    from app.api.v1.endpoints import invoices
    from app.core.config import settings
    ctx = await context(db_session, monkeypatch)
    ctx[0].sales_tax_rate = Decimal("8.5")
    ctx[0].shop_supplies_rate = Decimal("6")
    ctx[0].service_fee_rate = Decimal("3")
    ctx[3].status = InvoiceStatus.CANCELLED
    if mode != "manual_other_payer":
        await set_default(db_session, ctx, reference="Certificate ABC")
    order = await db_session.scalar(select(RepairOrder).where(RepairOrder.id == ctx[3].repair_order_id)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle)))
    order.total_labor_cost = Decimal("100")
    selected_payer = None
    if mode == "manual_other_payer":
        from app.db.models.customer import Customer
        from app.db.models.vehicle_relationship import VehicleCustomerRelationship
        other = Customer(tenant_id=ctx[0].id, first_name="Final", last_name="Payer", email="payer@example.com")
        db_session.add(other)
        await db_session.flush()
        db_session.add(VehicleCustomerRelationship(tenant_id=ctx[0].id, vehicle_id=order.vehicle_id,
            customer_id=other.id, relationship_type="default_payer"))
        selected_payer = other.id
        assert not ctx[2].tax_exempt
        ctx = (ctx[0], ctx[1], other, ctx[3], ctx[4])
        await set_default(db_session, ctx, reference="Certificate ABC")
    from app.db.models.repair_order import RepairOrderStatus
    order.status = RepairOrderStatus.COMPLETED
    await db_session.flush()
    monkeypatch.setattr(settings, "PROVIDER_OUTBOX_ENABLED", True)
    for name in ("notify_invoice_created", "broadcast_invoice_created", "broadcast_repair_order_update", "send_email"):
        monkeypatch.setattr(invoices, name, AsyncMock())
    if mode == "auto":
        created = await invoices.auto_create_invoice_for_order(db_session, order, ctx[0], ctx[1].id, notify=False)
    else:
        response = await invoices.create_invoice(invoices.InvoiceCreate(repair_order_id=order.id,
            bill_to_customer_id=selected_payer), db_session, ctx[1])
        from app.db.models.invoice import Invoice
        created = await db_session.get(Invoice, response.id)
    assert created.tax_amount == 0 and created.shop_supplies_amount == 6 and created.service_fee_amount == Decimal("3.18")
    assert created.total_amount == Decimal("109.18") and invoice_money_snapshot(created)[2] == 0
    assert created.tax_exemption["source"] == "customer_profile"
    assert created.tax_exemption["customer_id"] == str(ctx[2].id)
    assert created.tax_exemption["customer_tax_version"] == 1
    assert created.tax_exemption["support_reference"] == "Certificate ABC"
    await set_default(db_session, ctx, False, 1, "disable-setting")
    await db_session.refresh(created)
    assert created.tax_amount == 0 and created.tax_exemption["customer_tax_version"] == 1
