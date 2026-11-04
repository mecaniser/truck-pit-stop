"""Token-only Cards API boundary with explicit merchant environment.

The browser sends PAN/CVC directly to Intuit. This client accepts only its
opaque token and exposes masked card metadata, never raw provider payloads.
Tenant/realm admission belongs to the calling wallet service; no global
accounting or payment environment is inherited here.

Contract: Intuit's official PHP Payments SDK CardOperations and CardTest:
https://github.com/intuit/PHP-Payments-SDK/blob/master/src/Operations/CardOperations.php
https://github.com/intuit/PHP-Payments-SDK/blob/master/tests/CardTest.php
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.quickbooks_crypto import QuickBooksTokenEncryptionError, decrypt_quickbooks_token
from app.db.models.quickbooks_connection import QuickBooksConnection


class VaultError(RuntimeError):
    """Safe wallet error; mutations with uncertain outcomes must not be resent."""

    def __init__(self, message: str, *, outcome_unknown: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown
        self.status_code = status_code


@dataclass(frozen=True)
class VaultCard:
    id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int


_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,255}\Z")
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,50}\Z")
_MASKED_NUMBER = re.compile(r"[0-9]{0,6}[xX*\u2022\u25cf -]*[xX*\u2022\u25cf][xX*\u2022\u25cf -]*([0-9]{4})\Z")
_BASE_URLS = {"sandbox": "https://sandbox.api.intuit.com", "production": "https://api.intuit.com"}
_BRANDS = {
    "visa": "visa", "mastercard": "mastercard", "amex": "amex",
    "americanexpress": "amex", "discover": "discover", "dinersclub": "diners",
    "diners": "diners", "jcb": "jcb", "unionpay": "unionpay",
}
_UNAVAILABLE = "Saved cards are temporarily unavailable. Please try again."
_UNCONFIRMED = "We could not confirm whether your card was saved. Please do not add it again."


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise VaultError("The saved card reference is invalid.")
    return value


def _parse_card(payload: Any) -> VaultCard:
    if not isinstance(payload, dict):
        raise ValueError("invalid card shape")
    identifier = payload.get("id")
    if not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier):
        raise ValueError("invalid card reference")
    number = payload.get("number")
    if not isinstance(number, str) or len(number) > 64:
        raise ValueError("invalid masked number")
    masked = _MASKED_NUMBER.fullmatch(number)
    if masked is None:
        # Never accept an unexpectedly unmasked PAN, even if it is parseable.
        raise ValueError("invalid masked number")
    raw_month, raw_year = payload.get("expMonth"), payload.get("expYear")
    if (isinstance(raw_month, bool) or isinstance(raw_year, bool)
            or not re.fullmatch(r"[0-9]{1,2}", str(raw_month))
            or not re.fullmatch(r"[0-9]{4}", str(raw_year))):
        raise ValueError("invalid expiry")
    month, year = int(raw_month), int(raw_year)
    if not 1 <= month <= 12 or not 2000 <= year <= 9999:
        raise ValueError("invalid expiry")
    raw_brand = payload.get("cardType")
    brand_key = re.sub(r"[^a-z]", "", raw_brand.lower()) if isinstance(raw_brand, str) else ""
    return VaultCard(identifier, _BRANDS.get(brand_key, "card"), masked.group(1), month, year)


async def _request(
    *, connection: QuickBooksConnection, environment: str, customer_id: str,
    method: str, request_id: str, card_id: str | None = None, token: str | None = None,
) -> httpx.Response:
    if environment not in _BASE_URLS:
        raise VaultError("Secure card storage is not configured for this shop.")
    customer_id = _identifier(customer_id)
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise VaultError("The card request reference is invalid.")
    if (getattr(connection, "status", None) != "connected"
            or not getattr(connection, "realm_id", None)
            or not getattr(connection, "encrypted_access_token", None)
            or "com.intuit.quickbooks.payment" not in (getattr(connection, "scopes", "") or "").split()):
        raise VaultError("Secure card storage is not available for this shop.")
    path = f"/quickbooks/v4/customers/{customer_id}/cards"
    if card_id is not None:
        path += "/" + _identifier(card_id)
    if method == "POST":
        if (not isinstance(token, str) or not 1 <= len(token) <= 2048
                or not re.fullmatch(r"[A-Za-z0-9._~\-]+", token)
                or token.isdigit()):
            raise VaultError("The secure card token is invalid.")
        path += "/createFromToken"
    try:
        bearer = decrypt_quickbooks_token(connection.encrypted_access_token)
    except QuickBooksTokenEncryptionError:
        raise VaultError("Secure card storage is not available for this shop.") from None
    if not bearer or not isinstance(bearer, str) or not bearer.strip():
        raise VaultError("Secure card storage is not available for this shop.")
    mutation = method in {"POST", "DELETE"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.QUICKBOOKS_HTTP_TIMEOUT_SECONDS)) as client:
            response = await client.request(
                method, _BASE_URLS[environment] + path,
                headers={"Authorization": f"Bearer {bearer}", "Accept": "application/json",
                         "Content-Type": "application/json", "Request-Id": request_id},
                json={"value": token} if method == "POST" else None,
            )
    except httpx.HTTPError:
        raise VaultError(_UNCONFIRMED if mutation else _UNAVAILABLE, outcome_unknown=mutation) from None
    if method == "DELETE" and response.status_code == 404:
        # This exact customer/card path is already absent; no alternate card is tried.
        return response
    if response.status_code >= 400 or response.status_code < 200 or response.status_code >= 300:
        unknown = mutation and (300 <= response.status_code < 400 or response.status_code in {408, 425, 429} or response.status_code >= 500)
        raise VaultError(_UNCONFIRMED if unknown else _UNAVAILABLE,
                         outcome_unknown=unknown, status_code=response.status_code)
    return response


async def list_cards(*, connection: QuickBooksConnection, environment: str,
                     customer_id: str, request_id: str) -> list[VaultCard]:
    response = await _request(connection=connection, environment=environment, customer_id=customer_id,
                              method="GET", request_id=request_id)
    try:
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("invalid list")
        cards = [_parse_card(card) for card in payload]
        if len({card.id for card in cards}) != len(cards):
            raise ValueError("duplicate card reference")
        return cards
    except (ValueError, TypeError, OverflowError):
        raise VaultError(_UNAVAILABLE) from None


async def get_card(*, connection: QuickBooksConnection, environment: str,
                   customer_id: str, card_id: str, request_id: str) -> VaultCard:
    card_id = _identifier(card_id)
    response = await _request(connection=connection, environment=environment, customer_id=customer_id,
                              method="GET", request_id=request_id, card_id=card_id)
    try:
        card = _parse_card(response.json())
        if card.id != card_id:
            raise ValueError("card reference mismatch")
        return card
    except (ValueError, TypeError, OverflowError):
        raise VaultError(_UNAVAILABLE) from None


async def create_card_from_token(*, connection: QuickBooksConnection, environment: str,
                                 customer_id: str, token: str, request_id: str) -> VaultCard:
    response = await _request(connection=connection, environment=environment, customer_id=customer_id,
                              method="POST", request_id=request_id, token=token)
    try:
        return _parse_card(response.json())
    except (ValueError, TypeError, OverflowError):
        raise VaultError(_UNCONFIRMED, outcome_unknown=True) from None


async def delete_card(*, connection: QuickBooksConnection, environment: str,
                      customer_id: str, card_id: str, request_id: str) -> None:
    card_id = _identifier(card_id)
    response = await _request(connection=connection, environment=environment, customer_id=customer_id,
                              method="DELETE", request_id=request_id, card_id=card_id)
    if response.status_code not in {204, 404}:
        raise VaultError("We could not confirm whether your card was removed.", outcome_unknown=True)
