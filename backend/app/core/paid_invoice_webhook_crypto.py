"""Encryption boundary for tenant-owned paid-invoice webhook secrets."""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class PaidInvoiceWebhookCryptoError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY.strip()
    if not key:
        raise PaidInvoiceWebhookCryptoError("PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise PaidInvoiceWebhookCryptoError("PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_paid_invoice_webhook_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_paid_invoice_webhook_secret(encrypted_secret: str) -> str:
    try:
        return _fernet().decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise PaidInvoiceWebhookCryptoError("Paid-invoice webhook secret could not be decrypted") from exc
