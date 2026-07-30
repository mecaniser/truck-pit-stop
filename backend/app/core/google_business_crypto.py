"""Encryption boundary for Google Business Profile OAuth tokens."""
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings


class GoogleBusinessTokenEncryptionError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.GOOGLE_BUSINESS_TOKEN_ENCRYPTION_KEY.strip()
    if not key:
        raise GoogleBusinessTokenEncryptionError("GOOGLE_BUSINESS_TOKEN_ENCRYPTION_KEY must be configured")
    try:
        return Fernet(key.encode())
    except (TypeError, ValueError) as exc:
        raise GoogleBusinessTokenEncryptionError("GOOGLE_BUSINESS_TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_google_business_token(token: str) -> str:
    if not token:
        raise GoogleBusinessTokenEncryptionError("Google token cannot be empty")
    return _fernet().encrypt(token.encode()).decode()


def decrypt_google_business_token(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, AttributeError) as exc:
        raise GoogleBusinessTokenEncryptionError("Google token could not be decrypted") from exc
