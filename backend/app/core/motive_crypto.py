"""Versioned authenticated token envelopes bound to tenant, fleet and connection."""

import json
import re

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def cipher(version=None):
    version = version or settings.MOTIVE_TOKEN_ACTIVE_KEY_VERSION
    try:
        if not isinstance(version, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,32}", version
        ):
            raise ValueError()
        keys = json.loads(settings.MOTIVE_TOKEN_ENCRYPTION_KEYS)
        return Fernet(keys[version].encode())
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Motive token encryption is not configured") from None


def context(connection_id, tenant_id=None, fleet_customer_id=None):
    return [str(tenant_id), str(fleet_customer_id), str(connection_id)]


def encrypt(tokens: dict, connection_id, tenant_id=None, fleet_customer_id=None) -> str:
    version = settings.MOTIVE_TOKEN_ACTIVE_KEY_VERSION
    return (
        version
        + ":"
        + cipher(version)
        .encrypt(
            json.dumps(
                {
                    "context": context(connection_id, tenant_id, fleet_customer_id),
                    "tokens": tokens,
                }
            ).encode()
        )
        .decode()
    )


def decrypt(value: str, connection_id, tenant_id=None, fleet_customer_id=None) -> dict:
    try:
        version, ciphertext = value.split(":", 1)
        payload = json.loads(cipher(version).decrypt(ciphertext.encode()))
        if payload["context"] != context(connection_id, tenant_id, fleet_customer_id):
            raise ValueError()
        return payload["tokens"]
    except (ValueError, TypeError, KeyError, AttributeError, InvalidToken):
        raise ValueError("Motive credentials unavailable") from None
