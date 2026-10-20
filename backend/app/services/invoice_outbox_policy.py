"""Identify invoice outbox evidence unrelated to payment or accounting export."""
from sqlalchemy import and_, not_, or_

from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services.conversion_pii_retention_service import SHOP_HISTORY_EVENT
from app.services.provider_outbox_service import EMAIL_NOTIFICATION_EVENT


HISTORY_CAPTURE_FAILED_EVENT = "job.history_capture_failed"
NONFINANCIAL_INVOICE_EVENTS = frozenset({SHOP_HISTORY_EVENT, HISTORY_CAPTURE_FAILED_EVENT})


def financial_invoice_outbox_clause():
    """Filter only known unrelated events; unknown delivery still fails closed."""
    return not_(or_(
        ProviderOutboxEvent.event_type == EMAIL_NOTIFICATION_EVENT,
        and_(ProviderOutboxEvent.aggregate_type == "invoice",
             ProviderOutboxEvent.event_type.in_(NONFINANCIAL_INVOICE_EVENTS)),
    ))
