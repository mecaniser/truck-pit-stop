"""Network boundary checks for tenant-configured outbound webhooks."""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import anyio

MAX_VETTED_WEBHOOK_ADDRESSES = 4


class WebhookDestinationError(ValueError):
    """Raised when a webhook destination could reach a non-public network."""


class WebhookDestinationResolutionTimeout(WebhookDestinationError):
    """Raised when destination DNS exceeds its bounded resolution budget."""


@dataclass(frozen=True)
class ResolvedWebhookDestination:
    original_url: str
    tls_hostname: str
    host_header: str
    addresses: tuple[str, ...]


def _resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
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
    # Validate every answer before truncating so a private answer can never be
    # hidden beyond the connection-attempt ceiling. Sorting makes the selected
    # snapshot stable regardless of resolver response order.
    return tuple(sorted(addresses))[:MAX_VETTED_WEBHOOK_ADDRESSES]


async def resolve_webhook_destination(
    url: str,
    *,
    dns_timeout_seconds: float = 3.0,
) -> ResolvedWebhookDestination:
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
    try:
        with anyio.fail_after(dns_timeout_seconds):
            addresses = await anyio.to_thread.run_sync(
                _resolve_public_addresses,
                hostname,
                port,
                cancellable=True,
            )
    except TimeoutError as exc:
        raise WebhookDestinationResolutionTimeout(
            "Webhook hostname resolution timed out"
        ) from exc
    tls_hostname = hostname.encode("idna").decode("ascii")
    if literal and literal.version == 6:
        authority_host = f"[{hostname}]"
    else:
        authority_host = tls_hostname
    host_header = authority_host if port == 443 else f"{authority_host}:{port}"
    return ResolvedWebhookDestination(
        original_url=url,
        tls_hostname=tls_hostname,
        host_header=host_header,
        addresses=addresses,
    )


async def validate_webhook_destination(url: str) -> None:
    await resolve_webhook_destination(url)
