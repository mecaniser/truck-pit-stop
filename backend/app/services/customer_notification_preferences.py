"""One persisted policy for optional customer updates; never SMS consent."""
import hashlib
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.customer import Customer
from app.db.models.customer_notification_preferences import CustomerNotificationPreferences
from app.db.models.user import UserRole

CHOICES = ("invoice_email", "invoice_sms", "repair_email", "repair_sms")
TEMPLATES = {
    "email": {"invoice_created": "invoice_email", "invoice_reminder_email": "invoice_email", "work_started": "repair_email"},
    "sms": {"invoice_reminder_sms": "invoice_sms", "work_started_sms": "repair_sms", "work_complete_sms": "repair_sms", "ready_pickup_sms": "repair_sms"},
}
DISABLED = "customer_preference_disabled"


def context_key(tenant_id, customer_id):
    return hashlib.sha256(f"customer-notifications:{tenant_id}:{customer_id}".encode()).hexdigest()


async def own_customer(db, user, *, lock=False):
    if user.role != UserRole.CUSTOMER:
        raise HTTPException(403, "Only customer accounts can manage these preferences.")
    if not user.tenant_id or not user.customer_id:
        raise HTTPException(404, "Customer account not found.")
    query = select(Customer).where(Customer.id == user.customer_id, Customer.tenant_id == user.tenant_id, Customer.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    customer = await db.scalar(query.execution_options(populate_existing=True))
    if not customer:
        raise HTTPException(404, "Customer account not found.")
    return customer


async def load_row(db, tenant_id, customer_id):
    return await db.scalar(select(CustomerNotificationPreferences).where(
        CustomerNotificationPreferences.tenant_id == tenant_id,
        CustomerNotificationPreferences.customer_id == customer_id,
        CustomerNotificationPreferences.deleted_at.is_(None),
    ).execution_options(populate_existing=True))


def response(customer, row):
    return {
        "context_key": context_key(customer.tenant_id, customer.id),
        "revision": row.revision if row else 0,
        **{name: getattr(row, name) if row else True for name in CHOICES},
        "has_email": bool((customer.email or "").strip()),
        "has_phone": bool((customer.phone or "").strip()),
        "sms_opted_out": bool(customer.sms_opt_out),
    }


async def get_preferences(db, user):
    customer = await own_customer(db, user)
    return response(customer, await load_row(db, customer.tenant_id, customer.id))


async def save_preferences(db, user, body):
    customer = await own_customer(db, user, lock=True)
    if body.expected_context != context_key(customer.tenant_id, customer.id):
        raise HTTPException(409, "Your active shop changed. Reload notification preferences.")
    row = await load_row(db, customer.tenant_id, customer.id)
    if body.base_revision != (row.revision if row else 0):
        raise HTTPException(409, "These preferences changed elsewhere. Reload before saving.")
    if row is None:
        row = CustomerNotificationPreferences(tenant_id=customer.tenant_id, customer_id=customer.id, revision=1)
        db.add(row)
    else:
        row.revision += 1
    for name in CHOICES:
        setattr(row, name, getattr(body, name))
    row.updated_by_user_id = user.id
    await db.commit()
    await db.refresh(row)
    return response(customer, row)


def invoice_customer_scope(invoice, customer):
    """A real payer keeps its policy even when delivery contact is snapshotted.

    Legacy fleet publication binds an internal account while delivering to a
    separate vehicle billing contact; that contact has no customer login scope.
    """
    if not customer or (invoice.recipient_email and customer.is_internal_fleet):
        return None
    return customer.id


async def delivery_reason(db, *, tenant_id, customer_id, channel, template_name, recipient=None):
    """Return a policy reason only for an explicitly bound optional update.

    Third-party billing contacts, essential notices and staff/manual messages
    have no customer preference scope and retain their existing delivery path.
    """
    choice = TEMPLATES.get(channel, {}).get(template_name)
    if not choice or not customer_id:
        return None
    customer = await db.scalar(select(Customer).where(
        Customer.id == UUID(str(customer_id)), Customer.tenant_id == UUID(str(tenant_id)), Customer.deleted_at.is_(None),
    ).execution_options(populate_existing=True))
    if not customer:
        return "notification_identity_changed"
    if channel == "email" and recipient and (customer.email or "").strip().casefold() != recipient.strip().casefold():
        return "notification_identity_changed"
    row = await load_row(db, customer.tenant_id, customer.id)
    return DISABLED if row is not None and not getattr(row, choice) else None
