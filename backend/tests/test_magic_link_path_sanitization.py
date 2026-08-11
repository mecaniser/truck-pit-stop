from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.metrics import normalize_endpoint_label
from app.core.rate_limit import limiter
from app.core.redaction import (
    SensitiveDataFilter,
    redact_sensitive,
    redact_text,
    sanitize_request_path,
)
from app.db.models.error_log import ErrorCategory, ErrorSeverity
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.throttling import ThrottlingMiddleware
from app.services.error_service import log_error


TOKEN_A = "A" * 64
TOKEN_B = "B" * 64
API_PATH_A = f"/api/v1/quotes/token/{TOKEN_A}/approve"
API_PATH_B = f"/api/v1/quotes/token/{TOKEN_B}/approve"


class _CaptureLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    def _add(self, level: str, event: str, **values) -> None:
        self.events.append((level, event, values))

    def debug(self, event: str, **values) -> None:
        self._add("debug", event, **values)

    def info(self, event: str, **values) -> None:
        self._add("info", event, **values)

    def warning(self, event: str, **values) -> None:
        self._add("warning", event, **values)

    def error(self, event: str, **values) -> None:
        self._add("error", event, **values)


def _serialized(value) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def test_magic_link_path_sanitizer_covers_frontend_api_metrics_and_stdlib():
    frontend = f"https://www.example.test/quote/{TOKEN_A}?source=email"
    api = f"https://api.example.test{API_PATH_A}?safe=yes"

    assert sanitize_request_path(frontend) == (
        "https://www.example.test/quote/:token?source=email"
    )
    assert sanitize_request_path(api) == (
        "https://api.example.test/api/v1/quotes/token/:token/approve?safe=yes"
    )
    assert TOKEN_A not in redact_text(f"request failed at {api}")
    assert redact_sensitive(API_PATH_A.encode("ascii")) == (
        "/api/v1/quotes/token/:token/approve"
    )
    assert normalize_endpoint_label(API_PATH_A) == (
        "/api/v1/quotes/token/:token/approve"
    )
    assert limiter._key_style == "endpoint"

    record = logging.LogRecord(
        "uvicorn.access",
        logging.ERROR,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "POST", API_PATH_A, "1.1", 500),
        (RuntimeError, RuntimeError(f"failed at {API_PATH_A}"), None),
    )
    SensitiveDataFilter().filter(record)
    assert TOKEN_A not in record.getMessage()
    assert TOKEN_A not in (record.exc_text or "")
    assert "/api/v1/quotes/token/:token/approve" in record.getMessage()


@pytest.mark.parametrize("status_code", [200, 404, 500])
def test_magic_link_path_absent_from_observability_for_success_4xx_and_5xx(
    monkeypatch, status_code
):
    import app.middleware.observability as observability_module

    captured_context: list[dict] = []
    logger = _CaptureLogger()
    monkeypatch.setattr(observability_module, "logger", logger)
    monkeypatch.setattr(
        observability_module,
        "bind_contextvars",
        lambda **values: captured_context.append(values),
    )
    monkeypatch.setattr(observability_module, "clear_contextvars", lambda: None)

    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/api/v1/quotes/token/{token}/status")
    async def status_response(token: str):
        return JSONResponse(status_code=status_code, content={"ok": status_code < 400})

    response = TestClient(app).get(
        f"/api/v1/quotes/token/{TOKEN_A}/status"
    )

    assert response.status_code == status_code
    evidence = _serialized([captured_context, logger.events])
    assert TOKEN_A not in evidence
    assert "/api/v1/quotes/token/:token/status" in evidence


def test_magic_link_idempotency_uses_hmac_distinction_without_redis_or_log_leak(
    monkeypatch, fake_redis
):
    import app.middleware.idempotency as idempotency_module

    async def _fake_get_redis():
        return fake_redis

    logger = _CaptureLogger()
    monkeypatch.setattr(idempotency_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(idempotency_module, "logger", logger)

    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)

    @app.post("/api/v1/quotes/token/{token}/approve")
    async def approve(token: str):
        return {"approved": True}

    client = TestClient(app)
    headers = {"Idempotency-Key": "db003-magic-link-test-key"}
    first = client.post(API_PATH_A, headers=headers)
    conflict = client.post(API_PATH_B, headers=headers)

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert IdempotencyMiddleware._build_fingerprint(
        "POST", API_PATH_A, "ip:127.0.0.1", ""
    ) != IdempotencyMiddleware._build_fingerprint(
        "POST", API_PATH_B, "ip:127.0.0.1", ""
    )
    evidence = _serialized(
        {"kv": fake_redis.kv, "sets": fake_redis.sorted_sets, "logs": logger.events}
    )
    assert TOKEN_A not in evidence
    assert TOKEN_B not in evidence
    assert "/api/v1/quotes/token/:token/approve" in evidence


@pytest.mark.asyncio
async def test_magic_link_throttling_member_and_429_log_use_placeholder(
    monkeypatch, fake_redis
):
    import app.middleware.throttling as throttling_module

    async def _fake_get_redis():
        return fake_redis

    logger = _CaptureLogger()
    monkeypatch.setattr(throttling_module, "get_redis", _fake_get_redis)
    monkeypatch.setattr(throttling_module, "logger", logger)
    monkeypatch.setattr(throttling_module, "SOFT_THRESHOLD", 0)
    monkeypatch.setattr(throttling_module, "HARD_THRESHOLD", 0)

    app = FastAPI()
    app.add_middleware(ThrottlingMiddleware)

    @app.get("/api/v1/quotes/token/{token}")
    async def quote(token: str):
        return {"ok": True}

    response = TestClient(app).get(f"/api/v1/quotes/token/{TOKEN_A}")

    assert response.status_code == 429
    evidence = _serialized(
        {"kv": fake_redis.kv, "sets": fake_redis.sorted_sets, "logs": logger.events}
    )
    assert TOKEN_A not in evidence
    assert "/api/v1/quotes/token/:token" in evidence


@pytest.mark.asyncio
async def test_magic_link_path_absent_from_persisted_error_fields(db_session):
    error = await log_error(
        error_type="QuoteApprovalError",
        message=f"failed at {API_PATH_A}",
        category=ErrorCategory.AUTH,
        severity=ErrorSeverity.ERROR,
        endpoint=API_PATH_A,
        method="POST",
        status_code=500,
        stack_trace=f"RuntimeError: failed at {API_PATH_A}",
        request_context={
            "url": f"https://api.example.test{API_PATH_A}",
            "scope": {"path": API_PATH_A, "raw_path": API_PATH_A.encode("ascii")},
        },
        db=db_session,
    )

    evidence = _serialized(
        {
            "message": error.message,
            "endpoint": error.endpoint,
            "stack_trace": error.stack_trace,
            "request_context": error.request_context,
        }
    )
    assert TOKEN_A not in evidence
    assert "/api/v1/quotes/token/:token/approve" in evidence
