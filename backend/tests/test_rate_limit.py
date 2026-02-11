from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from starlette.requests import Request

import app.core.rate_limit as rate_limit_module


def _build_request(token: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode("latin1")))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/test",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_rate_limit_key_caches_verified_token_subject(monkeypatch):
    rate_limit_module.clear_rate_limit_token_cache()
    calls = {"decode": 0}

    def _fake_decode(token: str):
        calls["decode"] += 1
        return {"sub": "user-123", "exp": 4_102_444_800}  # year 2100

    monkeypatch.setattr(rate_limit_module, "decode_token", _fake_decode)

    request = _build_request("token-a")
    key1 = rate_limit_module.rate_limit_key(request)
    key2 = rate_limit_module.rate_limit_key(request)

    assert key1 == "user:user-123"
    assert key2 == "user:user-123"
    assert calls["decode"] == 1

    rate_limit_module.clear_rate_limit_token_cache()


def test_rate_limit_key_caches_invalid_token_result(monkeypatch):
    rate_limit_module.clear_rate_limit_token_cache()
    calls = {"decode": 0}

    def _fake_decode(token: str):
        calls["decode"] += 1
        return None

    monkeypatch.setattr(rate_limit_module, "decode_token", _fake_decode)

    request = _build_request("invalid-token")
    key1 = rate_limit_module.rate_limit_key(request)
    key2 = rate_limit_module.rate_limit_key(request)

    assert key1 == "ip:127.0.0.1"
    assert key2 == "ip:127.0.0.1"
    assert calls["decode"] == 1

    rate_limit_module.clear_rate_limit_token_cache()


def test_rate_limit_key_concurrent_access_is_stable(monkeypatch):
    rate_limit_module.clear_rate_limit_token_cache()
    calls = {"decode": 0}

    def _fake_decode(token: str):
        calls["decode"] += 1
        return {"sub": "concurrent-user", "exp": 4_102_444_800}

    monkeypatch.setattr(rate_limit_module, "decode_token", _fake_decode)

    request = _build_request("token-concurrent")

    def _call_key() -> str:
        return rate_limit_module.rate_limit_key(request)

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(lambda _: _call_key(), range(500)))

    assert all(result == "user:concurrent-user" for result in results)
    # Cache should suppress repeated decode work under normal contention.
    assert calls["decode"] < 50

    rate_limit_module.clear_rate_limit_token_cache()
