"""Versioned encryption boundary for tenant-owned webhook secrets."""
import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class PaidInvoiceWebhookCryptoError(RuntimeError):
    pass


PREFIX = "dbwh"


def _keyring() -> tuple[str, dict[str, Fernet]]:
    raw_keyring = settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEYS.strip()
    configured: dict[str, str] = {}
    if raw_keyring:
        try:
            decoded = json.loads(raw_keyring)
        except json.JSONDecodeError as exc:
            raise PaidInvoiceWebhookCryptoError("PAID_INVOICE_WEBHOOK_ENCRYPTION_KEYS must be valid JSON") from exc
        if not isinstance(decoded, dict) or not decoded:
            raise PaidInvoiceWebhookCryptoError("PAID_INVOICE_WEBHOOK_ENCRYPTION_KEYS must be a non-empty object")
        configured = {str(version): str(key) for version, key in decoded.items()}

    legacy = settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY.strip()
    active = settings.PAID_INVOICE_WEBHOOK_ACTIVE_KEY_VERSION.strip() or "v1"
    if legacy and not configured:
        configured[active] = legacy
    elif legacy:
        configured.setdefault("legacy", legacy)
    if not configured:
        raise PaidInvoiceWebhookCryptoError("Paid-invoice webhook encryption keyring is not configured")
    if active not in configured:
        raise PaidInvoiceWebhookCryptoError("Active paid-invoice webhook key version is missing from the keyring")

    ring: dict[str, Fernet] = {}
    try:
        for version, key in configured.items():
            if not version or ":" in version:
                raise ValueError("invalid version")
            ring[version] = Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise PaidInvoiceWebhookCryptoError("Paid-invoice webhook keyring contains an invalid Fernet key or version") from exc
    return active, ring


def encrypt_paid_invoice_webhook_secret(secret: str) -> str:
    active, ring = _keyring()
    token = ring[active].encrypt(secret.encode("utf-8")).decode("utf-8")
    return f"{PREFIX}:{active}:{token}"


def decrypt_paid_invoice_webhook_secret(encrypted_secret: str) -> str:
    _active, ring = _keyring()
    parts = encrypted_secret.split(":", 2)
    if len(parts) == 3 and parts[0] == PREFIX:
        version, token = parts[1], parts[2]
        fernet = ring.get(version)
        if not fernet:
            raise PaidInvoiceWebhookCryptoError(f"Paid-invoice webhook key version {version!r} is unavailable")
        candidates = (fernet,)
    else:
        # Legacy ciphertexts had no version prefix. Try every retained key so
        # they can be re-encrypted without downtime.
        token = encrypted_secret
        candidates = tuple(ring.values())
    for fernet in candidates:
        try:
            return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            continue
    raise PaidInvoiceWebhookCryptoError("Paid-invoice webhook secret could not be decrypted")


def reencrypt_paid_invoice_webhook_secret(encrypted_secret: str) -> str:
    return encrypt_paid_invoice_webhook_secret(decrypt_paid_invoice_webhook_secret(encrypted_secret))
