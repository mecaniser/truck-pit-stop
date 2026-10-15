"""DB128 private receipt lifecycle, bounded content and actual HTTP contracts."""
from datetime import UTC, date, datetime
from io import BytesIO
import struct
from types import SimpleNamespace
from urllib.parse import quote
from uuid import uuid4
import zlib

from fastapi import HTTPException
from PIL import Image
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import InvalidRequestError

from app.db.models.external_service import ExternalServiceEvent as ServiceEvent
from app.db.models.external_service_receipt import ExternalServiceReceipt as Receipt, ExternalServiceReceiptBlob as Blob, ExternalServiceReceiptEvent as Event
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.user import UserRole
from app.schemas.external_service import ExternalServiceRestore, ExternalServiceVoid
from app.schemas.external_service_receipt import ReceiptUpload, ReceiptRemove, ReceiptRestore
from app.services import external_service as records, external_service_receipt as receipts
from test_external_service import add_vehicle, create
from test_service_checklists import seed


PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


def upload_request(**values):
    return ReceiptUpload(**(dict(request_id=uuid4(), expected_record_version=1) | values))


def upload_file(content=PDF, filename="QA receipt.pdf"):
    return receipts.validate_content(content, filename)


def image_bytes(format="PNG", **options):
    output = BytesIO()
    Image.new("RGB", (3, 2), color="white").save(output, format=format, **options)
    return output.getvalue()


async def setup(db):
    a = await seed(db)
    a.record = (await records.mutate(db, a.vehicle.id, a.owner, create())).record
    await db.commit()
    return a


async def upload(db, a, body=None, file=None):
    return await receipts.mutate(db, a.vehicle.id, a.record.id, a.owner, body or upload_request(), upload=file or upload_file())


async def error(code, call):
    with pytest.raises(HTTPException) as failure:
        await call
    assert failure.value.status_code == receipts.ERRORS[code][0]
    assert failure.value.detail["code"] == code


def headers(body=None, filename="QA receipt.pdf", **changes):
    body = body or upload_request()
    return {"Content-Type": "application/octet-stream", "X-Request-ID": str(body.request_id), "X-Expected-Record-Version": str(body.expected_record_version), "X-Receipt-Filename": quote(filename, safe="")} | changes


def path(a):
    return f"/api/v1/vehicles/{a.vehicle.id}/external-services/{a.record.id}/receipts"


@pytest.mark.asyncio
async def test_lifecycle_replay_snapshot_and_native_invariants(db_session):
    a = await setup(db_session)
    a.vehicle.mileage, a.vehicle.next_pm_miles, a.vehicle.pm_due_date = 500000, 510000, date(2026, 11, 1)
    await db_session.commit()
    before = (a.order.status, a.order.total_cost, a.vehicle.mileage, a.vehicle.next_pm_miles, a.vehicle.pm_due_date)
    counts = [await db_session.scalar(select(func.count(model.id))) for model in (Invoice, Payment, ServiceEvent)]
    body = upload_request()
    saved = await upload(db_session, a, body)
    await db_session.commit()
    first = saved.receipt
    assert first.created_by_name == "Casey Owner" and first.version == saved.record_version == 1
    assert first.uploaded_vehicle_id == first.vehicle_id == a.vehicle.id
    assert not saved.replayed
    # A new ORM load of a blob cannot accidentally expose bytes.
    db_session.expunge_all()
    blob = await db_session.scalar(select(Blob).where(Blob.receipt_id == first.id))
    with pytest.raises(InvalidRequestError):
        _ = blob.content
    queries = []
    connection = await db_session.connection()
    def capture(conn, cursor, statement, parameters, context, many):
        queries.append(statement)
    event.listen(connection.sync_connection, "before_cursor_execute", capture)
    try:
        page = await receipts.page(db_session, a.vehicle.id, a.record.id, a.owner)
        history = await receipts.history(db_session, a.vehicle.id, a.record.id, first.id, a.owner)
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", capture)
    assert page.items == [first] and history.items[0].snapshot == first
    assert all("external_service_receipt_blobs" not in query for query in queries)
    assert "content_sha256" not in page.model_dump_json() and "content" not in history.model_dump_json()
    assert (await receipts.download(db_session, a.vehicle.id, a.record.id, first.id, a.owner))[0] == PDF
    remove = ReceiptRemove(request_id=uuid4(), expected_record_version=1, expected_version=1, reason="  Wrong file  ")
    removed = await receipts.mutate(db_session, a.vehicle.id, a.record.id, a.owner, remove, action="remove", receipt_id=first.id)
    assert removed.receipt.version == 2 and removed.receipt.removed_at
    await error("receipt_removed", receipts.download(db_session, a.vehicle.id, a.record.id, first.id, a.owner))
    page = await receipts.page(db_session, a.vehicle.id, a.record.id, a.owner)
    assert page.total == 0 and page.retained_count == 1 and page.retained_bytes == len(PDF)
    repeated = await upload(db_session, a, body)
    assert repeated.replayed and repeated.receipt == removed.receipt
    restore = ReceiptRestore(request_id=uuid4(), expected_record_version=1, expected_version=2)
    restored = await receipts.mutate(db_session, a.vehicle.id, a.record.id, a.owner, restore, action="restore", receipt_id=first.id)
    assert restored.receipt.version == 3 and restored.receipt.removed_at is None
    assert restored.receipt.created_by_name == first.created_by_name
    history = await receipts.history(db_session, a.vehicle.id, a.record.id, first.id, a.owner, limit=2)
    assert [row.action for row in history.items] == ["restore", "remove"] and history.has_more and history.total == 3
    assert history.items[1].reason == "Wrong file" and history.items[1].snapshot.version == 2
    assert (await receipts.history(db_session, a.vehicle.id, a.record.id, first.id, a.owner, skip=2)).items[0].snapshot == first
    assert (await records.page(db_session, a.vehicle.id, a.owner)).items == [a.record]
    assert counts == [await db_session.scalar(select(func.count(model.id))) for model in (Invoice, Payment, ServiceEvent)]
    assert before == (a.order.status, a.order.total_cost, a.vehicle.mileage, a.vehicle.next_pm_miles, a.vehicle.pm_due_date)


@pytest.mark.asyncio
async def test_duplicate_capacity_stale_and_replays_after_void(db_session):
    a = await setup(db_session)
    body = upload_request()
    saved = await upload(db_session, a, body)
    await error("duplicate_receipt", upload(db_session, a))
    await error("request_id_conflict", upload(db_session, a, body, upload_file(filename="changed.pdf")))
    await error("request_id_conflict", upload(db_session, a, body, upload_file(PDF + b" ")))
    await error("request_id_conflict", upload(db_session, a, body.model_copy(update={"expected_record_version": 2})))
    await error("record_changed", upload(db_session, a, upload_request(expected_record_version=2)))
    remove = ReceiptRemove(request_id=uuid4(), expected_record_version=1, expected_version=1, reason="Wrong")
    await receipts.mutate(db_session, a.vehicle.id, a.record.id, a.owner, remove, action="remove", receipt_id=saved.receipt.id)
    await error("receipt_changed", receipts.mutate(db_session, a.vehicle.id, a.record.id, a.owner, remove.model_copy(update={"request_id": uuid4()}), action="remove", receipt_id=saved.receipt.id))
    await error("receipt_already_removed", receipts.mutate(db_session, a.vehicle.id, a.record.id, a.owner, remove.model_copy(update={"request_id": uuid4(), "expected_version": 2}), action="remove", receipt_id=saved.receipt.id))
    await error("duplicate_removed_receipt", upload(db_session, a))
    for index in range(9):
        await upload(db_session, a, file=upload_file(PDF + b" " * (index + 1)))
    await error("receipt_capacity", upload(db_session, a, file=upload_file(PDF + b" " * 10)))
    await error("duplicate_removed_receipt", upload(db_session, a))
    assert (await upload(db_session, a, body)).replayed
    await records.mutate(db_session, a.vehicle.id, a.owner, ExternalServiceVoid(request_id=uuid4(), expected_version=1, reason="QA"), action="void", record_id=a.record.id)
    repeated = await upload(db_session, a, body)
    assert repeated.record_version == 2 and repeated.record_voided_at and repeated.replayed
    await error("record_voided", upload(db_session, a, upload_request(expected_record_version=2)))
    assert (await receipts.page(db_session, a.vehicle.id, a.record.id, a.owner, include_removed=True)).retained_count == 10
    assert (await receipts.history(db_session, a.vehicle.id, a.record.id, saved.receipt.id, a.owner)).total == 2
    await error("record_voided", receipts.download(db_session, a.vehicle.id, a.record.id, saved.receipt.id, a.owner))
    await records.mutate(db_session, a.vehicle.id, a.owner, ExternalServiceRestore(request_id=uuid4(), expected_version=2), action="restore", record_id=a.record.id)
    assert (await receipts.page(db_session, a.vehicle.id, a.record.id, a.owner, include_removed=True)).items[-1].removed_at


@pytest.mark.asyncio
async def test_tenant_route_actor_and_role_isolation(db_session):
    a, b = await setup(db_session), await setup(db_session)
    saved = await upload(db_session, a)
    other_vehicle = await add_vehicle(db_session, a)
    other_record = (await records.mutate(db_session, a.vehicle.id, a.owner, create())).record
    for vehicle_id, record_id, actor in [(a.vehicle.id, a.record.id, b.owner), (other_vehicle.id, a.record.id, a.owner), (a.vehicle.id, other_record.id, a.owner), (a.vehicle.id, b.record.id, a.owner)]:
        await error("receipt_not_found", receipts.download(db_session, vehicle_id, record_id, saved.receipt.id, actor))
    for role in UserRole:
        actor = SimpleNamespace(id=a.owner.id, tenant_id=a.tenant.id, role=role)
        if role in records.STAFF_ROLES:
            assert (await receipts.page(db_session, a.vehicle.id, a.record.id, actor)).total == 1
        else:
            with pytest.raises(HTTPException) as failure:
                await receipts.page(db_session, a.vehicle.id, a.record.id, actor)
            assert failure.value.status_code == 403
    body = upload_request()
    await upload(db_session, b, body)
    await upload(db_session, a, body, upload_file(PDF + b" "))
    actor = SimpleNamespace(id=uuid4(), tenant_id=a.tenant.id, role=UserRole.RECEPTIONIST)
    await error("request_id_conflict", receipts.mutate(db_session, a.vehicle.id, a.record.id, actor, body, upload=upload_file(PDF + b" ")))
    a.vehicle.deleted_at = datetime.now(UTC)
    await db_session.flush()
    await error("receipt_not_found", receipts.page(db_session, a.vehicle.id, a.record.id, a.owner))


@pytest.mark.parametrize("content,code", [(b"", "receipt_invalid"), (b"hello", "receipt_type"), (b"%PDF-1.7\nmissing end", "receipt_invalid"), (b"%PDF-3.0\n%%EOF", "receipt_invalid"), (b"\x89PNG\r\n\x1a\nbad", "receipt_invalid"), (b"\xff\xd8\xffbad", "receipt_invalid"), (b"a" * (receipts.MAX_FILE_BYTES + 1), "receipt_too_large")])
def test_reject_invalid_content(content, code):
    with pytest.raises(HTTPException) as failure:
        upload_file(content)
    assert failure.value.detail["code"] == code


def test_real_images_filename_and_size_bounds():
    for format, mime, extension in [("PNG", "image/png", ".png"), ("JPEG", "image/jpeg", ".jpg")]:
        content = image_bytes(format)
        file = upload_file(content, "../folder\\ \u202e\x00\x85cafe\u0301\r\n\".exe")
        assert file.content == content and file.media_type == mime and file.filename == 'café"' + extension
        rendered = receipts.download_headers(file.filename)["Content-Disposition"]
        assert "filename*=UTF-8''caf%C3%A9%22" in rendered and "\n" not in rendered and "\r" not in rendered
    assert len(upload_file(filename="x" * 200 + ".exe").filename) == 180
    assert upload_file(filename="../.").filename == "receipt.pdf"
    assert upload_file(filename="\u00a0.  invoice.exe.\u00a0").filename == "invoice.pdf"
    assert upload_file(PDF + b" " * (receipts.MAX_FILE_BYTES - len(PDF))).content
    with pytest.raises(HTTPException):
        upload_file(image_bytes()[:-10])


def test_images_reject_animation_dimensions_and_bombs(monkeypatch):
    first, second = Image.new("RGB", (2, 2), "white"), Image.new("RGB", (2, 2), "black")
    output = BytesIO()
    first.save(output, format="PNG", save_all=True, append_images=[second])
    with pytest.raises(HTTPException):
        upload_file(output.getvalue())
    monkeypatch.setattr(receipts, "MAX_DIMENSION", 2)
    with pytest.raises(HTTPException):
        upload_file(image_bytes())
    monkeypatch.setattr(receipts, "MAX_DIMENSION", 10000)
    monkeypatch.setattr(receipts, "MAX_PIXELS", 5)
    with pytest.raises(HTTPException):
        upload_file(image_bytes())
    monkeypatch.setattr(receipts, "MAX_PIXELS", 20000000)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 4)
    with pytest.raises(HTTPException):
        upload_file(image_bytes())


@pytest.mark.parametrize("width,height", [(10001, 1), (5000, 5000), (100000, 100000)])
def test_real_png_header_cannot_trigger_unbounded_decode(width, height):
    content = image_bytes()
    ihdr = struct.pack(">II", width, height) + content[24:29]
    forged = content[:16] + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)) + content[33:]
    with pytest.raises(HTTPException) as failure:
        upload_file(forged)
    assert failure.value.detail["code"] == "receipt_invalid"


@pytest.mark.asyncio
async def test_event_failure_rolls_back_metadata_and_blob(db_session):
    a = await setup(db_session)
    def reject(mapper, connection, target):
        raise RuntimeError("Injected audit failure")
    event.listen(Event, "before_insert", reject)
    try:
        with pytest.raises(RuntimeError, match="Injected"):
            await upload(db_session, a)
    finally:
        event.remove(Event, "before_insert", reject)
    for model in (Receipt, Blob, Event):
        assert await db_session.scalar(select(func.count(model.id))) == 0


@pytest.mark.asyncio
async def test_actual_http_full_lifecycle(client, db_session):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    a = await setup(db_session)
    assert (await client.get(path(a))).status_code == 401
    app.dependency_overrides[get_current_active_user] = lambda: a.owner
    try:
        body = upload_request()
        saved = await client.post(path(a), headers=headers(body, filename="../café.exe"), content=PDF)
        assert saved.status_code == 201, saved.text
        receipt = saved.json()["receipt"]
        base = f"{path(a)}/{receipt['id']}"
        assert receipt["filename"] == "café.pdf"
        repeated = await client.post(path(a), headers=headers(body, filename="../café.exe"), content=PDF)
        assert repeated.status_code == 200 and repeated.json()["replayed"]
        assert (await client.get(path(a))).json()["items"] == [receipt]
        downloaded = await client.get(base + "/download", headers={"Range": "bytes=0-1", "If-None-Match": "anything"})
        assert downloaded.status_code == 200 and downloaded.content == PDF
        assert downloaded.headers["content-type"] == "application/octet-stream"
        assert downloaded.headers["content-length"] == str(len(PDF))
        assert downloaded.headers["content-disposition"].startswith("attachment;")
        assert downloaded.headers["content-security-policy"] == "sandbox; default-src 'none'"
        assert "etag" not in downloaded.headers and "content-range" not in downloaded.headers
        remove = dict(request_id=str(uuid4()), expected_record_version=1, expected_version=1, reason="Wrong file")
        removed = await client.post(base + "/remove", json=remove)
        assert removed.status_code == 200 and removed.json()["receipt"]["version"] == 2
        assert (await client.get(base + "/download")).json()["detail"]["code"] == "receipt_removed"
        assert (await client.get(path(a))).json()["total"] == 0
        assert (await client.get(path(a) + "?include_removed=true")).json()["total"] == 1
        restored = await client.post(base + "/restore", json=dict(request_id=str(uuid4()), expected_record_version=1, expected_version=2))
        assert restored.status_code == 200 and restored.json()["record_version"] == 1
        assert (await client.get(base + "/history")).json()["total"] == 3
        for response in (saved, removed, downloaded, await client.get(base + "/history?skip=-1")):
            assert response.headers["cache-control"] == "private, no-store, max-age=0"
            assert response.headers["pragma"] == "no-cache" and response.headers["x-content-type-options"] == "nosniff"
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.asyncio
async def test_actual_http_headers_stream_limits_and_idempotency_bypass(client, db_session):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    a = await setup(db_session)
    app.dependency_overrides[get_current_active_user] = lambda: a.owner
    try:
        for key, invalid in [("X-Request-ID", "invalid"), ("X-Request-ID", uuid4().hex), ("X-Expected-Record-Version", "0"), ("X-Expected-Record-Version", "+1"), ("X-Expected-Record-Version", "1.0"), ("X-Expected-Record-Version", "1e1"), ("X-Receipt-Filename", "%ZZ"), ("X-Receipt-Filename", "%ff"), ("X-Receipt-Filename", "a" * 2049)]:
            response = await client.post(path(a), headers=headers(**{key: invalid}), content=PDF)
            assert response.status_code == 422, response.text
        for key in ("X-Request-ID", "X-Expected-Record-Version", "X-Receipt-Filename"):
            values = headers()
            values.pop(key)
            assert (await client.post(path(a), headers=values, content=PDF)).status_code == 422
            values = list(headers().items()) + [(key, "duplicate")]
            assert (await client.post(path(a), headers=values, content=PDF)).status_code == 422
        assert (await client.post(path(a), headers=headers(**{"Content-Type": "multipart/form-data; boundary=x"}), content=PDF)).status_code == 415
        for length in (None, "1", str(receipts.MAX_FILE_BYTES + 1)):
            async def chunks():
                yield b"x" * receipts.MAX_FILE_BYTES
                yield b"y"
            extra = {} if length is None else {"Content-Length": length}
            response = await client.post(path(a), headers=headers(**extra), content=chunks())
            assert response.status_code == 413 and response.json()["detail"]["code"] == "receipt_too_large"
            assert response.headers["cache-control"] == "private, no-store, max-age=0"
        # Generic Redis idempotency must neither buffer nor cache private files.
        body = upload_request()
        values = headers(body, **{"Idempotency-Key": "x" * 32})
        assert (await client.post(path(a), headers=values, content=PDF)).status_code == 201
        a.owner.role = UserRole.CUSTOMER
        denied = await client.post(path(a), headers=values, content=PDF)
        assert denied.status_code == 403
        assert "x-idempotency-replayed" not in denied.headers
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [None, *list(UserRole)])
async def test_upload_authorizes_before_body_receive(db_session, role):
    from fastapi import FastAPI
    from app.api.v1.endpoints.external_services import router
    from app.core.dependencies import get_current_active_user
    from app.db.session import get_db
    from app.middleware.idempotency import IdempotencyMiddleware
    from app.middleware.request_size import RequestBodyLimitMiddleware
    a = await setup(db_session)
    mini = FastAPI()
    mini.include_router(router, prefix="/api/v1/vehicles")
    if role is not None:
        mini.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id=a.owner.id, tenant_id=a.tenant.id, role=role)
    mini.dependency_overrides[get_db] = lambda: db_session
    mini.add_middleware(IdempotencyMiddleware)
    mini.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=10000000)
    consumed, sent = [], []
    async def receive():
        consumed.append(True)
        return {"type": "http.request", "body": PDF, "more_body": False}
    async def send(message):
        sent.append(message)
    metadata = headers(**{"Idempotency-Key": "x" * 32, "Content-Length": "999999999"})
    await mini({"type": "http", "http_version": "1.1", "asgi": {"version": "3.0", "spec_version": "2.4"}, "method": "POST", "path": path(a), "raw_path": path(a).encode(), "query_string": b"", "scheme": "http", "server": ("test", 80), "client": ("127.0.0.1", 123), "headers": [(k.lower().encode(), v.encode()) for k, v in metadata.items()]}, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    assert not consumed
    assert status == (401 if role is None else 413 if role in records.STAFF_ROLES else 403)


def test_receipt_middleware_boundary_is_exact():
    from app.middleware.receipt_paths import is_receipt_path
    base = f"/api/v1/vehicles/{uuid4()}/external-services/{uuid4()}/receipts"
    assert is_receipt_path(base) and is_receipt_path(base + f"/{uuid4()}/remove")
    assert is_receipt_path(f"/api/v1/vehicles/{uuid4().hex}/external-services/urn:uuid:{uuid4()}/receipts")
    for wrong in (base.replace("/receipts", ""), base + "/unknown", "/api/v1/receipts", base.replace("/external-services/", "/other/")):
        assert not is_receipt_path(wrong)


@pytest.mark.asyncio
async def test_unexpected_upload_errors_are_private_and_do_not_log_bytes(client, db_session, monkeypatch):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    from app.api.v1.endpoints import external_service_receipts as routes
    a = await setup(db_session)
    app.dependency_overrides[get_current_active_user] = lambda: a.owner
    messages = []
    monkeypatch.setattr(routes.logger, "error", lambda *args, **kwargs: messages.append((args, kwargs)))
    def fail_validation(*args):
        raise RuntimeError("PRIVATE RECEIPT BODY and filename must not reach diagnostics")
    monkeypatch.setattr(receipts, "validate_content", fail_validation)
    try:
        response = await client.post(path(a), headers=headers(), content=PDF)
        assert response.status_code == 500 and "PRIVATE RECEIPT" not in response.text
        assert response.headers["cache-control"] == "private, no-store, max-age=0"
        assert messages and messages[0][1]["error_type"] == "RuntimeError"
        assert "PRIVATE RECEIPT" not in str(messages) and "exc_info" not in messages[0][1]
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
