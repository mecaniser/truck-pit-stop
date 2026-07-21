from datetime import datetime, timezone

from app.api.v1.endpoints.dashboard import is_pending_zelle_confirmation
from app.db.models.invoice import InvoiceStatus


def test_pending_zelle_confirmation_requires_submission_and_unpaid_invoice():
    submitted_at = datetime.now(timezone.utc)

    assert is_pending_zelle_confirmation(InvoiceStatus.SENT, submitted_at) is True
    assert is_pending_zelle_confirmation(InvoiceStatus.PAID, submitted_at) is False
    assert is_pending_zelle_confirmation(InvoiceStatus.SENT, None) is False
