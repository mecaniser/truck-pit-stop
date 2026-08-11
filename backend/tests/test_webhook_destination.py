import socket

import pytest

from app.core.webhook_destination import WebhookDestinationError, validate_webhook_destination


def _dns_result(address: str):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.asyncio
async def test_webhook_destination_accepts_only_public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _dns_result("93.184.216.34"))
    await validate_webhook_destination("https://hooks.example.com/conversions")


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.8", "169.254.169.254", "::1", "fc00::1"])
async def test_webhook_destination_rejects_non_public_dns(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _dns_result(address))
    with pytest.raises(WebhookDestinationError, match="public"):
        await validate_webhook_destination("https://hooks.example.com/conversions")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/path",
        "https://localhost/path",
        "https://metadata/path",
        "https://user:secret@hooks.example.com/path",
        "https://127.0.0.1/path",
        "https://hooks.example.com/path#fragment",
    ],
)
async def test_webhook_destination_rejects_unsafe_url_shapes(url):
    with pytest.raises(WebhookDestinationError):
        await validate_webhook_destination(url)
