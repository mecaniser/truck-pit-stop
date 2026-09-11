"""Audited customer default; only new native invoices consume this setting."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.dependencies import user_has_permission
from app.db.models.customer import Customer
from app.db.models.customer_tax_exemption import CustomerTaxExemptionAudit
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.schemas.customer import CustomerTaxExemptionRead
from app.services.invoice_settlement_service import SettlementDomainError, _canonical_hash, _actor_snapshot


def state(customer):
    return CustomerTaxExemptionRead(tax_exempt=customer.tax_exempt,
        support_reference=customer.tax_exemption_support_reference,
        version=customer.tax_exemption_version, updated_at=customer.tax_exemption_updated_at)


async def customer_for_setting(db, customer_id, actor, *, lock=False):
    if actor.role not in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN} or not user_has_permission(actor, "payments"):
        raise SettlementDomainError("customer_not_found", "Customer not found.", status_code=404)
    return await active_customer(db, customer_id, actor.tenant_id, lock=lock)


async def active_customer(db, customer_id, tenant_id, *, lock=False):
    query = select(Customer).join(Tenant, Tenant.id == Customer.tenant_id).where(
        Customer.id == customer_id, Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None),
        Tenant.is_active.is_(True), Tenant.deleted_at.is_(None))
    if lock:
        query = query.with_for_update(of=Customer)
    customer = await db.scalar(query.execution_options(populate_existing=True))
    if customer is None:
        raise SettlementDomainError("customer_not_found", "Customer not found.", status_code=404)
    return customer


async def update_setting(db, customer_id, actor, body, key):
    if not key or not key.strip() or len(key.strip()) > 255:
        raise SettlementDomainError("idempotency_key_required", "A valid Idempotency-Key is required.", status_code=422)
    key = key.strip()
    customer = await customer_for_setting(db, customer_id, actor, lock=True)
    fingerprint = _canonical_hash({"customer_id": str(customer.id), "actor_id": str(actor.id), **body.model_dump()})
    previous = await db.scalar(select(CustomerTaxExemptionAudit).where(
        CustomerTaxExemptionAudit.tenant_id == customer.tenant_id,
        CustomerTaxExemptionAudit.idempotency_key == key))
    if previous:
        if previous.request_hash != fingerprint:
            raise SettlementDomainError("idempotency_conflict", "This key was used for a different customer tax setting.")
        return state(customer)
    if customer.tax_exemption_version != body.expected_version:
        raise SettlementDomainError("stale_customer_tax_version", "The tax setting changed. Refresh and retry.",
            current_version=customer.tax_exemption_version)
    before = state(customer).model_dump(mode="json")
    try:
        async with db.begin_nested():
            customer.tax_exempt = body.tax_exempt
            customer.tax_exemption_support_reference = body.support_reference
            customer.tax_exemption_version += 1
            customer.tax_exemption_updated_at = datetime.now(timezone.utc)
            actor_id, name, role = _actor_snapshot(actor)
            db.add(CustomerTaxExemptionAudit(tenant_id=customer.tenant_id, customer_id=customer.id,
                version=customer.tax_exemption_version, idempotency_key=key, request_hash=fingerprint,
                evidence={"schema": "customer-tax-default-v1", "actor": {"id": str(actor_id), "name": name, "role": role},
                    "customer": {"id": str(customer.id), "tenant_id": str(customer.tenant_id),
                        "name": customer.company_name or f"{customer.first_name} {customer.last_name}".strip()},
                    "before": before, "after": state(customer).model_dump(mode="json")}))
            await db.flush()
    except IntegrityError as exc:
        # A tenant-wide key can race on two separately locked customers. The
        # savepoint rolls back only this command's changes, including version.
        raise SettlementDomainError("idempotency_conflict", "This key was used for a different customer tax setting.") from exc
    return state(customer)


async def issuance_default(db, order, tenant):
    customer = await active_customer(db, order.customer_id, tenant.id, lock=True)
    if order.is_internal or not customer.tax_exempt:
        return None
    audit = await db.scalar(select(CustomerTaxExemptionAudit).where(
        CustomerTaxExemptionAudit.tenant_id == tenant.id, CustomerTaxExemptionAudit.customer_id == customer.id,
        CustomerTaxExemptionAudit.version == customer.tax_exemption_version))
    if (not audit or audit.evidence["after"]["tax_exempt"] is not True
            or audit.evidence["after"]["version"] != customer.tax_exemption_version
            or audit.evidence["after"]["support_reference"] != customer.tax_exemption_support_reference):
        raise SettlementDomainError("customer_tax_default_unverified", "Review the customer tax setting before issuing an invoice.")
    return {"customer_id": str(customer.id), "version": customer.tax_exemption_version,
        "support_reference": customer.tax_exemption_support_reference, "audit_id": str(audit.id),
        "actor": audit.evidence["actor"]}


def stamp_invoice(invoice, default, taxable_checkout, issuer_id):
    if not default:
        return
    from app.services.invoice_tax_exemption import snapshot
    invoice.id = invoice.id or uuid4()
    after = snapshot(invoice)
    before = {**after, "tax_amount": str(taxable_checkout["tax_amount"]),
        "total_amount": str(invoice.total_amount + taxable_checkout["tax_amount"])}
    invoice.tax_exemption = {"schema": "invoice-tax-exemption-v1", "source": "customer_profile",
        "tenant_id": str(invoice.tenant_id), "invoice_id": str(invoice.id),
        "customer_id": default["customer_id"], "customer_tax_version": default["version"],
        "customer_tax_audit_id": default["audit_id"], "applied_at": datetime.now(timezone.utc).isoformat(),
        "actor_id": default["actor"]["id"], "actor_name": default["actor"]["name"], "actor_role": default["actor"]["role"],
        "issued_by_user_id": str(issuer_id) if issuer_id else None,
        "reason": None, "support_reference": default["support_reference"], "before": before, "after": after,
        "before_settlement_version": None, "after_settlement_version": None,
        "idempotency_key": f"customer-profile:{invoice.id}:{default['version']}",
        "request_hash": _canonical_hash({"invoice_id": str(invoice.id), **default})}
