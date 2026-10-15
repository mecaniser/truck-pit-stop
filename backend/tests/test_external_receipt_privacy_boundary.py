"""Private receipt diagnostics must not retain file-derived failure content."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import Response

from app import main
from app.db import session
from app.db.models.error_log import ErrorCategory, ErrorSeverity


def request(path):
    return Request({'type': 'http', 'method': 'POST', 'path': path, 'headers': [], 'query_string': b'', 'scheme': 'https', 'server': ('test', 443)})


def receipt_path():
    return f'/api/v1/vehicles/{uuid4()}/external-services/{uuid4()}/receipts'


def test_receipt_sql_failure_snapshot_drops_original_file_and_filename():
    marker = 'SYNTHETIC_PRIVATE_RECEIPT_BYTES'
    failure = IntegrityError('INSERT INTO receipt_blobs VALUES (?)', (marker.encode(),), Exception('driver failure'))
    assert marker in str(failure)
    envelope = main._snapshot_error(request(receipt_path()), error_type='IntegrityError', message=failure,
        category=ErrorCategory.DATABASE, severity=ErrorSeverity.ERROR, correlation_id='receipt-test', status_code=500,
        stack_trace=f'private-filename.pdf {marker}')
    assert envelope.message == 'Private receipt request failed'
    assert envelope.stack_trace is None
    assert marker not in str(envelope)
    assert 'private-filename.pdf' not in str(envelope)


def test_real_sql_error_omits_bound_receipt_bytes():
    engine = create_engine('sqlite://', **session.build_engine_options('sqlite://'))
    with engine.begin() as db:
        db.execute(text('CREATE TABLE receipts (id INTEGER PRIMARY KEY, content BLOB)'))
        db.execute(text('INSERT INTO receipts VALUES (1, :content)'), {'content': b'SYNTHETIC_PRIVATE_RECEIPT_BYTES'})
        with pytest.raises(IntegrityError) as failure:
            db.execute(text('INSERT INTO receipts VALUES (1, :content)'), {'content': b'SYNTHETIC_PRIVATE_RECEIPT_BYTES'})
    assert 'SYNTHETIC_PRIVATE_RECEIPT_BYTES' not in str(failure.value)
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 401, 403, 404, 413, 422, 500])
async def test_outer_security_headers_protect_receipt_errors_and_downloads(status):
    response = await main.add_security_headers(request(receipt_path()), AsyncMock(return_value=Response(status_code=status)))
    assert response.headers['Cache-Control'] == 'private, no-store, max-age=0'
    assert response.headers['Pragma'] == 'no-cache'
    assert response.headers['Referrer-Policy'] == 'no-referrer'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'


@pytest.mark.asyncio
async def test_upload_headers_pass_configured_cross_origin_preflight():
    from httpx import ASGITransport, AsyncClient
    origin = main.settings.CORS_ORIGINS[0]
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url='https://test') as client:
        result = await client.options(receipt_path(), headers={'Origin': origin, 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-request-id,x-expected-record-version,x-receipt-filename'})
    assert result.status_code == 200
    assert result.headers['access-control-allow-origin'] == origin
    assert result.headers['Cache-Control'] == 'private, no-store, max-age=0'


@pytest.mark.asyncio
async def test_outer_middleware_failure_keeps_response_and_diagnostics_private(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from starlette.middleware.base import BaseHTTPMiddleware

    class FailedMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            raise RuntimeError('SYNTHETIC_PRIVATE_RECEIPT_BYTES')

    isolated = FastAPI()
    isolated.add_exception_handler(Exception, main.global_exception_handler)
    isolated.add_middleware(FailedMiddleware)
    isolated.middleware('http')(main.add_security_headers)
    persisted = []

    async def capture(envelope):
        persisted.append(envelope)

    monkeypatch.setattr(main, '_log_error_async', capture)
    async with AsyncClient(transport=ASGITransport(app=isolated, raise_app_exceptions=False), base_url='https://test') as client:
        result = await client.post(receipt_path())
    assert result.status_code == 500
    assert result.headers['Cache-Control'] == 'private, no-store, max-age=0'
    assert result.headers['Pragma'] == 'no-cache'
    assert result.headers['X-Content-Type-Options'] == 'nosniff'
    assert result.headers['Referrer-Policy'] == 'no-referrer'
    assert 'SYNTHETIC_PRIVATE_RECEIPT_BYTES' not in result.text
    assert len(persisted) == 1
    assert persisted[0].message == 'Private receipt request failed'
    assert persisted[0].stack_trace is None
