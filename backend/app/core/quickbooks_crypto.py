"""Small, purpose-specific encryption boundary for QuickBooks OAuth tokens."""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class QuickBooksTokenEncryptionError(RuntimeError):
    """QuickBooks token encryption cannot be safely performed."""


def _fernet() -> Fernet:
    key = settings.QUICKBOOKS_TOKEN_ENCRYPTION_KEY.strip()
    if not key:
        raise QuickBooksTokenEncryptionError(
            "QUICKBOOKS_TOKEN_ENCRYPTION_KEY must be configured before connecting QuickBooks"
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise QuickBooksTokenEncryptionError(
            "QUICKBOOKS_TOKEN_ENCRYPTION_KEY must be a valid Fernet key"
        ) from exc


def validate_quickbooks_token_encryption_key() -> None:
    """Fail configuration checks before redirecting an admin to Intuit."""
    _fernet()


def encrypt_quickbooks_token(token: str) -> str:
    if not token:
        raise QuickBooksTokenEncryptionError("QuickBooks token cannot be empty")
    return _fernet().encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_quickbooks_token(encrypted_token: str) -> str:
    if not encrypted_token:
        raise QuickBooksTokenEncryptionError("QuickBooks encrypted token is missing")
    try:
        return _fernet().decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise QuickBooksTokenEncryptionError("QuickBooks token could not be decrypted") from exc
