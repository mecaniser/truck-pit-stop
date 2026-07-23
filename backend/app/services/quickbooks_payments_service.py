"""Small, token-only client for QuickBooks Payments.

Card and bank details must go from the browser directly to Intuit's token
endpoint. This module receives only Intuit's short-lived opaque token.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings
from app.core.quickbooks_crypto import decrypt_quickbooks_token
from app.db.models.quickbooks_connection import QuickBooksConnection


class QuickBooksPaymentError(RuntimeError):
    """QuickBooks could not create, refund, or retrieve a payment."""


@dataclass(frozen=True)
class QuickBooksCharge:
    id: str
    status: str
    amount: Decimal
    raw: dict[str, Any]


@dataclass(frozen=True)
class QuickBooksRefund:
    id: str
    status: str
    amount: Decimal
    raw: dict[str, Any]


def payments_base_url() -> str:
    environment = settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower()
    if environment == "sandbox":
        return "https://sandbox.api.intuit.com"
    if environment == "production":
        return "https://api.intuit.com"
    raise QuickBooksPaymentError("QuickBooks Payments environment must be sandbox or production")


def _parse_charge(payload: Any) -> QuickBooksCharge:
    if not isinstance(payload, dict):
        raise QuickBooksPaymentError("Intuit returned an invalid payment response")
    charge_id = payload.get("id")
    charge_status = payload.get("status")
    amount = payload.get("amount")
    if not isinstance(charge_id, str) or not charge_id or not isinstance(charge_status, str) or not charge_status:
        raise QuickBooksPaymentError("Intuit returned an incomplete payment response")
    try:
        parsed_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except Exception as exc:
        raise QuickBooksPaymentError("Intuit returned an invalid payment amount") from exc
    return QuickBooksCharge(id=charge_id, status=charge_status.upper(), amount=parsed_amount, raw=payload)


async def create_charge(
    *,
    connection: QuickBooksConnection,
    token: str,
    amount: Decimal,
    description: str,
    request_id: str,
) -> QuickBooksCharge:
    """Create a captured charge using an Intuit browser token, never raw PAN data."""
    if not token or len(token) > 2048:
        raise QuickBooksPaymentError("Invalid QuickBooks payment token")
    if not connection.encrypted_access_token:
        raise QuickBooksPaymentError("QuickBooks access token is unavailable")
    try:
        access_token = decrypt_quickbooks_token(connection.encrypted_access_token)
        timeout = httpx.Timeout(settings.QUICKBOOKS_HTTP_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{payments_base_url()}/quickbooks/v4/payments/charges",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Request-Id": request_id,
                },
                json={
                    "amount": str(amount.quantize(Decimal("0.01"))),
                    "currency": "USD",
                    "token": token,
                    "capture": True,
                    "description": description[:400],
                },
            )
    except httpx.HTTPError as exc:
        raise QuickBooksPaymentError("Could not reach QuickBooks Payments") from exc

    if response.status_code >= 400:
        raise QuickBooksPaymentError("QuickBooks declined or rejected this payment")
    try:
        return _parse_charge(response.json())
    except ValueError as exc:
        raise QuickBooksPaymentError("Intuit returned an invalid payment response") from exc


def is_successful_charge(charge: QuickBooksCharge) -> bool:
    return charge.status in {"CAPTURED", "SUCCEEDED", "COMPLETED"}


async def get_charge(*, connection: QuickBooksConnection, charge_id: str) -> QuickBooksCharge:
    if not connection.encrypted_access_token or not charge_id:
        raise QuickBooksPaymentError("QuickBooks charge is unavailable")
    access_token = decrypt_quickbooks_token(connection.encrypted_access_token)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.QUICKBOOKS_HTTP_TIMEOUT_SECONDS)) as client:
            response = await client.get(
                f"{payments_base_url()}/quickbooks/v4/payments/charges/{charge_id}",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise QuickBooksPaymentError("Could not retrieve the QuickBooks payment") from exc
    if response.status_code >= 400:
        raise QuickBooksPaymentError("QuickBooks payment could not be retrieved")
    try:
        return _parse_charge(response.json())
    except ValueError as exc:
        raise QuickBooksPaymentError("Intuit returned an invalid payment response") from exc


async def refund_charge(
    *,
    connection: QuickBooksConnection,
    charge_id: str,
    amount: Decimal,
    description: str,
    request_id: str,
) -> QuickBooksRefund:
    if not connection.encrypted_access_token or not charge_id or amount <= Decimal("0.00"):
        raise QuickBooksPaymentError("QuickBooks refund request is invalid")
    access_token = decrypt_quickbooks_token(connection.encrypted_access_token)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.QUICKBOOKS_HTTP_TIMEOUT_SECONDS)) as client:
            response = await client.post(
                f"{payments_base_url()}/quickbooks/v4/payments/charges/{charge_id}/refunds",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Request-Id": request_id,
                },
                json={"amount": str(amount.quantize(Decimal("0.01"))), "description": description[:400]},
            )
    except httpx.HTTPError as exc:
        raise QuickBooksPaymentError("Could not reach QuickBooks Payments for the refund") from exc
    if response.status_code >= 400:
        raise QuickBooksPaymentError("QuickBooks rejected the refund")
    try:
        payload = response.json()
    except ValueError as exc:
        raise QuickBooksPaymentError("Intuit returned an invalid refund response") from exc
    if not isinstance(payload, dict) or not payload.get("id") or not payload.get("status"):
        raise QuickBooksPaymentError("Intuit returned an incomplete refund response")
    try:
        refunded_amount = Decimal(str(payload.get("amount"))).quantize(Decimal("0.01"))
    except Exception as exc:
        raise QuickBooksPaymentError("Intuit returned an invalid refund amount") from exc
    return QuickBooksRefund(
        id=str(payload["id"]),
        status=str(payload["status"]).upper(),
        amount=refunded_amount,
        raw=payload,
    )
