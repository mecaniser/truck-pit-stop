"""Public review invitations, resolved from the invoice shop without provider I/O."""
from html import escape
from urllib.parse import urlsplit


def normalize_review_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    try:
        parsed = urlsplit(value)
        valid = (
            len(value) <= 2048 and parsed.scheme == "https"
            and parsed.hostname and "." in parsed.hostname
            and not parsed.username and not parsed.password
            and parsed.port in (None, 443)
            and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            and not any(c in value for c in '<>"\\')
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Review link must be a valid HTTPS URL without sign-in details")
    return value


def invoice_review_url(tenant, invoice) -> str | None:
    if tenant is None or getattr(invoice, "is_internal", False):
        return None
    # Fail closed if an accidental caller passes a different shop.
    if getattr(invoice, "tenant_id", None) != getattr(tenant, "id", None):
        return None
    try:
        return normalize_review_url(getattr(tenant, "review_url", None))
    except ValueError:
        return None


def invoice_review_html(tenant, invoice) -> str:
    url = invoice_review_url(tenant, invoice)
    if not url:
        return ""
    return (
        '<p style="margin:12px 0;font-size:13px;text-align:center;">'
        'Share your experience: '
        f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer" '
        'style="color:#b45309;text-decoration:underline;">Leave a review</a></p>'
    )
