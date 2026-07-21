"""QuickBooks Online OAuth helpers.

This module deliberately handles authorization only.  It does not create
invoices or charges yet: those financial writes will be introduced behind
idempotent sync jobs once the connection has been validated in Intuit's
sandbox.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.quickbooks_crypto import (
    QuickBooksTokenEncryptionError,
    decrypt_quickbooks_token,
    encrypt_quickbooks_token,
    validate_quickbooks_token_encryption_key,
)
from app.db.models.quickbooks_connection import QuickBooksConnection


QUICKBOOKS_ACCOUNTING_SCOPE = "com.intuit.quickbooks.accounting"
QUICKBOOKS_PAYMENTS_SCOPE = "com.intuit.quickbooks.payment"
QUICKBOOKS_SCOPES = (QUICKBOOKS_ACCOUNTING_SCOPE, QUICKBOOKS_PAYMENTS_SCOPE)
INTUIT_AUTHORIZE_URL = "https://appcenter.intuit.com/connect/oauth2"
INTUIT_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


class QuickBooksConfigurationError(RuntimeError):
    """Required QuickBooks deployment configuration is incomplete."""


class QuickBooksOAuthError(RuntimeError):
    """Intuit rejected or could not complete an OAuth exchange."""


@dataclass(frozen=True)
class QuickBooksTokenSet:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_token_expires_in: int | None


def _required_settings() -> dict[str, str]:
    return {
        "QUICKBOOKS_CLIENT_ID": settings.QUICKBOOKS_CLIENT_ID,
        "QUICKBOOKS_CLIENT_SECRET": settings.QUICKBOOKS_CLIENT_SECRET,
        "QUICKBOOKS_REDIRECT_URI": settings.QUICKBOOKS_REDIRECT_URI,
        "QUICKBOOKS_TOKEN_ENCRYPTION_KEY": settings.QUICKBOOKS_TOKEN_ENCRYPTION_KEY,
    }


def ensure_quickbooks_configured() -> None:
    missing = [name for name, value in _required_settings().items() if not value.strip()]
    if missing:
        raise QuickBooksConfigurationError(
            "QuickBooks is not configured. Missing: " + ", ".join(missing)
        )
    try:
        validate_quickbooks_token_encryption_key()
    except QuickBooksTokenEncryptionError as exc:
        raise QuickBooksConfigurationError("QuickBooks token encryption is not configured safely") from exc


def is_quickbooks_configured() -> bool:
    """Whether deployment has the minimum credentials to start consent."""
    try:
        ensure_quickbooks_configured()
    except QuickBooksConfigurationError:
        return False
    return True


def build_authorization_url(state: str) -> str:
    ensure_quickbooks_configured()
    query = urlencode({
        'client_id': settings.QUICKBOOKS_CLIENT_ID,
        'response_type': 'code',
        'scope': ' '.join(QUICKBOOKS_SCOPES),
        'redirect_uri': settings.QUICKBOOKS_REDIRECT_URI,
        'state': state,
    })
    return f"{INTUIT_AUTHORIZE_URL}?{query}"


def _parse_positive_int(value: Any, *, field_name: str, required: bool) -> int | None:
    if value is None and not required:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise QuickBooksOAuthError(f"Intuit returned an invalid {field_name}") from exc
    if parsed <= 0:
        raise QuickBooksOAuthError(f"Intuit returned an invalid {field_name}")
    return parsed


async def exchange_authorization_code(code: str) -> QuickBooksTokenSet:
    """Exchange an authorization code without recording token values in logs."""
    ensure_quickbooks_configured()
    if not code:
        raise QuickBooksOAuthError("Intuit did not return an authorization code")

    try:
        timeout = httpx.Timeout(settings.QUICKBOOKS_HTTP_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                INTUIT_TOKEN_URL,
                auth=(settings.QUICKBOOKS_CLIENT_ID, settings.QUICKBOOKS_CLIENT_SECRET),
                headers={"Accept": "application/json"},
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.QUICKBOOKS_REDIRECT_URI,
                },
            )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        raise QuickBooksOAuthError("Could not reach Intuit during authorization") from exc

    if response.status_code >= 400:
        raise QuickBooksOAuthError("Intuit rejected the authorization exchange")
    try:
        payload = response.json()
    except ValueError as exc:
        raise QuickBooksOAuthError("Intuit returned an invalid authorization response") from exc

    if not isinstance(payload, dict):
        raise QuickBooksOAuthError("Intuit returned an invalid authorization response")
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise QuickBooksOAuthError("Intuit did not return the required authorization tokens")
    expires_in = _parse_positive_int(payload.get("expires_in"), field_name="expires_in", required=True)
    refresh_expires = _parse_positive_int(
        payload.get("x_refresh_token_expires_in"),
        field_name="x_refresh_token_expires_in",
        required=False,
    )
    return QuickBooksTokenSet(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in or 0,
        refresh_token_expires_in=refresh_expires,
    )


async def refresh_access_token(connection: QuickBooksConnection) -> QuickBooksTokenSet:
    """Rotate an Intuit token set without exposing token material to callers."""
    ensure_quickbooks_configured()
    if not connection.encrypted_refresh_token:
        raise QuickBooksOAuthError("QuickBooks refresh token is unavailable")

    try:
        refresh_token = decrypt_quickbooks_token(connection.encrypted_refresh_token)
        timeout = httpx.Timeout(settings.QUICKBOOKS_HTTP_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                INTUIT_TOKEN_URL,
                auth=(settings.QUICKBOOKS_CLIENT_ID, settings.QUICKBOOKS_CLIENT_SECRET),
                headers={"Accept": "application/json"},
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            )
    except (QuickBooksTokenEncryptionError, httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        raise QuickBooksOAuthError("Could not refresh the QuickBooks connection") from exc

    if response.status_code >= 400:
        raise QuickBooksOAuthError("QuickBooks requires this shop to reconnect")
    try:
        payload = response.json()
    except ValueError as exc:
        raise QuickBooksOAuthError("Intuit returned an invalid refresh response") from exc
    if not isinstance(payload, dict):
        raise QuickBooksOAuthError("Intuit returned an invalid refresh response")

    access_token = payload.get("access_token")
    next_refresh_token = payload.get("refresh_token")
    if not isinstance(access_token, str) or not isinstance(next_refresh_token, str):
        raise QuickBooksOAuthError("Intuit did not return refreshed credentials")
    expires_in = _parse_positive_int(payload.get("expires_in"), field_name="expires_in", required=True)
    refresh_expires = _parse_positive_int(
        payload.get("x_refresh_token_expires_in"), field_name="x_refresh_token_expires_in", required=False
    )
    return QuickBooksTokenSet(
        access_token=access_token,
        refresh_token=next_refresh_token,
        expires_in=expires_in or 0,
        refresh_token_expires_in=refresh_expires,
    )


def save_token_set(
    connection: QuickBooksConnection,
    *,
    realm_id: str,
    token_set: QuickBooksTokenSet,
    now: datetime | None = None,
) -> None:
    """Apply encrypted token material to a tenant connection in the caller's transaction."""
    if not realm_id or len(realm_id) > 64 or not realm_id.isdigit():
        raise QuickBooksOAuthError("Intuit did not return a valid company identifier")
    now = now or datetime.now(timezone.utc)
    connection.realm_id = realm_id
    connection.scopes = " ".join(QUICKBOOKS_SCOPES)
    connection.status = "connected"
    connection.encrypted_access_token = encrypt_quickbooks_token(token_set.access_token)
    connection.encrypted_refresh_token = encrypt_quickbooks_token(token_set.refresh_token)
    connection.access_token_expires_at = now + timedelta(seconds=token_set.expires_in)
    connection.refresh_token_expires_at = (
        now + timedelta(seconds=token_set.refresh_token_expires_in)
        if token_set.refresh_token_expires_in
        else None
    )
    connection.connected_at = connection.connected_at or now
    connection.disconnected_at = None


def disconnect(connection: QuickBooksConnection, *, now: datetime | None = None) -> None:
    """Forget local credentials. Revocation at Intuit is handled by reconnect consent."""
    connection.realm_id = None
    connection.scopes = ""
    connection.status = "disconnected"
    connection.encrypted_access_token = None
    connection.encrypted_refresh_token = None
    connection.access_token_expires_at = None
    connection.refresh_token_expires_at = None
    connection.disconnected_at = now or datetime.now(timezone.utc)
