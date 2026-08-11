"""Network boundary checks for tenant-configured outbound webhooks."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import anyio


class WebhookDestinationError(ValueError):
    """Raised when a webhook destination could reach a non-public network."""


def _resolve_public_addresses(hostname: str, port: int) -> set[str]:
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebhookDestinationError("Webhook hostname could not be resolved") from exc

    addresses = {record[4][0] for record in records}
    if not addresses:
        raise WebhookDestinationError("Webhook hostname could not be resolved")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise WebhookDestinationError("Webhook hostname resolved to an invalid address") from exc
        if not parsed.is_global:
            raise WebhookDestinationError("Webhook destination must resolve only to public addresses")
    return addresses


async def validate_webhook_destination(url: str) -> None:
    """Require HTTPS and reject credentials, local names, and non-public DNS results.

    This validation is repeated immediately before every request so a destination
    changed after configuration cannot silently become an internal-network target.
    Redirects are separately disabled by the delivery client.
    """

    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise WebhookDestinationError("Webhook destination must be an HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise WebhookDestinationError("Webhook destination must not include credentials")
    if parsed.fragment:
        raise WebhookDestinationError("Webhook destination must not include a fragment")

    hostname = parsed.hostname.rstrip(".").lower()
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise WebhookDestinationError("Webhook destination must use a public address")
    elif hostname == "localhost" or hostname.endswith(".localhost") or "." not in hostname:
        raise WebhookDestinationError("Webhook destination must use a public hostname")

    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise WebhookDestinationError("Webhook destination has an invalid port") from exc
    await anyio.to_thread.run_sync(_resolve_public_addresses, hostname, port)
