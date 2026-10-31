"""Strict, independently reviewed source correspondence for legacy bill-to identity.

These helpers never upload evidence, approve a mapping, or change source records.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select, text

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.notification import Notification, NotificationStatus, NotificationType
from app.db.models.repair_order import RepairOrder


def fail(message, code=422):
    raise HTTPException(status_code=code, detail=message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def utc(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def email(value):
    return (value or "").strip().casefold()


def snapshot(notification):
    """Canonical read-only capture contract; document bytes remain evidence."""
    return {
        "version": "db094-sent-correspondence-v1",
        "notification_id": str(notification.id), "tenant_id": str(notification.tenant_id),
        "type": notification.type.value, "status": notification.status.value,
        "recipient_email": notification.recipient_email, "subject": notification.subject,
        "body": notification.body, "template_name": notification.template_name,
        "created_at": utc(notification.created_at).isoformat(),
        "sent_at": utc(notification.sent_at).isoformat() if notification.sent_at else None,
        "external_id": notification.external_id,
    }


async def context(db, invoice):
    order = (await db.execute(select(RepairOrder).where(RepairOrder.id == invoice.repair_order_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not order or order.tenant_id != invoice.tenant_id or order.deleted_at is not None:
        fail("Invoice source context is unavailable", 409)
    predecessor = None
    replacement = order.source == "easy_truck_shop_import"
    if replacement:
        if invoice.source is not None or not invoice.supersedes_invoice_id or invoice.supersedes_invoice_id == invoice.id:
            fail("Imported ETS invoices are read-only", 409)
        predecessor = (await db.execute(select(Invoice).where(
            Invoice.id == invoice.supersedes_invoice_id,
            Invoice.tenant_id == invoice.tenant_id,
            Invoice.repair_order_id == invoice.repair_order_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if (not predecessor or predecessor.source != "easy_truck_shop_import"
                or predecessor.status != InvoiceStatus.CANCELLED or predecessor.voided_at is None
                or predecessor.deleted_at is not None or predecessor.is_internal
                or predecessor.billed_customer_id is not None
                or utc(predecessor.created_at) > utc(invoice.created_at)):
            fail("Native replacement has no verified imported predecessor", 409)
    elif invoice.source == "easy_truck_shop_import":
        fail("Imported ETS invoices are read-only", 409)
    value = {
        "invoice_id": str(invoice.id), "tenant_id": str(invoice.tenant_id),
        "repair_order_id": str(invoice.repair_order_id), "invoice_number": invoice.invoice_number,
        "invoice_source": invoice.source, "invoice_created_at": utc(invoice.created_at).isoformat(),
        "order_source": order.source,
        "supersedes_invoice_id": str(invoice.supersedes_invoice_id) if invoice.supersedes_invoice_id else None,
        "replacement": replacement,
        "predecessor": None if not predecessor else {
            "id": str(predecessor.id), "source": predecessor.source,
            "repair_order_id": str(predecessor.repair_order_id),
            "invoice_number": predecessor.invoice_number,
            "voided_at": utc(predecessor.voided_at).isoformat(),
        },
    }
    return value


class _PortalLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def has_portal_uuid(body, invoice_id):
    parser = _PortalLinks()
    parser.feed(body)
    configured = urlsplit(settings.FRONTEND_URL)
    origins = {(configured.scheme, configured.netloc), ("https", "dieselbridge.com"), ("https", "www.dieselbridge.com")}
    return any((urlsplit(link).scheme, urlsplit(link).netloc) in origins
               and urlsplit(link).path == f"/portal/invoices/{invoice_id}"
               and not urlsplit(link).username and not urlsplit(link).password
               for link in parser.links)


def contains_number(text, number):
    return bool(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(number) + r"(?![A-Za-z0-9_-])", text or ""))


async def require_unique_email(db, tenant_id, target, recipient):
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant, 94094))"), {"tenant": str(tenant_id)})
    recipient = email(recipient)
    if not recipient or email(target.email) != recipient:
        fail("Correspondence recipient differs from target identity")
    candidates = (await db.execute(select(Customer).where(
        Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None),
    ).execution_options(populate_existing=True))).scalars().all()
    if [row.id for row in candidates if email(row.email) == recipient] != [target.id]:
        fail("Correspondence recipient is not a unique active customer identity")


async def prove(db, invoice, evidence, target, proof, observed_number, reviewer_id):
    current_context = await context(db, invoice)
    if (proof.observed_invoice_id != invoice.id or proof.observed_repair_order_id != invoice.repair_order_id
            or not proof.original_correspondence_attested):
        fail("Exact original invoice and correspondence review required")
    if evidence.original_customer_id is not None and evidence.original_customer_id != target.id:
        fail("Original customer identity needs separate lineage review")
    if (evidence.source_type not in ("billing_correspondence", "preserved_source_record")
            or evidence.source_content_type != "application/json"):
        fail("Preserved sent correspondence JSON is required")
    notification = (await db.execute(select(Notification).where(
        Notification.id == proof.notification_id, Notification.tenant_id == invoice.tenant_id,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not notification:
        fail("Correspondence source not found", 404)
    if (notification.deleted_at is not None or notification.type != NotificationType.EMAIL
            or notification.status not in (NotificationStatus.SENT, NotificationStatus.DELIVERED)
            or notification.sent_at is None or notification.template_name != "invoice_created"):
        fail("Original sent invoice correspondence is required")
    created, sent = utc(notification.created_at), utc(notification.sent_at)
    issued = utc(invoice.created_at)
    if not (issued <= created <= sent <= issued + timedelta(hours=24)
            and sent <= utc(evidence.captured_at)):
        fail("Correspondence is outside original invoice issuance window")
    expected = snapshot(notification)
    if (evidence.source_document != canonical(expected).encode()
            or hashlib.sha256(evidence.source_document).hexdigest() != evidence.source_sha256):
        fail("Preserved correspondence differs from durable sent source")
    recipient = email(proof.observed_recipient_email)
    if email(notification.recipient_email) != recipient:
        fail("Observed recipient differs from original correspondence")
    await require_unique_email(db, invoice.tenant_id, target, recipient)
    if not (contains_number(notification.subject, observed_number) and contains_number(notification.body, observed_number)):
        fail("Observed invoice number is absent from original correspondence")
    alias = observed_number != invoice.invoice_number
    if alias:
        prefix = str(invoice.tenant_id).split("-")[0].upper()
        if (not current_context["replacement"]
                or not re.fullmatch(rf"INV-{prefix}-[0-9]{{6}}", observed_number)
                or not has_portal_uuid(notification.body, invoice.id)):
            fail("Historic invoice alias lacks exact native replacement UUID linkage")
    elif current_context["replacement"]:
        if not has_portal_uuid(notification.body, invoice.id):
            fail("Native replacement correspondence needs exact invoice UUID linkage")
    else:
        same_number = (await db.execute(select(Invoice.id).where(
            Invoice.tenant_id == invoice.tenant_id, Invoice.invoice_number == observed_number,
        ))).scalars().all()
        if same_number != [invoice.id]:
            fail("Historic invoice number is ambiguous")
    return {
        "version": "db094-reviewed-identity-v1", "kind": "sent_notification",
        "notification_id": str(notification.id), "notification_sha256": digest(expected),
        "recipient_email": recipient, "target_customer_id": str(target.id),
        "observed_invoice_id": str(invoice.id), "observed_repair_order_id": str(invoice.repair_order_id),
        "observed_invoice_number": observed_number, "source_sha256": evidence.source_sha256,
        "context_sha256": digest(current_context), "reviewer_id": str(reviewer_id),
    }


async def revalidate(db, invoice, evidence, target):
    """Reconstruct the original proof against current scope before granting access."""
    from types import SimpleNamespace
    try:
        value = json.loads(evidence.identity_proof)
        if (value["version"] != "db094-reviewed-identity-v1"
                or digest(value) != evidence.identity_proof_sha256
                or value["reviewer_id"] != str(evidence.verified_by_user_id)):
            raise ValueError()
        from uuid import UUID
        proof = SimpleNamespace(notification_id=UUID(value["notification_id"]),
            observed_invoice_id=UUID(value["observed_invoice_id"]),
            observed_repair_order_id=UUID(value["observed_repair_order_id"]),
            observed_recipient_email=value["recipient_email"], original_correspondence_attested=True)
        current = await prove(db, invoice, evidence, target, proof, value["observed_invoice_number"], evidence.verified_by_user_id)
    except (ValueError, KeyError, TypeError):
        fail("Verified identity proof is invalid", 409)
    except HTTPException as error:
        raise HTTPException(status_code=409, detail="Verified identity proof changed; fresh review required") from error
    if current != value:
        fail("Verified identity proof changed; fresh review required", 409)
