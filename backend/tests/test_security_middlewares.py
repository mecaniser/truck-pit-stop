from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Message, Scope

from app.core.pagination import build_paginated_payload, paginated_or_list
from app.middleware.cache_control import CacheControlMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.request_size import RequestBodyLimitMiddleware
from app.middleware.timeout import TimeoutMiddleware
from app.middleware.throttling import ThrottlingMiddleware


async def _run_asgi_request(
    app: ASGIApp,
    *,
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]],
    incoming_messages: list[Message],
) -> list[Message]:
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }

    queue = list(incoming_messages)
    sent: list[Message] = []

    async def receive() -> Message:
        if queue:
            return queue.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


async def _response_status_and_headers(
    app: ASGIApp,
    *,
    method: str,
    path: str,
) -> tuple[int, dict[str, str]]:
    sent = await _run_asgi_request(
        app,
        method=method,
        path=path,
        headers=[],
        incoming_messages=[{"type": "http.request", "body": b"", "more_body": False}],
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    headers = {
        key.decode("latin1").lower(): value.decode("latin1")
        for key, value in start.get("headers", [])
    }
    return start["status"], headers


def test_idempotency_replay_and_conflict(monkeypatch, fake_redis):
    import app.middleware.idempotency as idempotency_module

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(idempotency_module, "get_redis", _fake_get_redis)

    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)
    state = {"calls": 0}

    @app.post("/api/v1/items")
    async def create_item(payload: dict):
        state["calls"] += 1
        return {"call": state["calls"], "payload": payload}

    client = TestClient(app)
    key = "abcd1234abcd1234"

    r1 = client.post("/api/v1/items", json={"name": "first"}, headers={"Idempotency-Key": key})
    assert r1.status_code == 200
    assert r1.headers.get("X-Idempotency-Replayed") == "false"

    r2 = client.post("/api/v1/items", json={"name": "first"}, headers={"Idempotency-Key": key})
    assert r2.status_code == 200
    assert r2.headers.get("X-Idempotency-Replayed") == "true"
    assert r2.json() == r1.json()
    assert state["calls"] == 1

    r3 = client.post("/api/v1/items", json={"name": "different"}, headers={"Idempotency-Key": key})
    assert r3.status_code == 409


def test_idempotency_is_optional(monkeypatch, fake_redis):
    import app.middleware.idempotency as idempotency_module

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(idempotency_module, "get_redis", _fake_get_redis)

    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)
    state = {"calls": 0}

    @app.post("/api/v1/items")
    async def create_item(payload: dict):
        state["calls"] += 1
        return {"call": state["calls"], "payload": payload}

    client = TestClient(app)

    r1 = client.post("/api/v1/items", json={"name": "a"})
    r2 = client.post("/api/v1/items", json={"name": "a"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert state["calls"] == 2


def test_idempotency_replay_preserves_cache_control_headers(monkeypatch, fake_redis):
    import app.middleware.idempotency as idempotency_module

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(idempotency_module, "get_redis", _fake_get_redis)

    app = FastAPI()
    # Match production ordering where Idempotency can short-circuit before CacheControl executes.
    app.add_middleware(CacheControlMiddleware)
    app.add_middleware(IdempotencyMiddleware)

    @app.post("/api/v1/items")
    async def create_item(payload: dict):
        return {"payload": payload}

    client = TestClient(app)
    key = "idempotency-key-123456"

    first = client.post("/api/v1/items", json={"name": "x"}, headers={"Idempotency-Key": key})
    assert first.status_code == 200
    assert first.headers.get("Cache-Control") == "no-store, private"
    assert first.headers.get("Pragma") == "no-cache"
    assert first.headers.get("Expires") == "0"

    replay = client.post("/api/v1/items", json={"name": "x"}, headers={"Idempotency-Key": key})
    assert replay.status_code == 200
    assert replay.headers.get("X-Idempotency-Replayed") == "true"
    assert replay.headers.get("Cache-Control") == "no-store, private"
    assert replay.headers.get("Pragma") == "no-cache"
    assert replay.headers.get("Expires") == "0"


def test_idempotency_replays_cacheable_422_response(monkeypatch, fake_redis):
    import app.middleware.idempotency as idempotency_module

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(idempotency_module, "get_redis", _fake_get_redis)

    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)
    state = {"calls": 0}

    @app.post("/api/v1/items")
    async def create_item(payload: dict):
        state["calls"] += 1
        return JSONResponse(status_code=422, content={"detail": "Invalid payload"})

    client = TestClient(app)
    key = "idempotency-key-422abc"

    first = client.post("/api/v1/items", json={"name": "x"}, headers={"Idempotency-Key": key})
    second = client.post("/api/v1/items", json={"name": "x"}, headers={"Idempotency-Key": key})

    assert first.status_code == 422
    assert first.headers.get("X-Idempotency-Replayed") == "false"
    assert second.status_code == 422
    assert second.headers.get("X-Idempotency-Replayed") == "true"
    assert second.json() == first.json()
    assert state["calls"] == 1


def test_idempotency_does_not_cache_500_response(monkeypatch, fake_redis):
    import app.middleware.idempotency as idempotency_module

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(idempotency_module, "get_redis", _fake_get_redis)

    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)
    state = {"calls": 0}

    @app.post("/api/v1/items")
    async def create_item(payload: dict):
        state["calls"] += 1
        if state["calls"] == 1:
            return JSONResponse(status_code=500, content={"detail": "Transient failure"})
        return {"ok": True}

    client = TestClient(app)
    key = "idempotency-key-500abc"

    first = client.post("/api/v1/items", json={"name": "x"}, headers={"Idempotency-Key": key})
    second = client.post("/api/v1/items", json={"name": "x"}, headers={"Idempotency-Key": key})

    assert first.status_code == 500
    assert first.headers.get("X-Idempotency-Replayed") == "false"
    assert second.status_code == 200
    assert second.headers.get("X-Idempotency-Replayed") == "false"
    assert state["calls"] == 2


def test_idempotency_does_not_cache_large_response_body(monkeypatch, fake_redis):
    import app.middleware.idempotency as idempotency_module

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(idempotency_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(idempotency_module, "MAX_CACHED_RESPONSE_BYTES", 32)

    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)
    state = {"calls": 0}

    @app.post("/api/v1/items")
    async def create_item(payload: dict):
        state["calls"] += 1
        return {"blob": "x" * 128}

    client = TestClient(app)
    key = "idempotency-key-large-body"

    first = client.post("/api/v1/items", json={"name": "x"}, headers={"Idempotency-Key": key})
    second = client.post("/api/v1/items", json={"name": "x"}, headers={"Idempotency-Key": key})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers.get("X-Idempotency-Replayed") == "false"
    assert second.headers.get("X-Idempotency-Replayed") == "false"
    assert state["calls"] == 2


def test_timeout_returns_504():
    app = FastAPI()
    app.add_middleware(TimeoutMiddleware, timeout_seconds=0.01)

    @app.get("/api/v1/slow")
    async def slow_endpoint():
        await asyncio.sleep(0.05)
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/api/v1/slow")
    assert response.status_code == 504
    assert response.json()["detail"] == "Request timeout"


def test_timeout_cancels_handler_execution():
    app = FastAPI()
    app.add_middleware(TimeoutMiddleware, timeout_seconds=0.01)
    state = {"finished": False, "cancelled": False}

    @app.get("/api/v1/slow-cancel")
    async def slow_cancel_endpoint():
        try:
            await asyncio.sleep(0.05)
            state["finished"] = True
            return {"ok": True}
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    client = TestClient(app)
    response = client.get("/api/v1/slow-cancel")
    assert response.status_code == 504

    # Give the cancelled task enough time to prove it doesn't keep running.
    time.sleep(0.1)
    assert state["finished"] is False
    assert state["cancelled"] is True


def test_request_body_limit_rejects_oversized_payload():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=64)

    @app.post("/api/v1/upload")
    async def upload(payload: dict):
        return payload

    client = TestClient(app)
    response = client.post("/api/v1/upload", json={"data": "x" * 256})
    assert response.status_code == 413
    assert response.json()["error"] == "Request body too large"


def test_request_body_limit_allows_payload_within_limit():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=4_096)

    @app.post("/api/v1/upload")
    async def upload(payload: dict):
        return {"size": len(payload.get("data", ""))}

    client = TestClient(app)
    response = client.post("/api/v1/upload", json={"data": "x" * 64})
    assert response.status_code == 200
    assert response.json()["size"] == 64


def test_request_body_limit_works_with_basehttp_outer_middleware():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=4_096)
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_request_body_limit_does_not_break_http_exception_responses():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=4_096)
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/api/v1/protected")
    async def protected():
        raise HTTPException(status_code=401, detail="Not authenticated")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/protected")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_request_body_limit_rejects_chunked_without_content_length():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=64)

    @app.post("/api/v1/upload")
    async def upload(request: Request):
        body = await request.body()
        return {"size": len(body)}

    sent = asyncio.run(
        _run_asgi_request(
            app,
            method="POST",
            path="/api/v1/upload",
            headers=[
                (b"host", b"testserver"),
                (b"content-type", b"application/octet-stream"),
                (b"transfer-encoding", b"chunked"),
            ],
            incoming_messages=[
                {"type": "http.request", "body": b"a" * 40, "more_body": True},
                {"type": "http.request", "body": b"b" * 40, "more_body": False},
            ],
        )
    )

    start = next(message for message in sent if message["type"] == "http.response.start")
    body = next(message for message in sent if message["type"] == "http.response.body")
    assert start["status"] == 413
    assert b"Request body too large" in body.get("body", b"")


def test_request_body_limit_rejects_underreported_content_length():
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=64)

    @app.post("/api/v1/upload")
    async def upload(request: Request):
        body = await request.body()
        return {"size": len(body)}

    sent = asyncio.run(
        _run_asgi_request(
            app,
            method="POST",
            path="/api/v1/upload",
            headers=[
                (b"host", b"testserver"),
                (b"content-type", b"application/octet-stream"),
                (b"content-length", b"10"),
            ],
            incoming_messages=[
                {"type": "http.request", "body": b"x" * 80, "more_body": False},
            ],
        )
    )

    start = next(message for message in sent if message["type"] == "http.response.start")
    body = next(message for message in sent if message["type"] == "http.response.body")
    assert start["status"] == 413
    assert b"Request body too large" in body.get("body", b"")


def test_cache_control_headers_set_for_api_routes():
    app = FastAPI()
    app.add_middleware(CacheControlMiddleware)

    @app.get("/api/v1/ping")
    async def api_ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    client = TestClient(app)

    api_response = client.get("/api/v1/ping")
    assert api_response.headers.get("Cache-Control") == "no-store, private"
    assert api_response.headers.get("Pragma") == "no-cache"
    assert api_response.headers.get("Expires") == "0"

    health_response = client.get("/health")
    assert health_response.headers.get("Cache-Control") != "no-store, private"


@pytest.mark.asyncio
async def test_throttling_limits_requests(monkeypatch, fake_redis):
    import app.middleware.throttling as throttling_module

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(throttling_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(throttling_module, "SOFT_THRESHOLD", 999)
    monkeypatch.setattr(throttling_module, "HARD_THRESHOLD", 2)
    monkeypatch.setattr(throttling_module, "MIN_DELAY", 0.0)
    monkeypatch.setattr(throttling_module, "MAX_DELAY", 0.0)

    app = FastAPI()
    app.add_middleware(ThrottlingMiddleware)

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    for _ in range(2):
        status, headers = await _response_status_and_headers(app, method="GET", path="/api/v1/ping")
        assert status == 200
        assert headers.get("x-ratelimit-limit") == "2"
        assert headers.get("x-ratelimit-remaining") is not None
        assert headers.get("x-ratelimit-reset") is not None

    status, headers = await _response_status_and_headers(app, method="GET", path="/api/v1/ping")
    assert status == 429
    assert headers.get("retry-after") == "60"
    assert headers.get("x-ratelimit-limit") == "2"
    assert headers.get("x-ratelimit-remaining") == "0"
    assert headers.get("x-ratelimit-reset") is not None


@pytest.mark.asyncio
async def test_throttling_skips_soft_delay_for_safe_reads(monkeypatch, fake_redis):
    import app.middleware.throttling as throttling_module

    async def _fake_get_redis():
        return fake_redis

    delays: list[float] = []

    async def _record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(throttling_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(throttling_module, "SOFT_THRESHOLD", 1)
    monkeypatch.setattr(throttling_module, "HARD_THRESHOLD", 3)
    monkeypatch.setattr(throttling_module.asyncio, "sleep", _record_sleep)

    app = FastAPI()
    app.add_middleware(ThrottlingMiddleware)

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    assert (await _response_status_and_headers(app, method="GET", path="/api/v1/ping"))[0] == 200
    assert (await _response_status_and_headers(app, method="GET", path="/api/v1/ping"))[0] == 200

    assert delays == []


@pytest.mark.asyncio
async def test_throttling_keeps_soft_delay_for_mutations(monkeypatch, fake_redis):
    import app.middleware.throttling as throttling_module

    async def _fake_get_redis():
        return fake_redis

    delays: list[float] = []

    async def _record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(throttling_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(throttling_module, "SOFT_THRESHOLD", 1)
    monkeypatch.setattr(throttling_module, "HARD_THRESHOLD", 3)
    monkeypatch.setattr(throttling_module, "MIN_DELAY", 0.1)
    monkeypatch.setattr(throttling_module, "MAX_DELAY", 0.5)
    monkeypatch.setattr(throttling_module.asyncio, "sleep", _record_sleep)

    app = FastAPI()
    app.add_middleware(ThrottlingMiddleware)

    @app.post("/api/v1/items")
    async def create_item():
        return {"ok": True}

    assert (await _response_status_and_headers(app, method="POST", path="/api/v1/items"))[0] == 200
    assert (await _response_status_and_headers(app, method="POST", path="/api/v1/items"))[0] == 200

    assert delays == [pytest.approx(0.3)]


@pytest.mark.asyncio
async def test_throttling_does_not_undercount_same_millisecond_requests(monkeypatch, fake_redis):
    import app.middleware.throttling as throttling_module

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(throttling_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(throttling_module.time, "time", lambda: 1_700_000_000.0)
    monkeypatch.setattr(throttling_module, "SOFT_THRESHOLD", 999999)
    monkeypatch.setattr(throttling_module, "HARD_THRESHOLD", 1)

    app = FastAPI()
    app.add_middleware(ThrottlingMiddleware)

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    first_status, _ = await _response_status_and_headers(app, method="GET", path="/api/v1/ping")
    second_status, _ = await _response_status_and_headers(app, method="GET", path="/api/v1/ping")

    assert first_status == 200
    assert second_status == 429


@pytest.mark.asyncio
async def test_throttling_does_not_apply_to_non_api_routes(monkeypatch, fake_redis):
    import app.middleware.throttling as throttling_module

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(throttling_module, "get_redis", _fake_get_redis)

    app = FastAPI()
    app.add_middleware(ThrottlingMiddleware)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    status, headers = await _response_status_and_headers(app, method="GET", path="/health")
    assert status == 200
    assert headers.get("x-ratelimit-limit") is None


def test_pagination_helper_behaviour():
    items = [{"id": 1}, {"id": 2}]
    payload = build_paginated_payload(items=items, total=5, skip=0, limit=2)
    assert payload == {
        "items": items,
        "total": 5,
        "skip": 0,
        "limit": 2,
        "has_more": True,
    }

    as_list = paginated_or_list(items=items, total=5, skip=0, limit=2, paginated=False)
    assert as_list == items

    as_paginated = paginated_or_list(items=items, total=5, skip=0, limit=2, paginated=True)
    assert isinstance(as_paginated, JSONResponse)
    body = json.loads(as_paginated.body.decode("utf-8"))
    assert body["has_more"] is True


def test_existing_strict_limits_are_still_present():
    repo_root = Path(__file__).resolve().parents[2]
    auth_text = (repo_root / "backend/app/api/v1/endpoints/auth.py").read_text()
    quotes_text = (repo_root / "backend/app/api/v1/endpoints/quotes.py").read_text()

    assert '@limiter.limit("5/minute")' in auth_text
    assert '@limiter.limit("10/minute")' in quotes_text
