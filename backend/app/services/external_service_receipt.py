"""Bounded private receipt storage with parent locks and durable replay."""
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import json
import re
import unicodedata
from urllib.parse import quote
from uuid import uuid4
import warnings

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError

from app.db.models.external_service import ExternalServiceRecord as Record
from app.db.models.external_service_receipt import ExternalServiceReceipt as Receipt, ExternalServiceReceiptBlob as Blob, ExternalServiceReceiptEvent as Event
from app.db.models.vehicle import Vehicle
from app.schemas.external_service_receipt import ReceiptHistoryItem, ReceiptHistoryPage, ReceiptItem, ReceiptMutation, ReceiptPage
from app.services import external_service
from app.services.service_checklist import actor_name

MAX_FILE_BYTES = 5242880
MAX_FILES = 10
MAX_TOTAL_BYTES = 52428800
MAX_PIXELS = 20000000
MAX_DIMENSION = 10000
PRIVATE_HEADERS = {"Cache-Control": "private, no-store, max-age=0", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff"}
ERRORS = {
    "receipt_not_found": (404, "Vehicle, service record or receipt not found."),
    "request_id_conflict": (409, "This save ID has already been used. Refresh and try again."),
    "record_changed": (409, "This service record has changed. Refresh it before saving."),
    "receipt_changed": (409, "This receipt has changed. Refresh it before saving."),
    "record_voided": (409, "Restore this service record before using its receipts."),
    "receipt_removed": (409, "Restore this receipt before downloading it."),
    "receipt_already_removed": (409, "This receipt is already removed."),
    "receipt_already_active": (409, "This receipt is already active."),
    "duplicate_receipt": (409, "This file is already attached to this service record."),
    "duplicate_removed_receipt": (409, "This file is retained under Show removed. Restore it there."),
    "receipt_capacity": (409, "This service record has reached its retained receipt limit. Removed files still count."),
    "receipt_too_large": (413, "Use a file up to 5 MiB."),
    "receipt_type": (415, "Use a PDF, JPEG or PNG receipt."),
    "receipt_invalid": (422, "This receipt file is empty, invalid or cannot be safely processed."),
}


def fail(code, **extra):
    status, message = ERRORS[code]
    raise HTTPException(status, {"code": code, "message": message, **extra}, headers=PRIVATE_HEADERS)


@dataclass(frozen=True, repr=False)
class ValidatedReceipt:
    content: bytes
    filename: str
    media_type: str
    content_sha256: str


def normalize_filename(filename, extension):
    filename = unicodedata.normalize("NFC", filename).replace("\\", "/").rsplit("/", 1)[-1]
    filename = "".join(char for char in filename if not (ord(char) < 32 or 127 <= ord(char) <= 159 or char in "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))
    filename = re.sub(r"^[\s.]+|[\s.]+$", "", filename)
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    stem = re.sub(r"^[\s.]+|[\s.]+$", "", stem) or "receipt"
    return stem[:180 - len(extension)].rstrip(" .") + extension


def validate_content(content: bytes, filename: str) -> ValidatedReceipt:
    """Run in the worker pool: never render PDFs or decode unbounded images."""
    if len(content) > MAX_FILE_BYTES:
        fail("receipt_too_large")
    if not content:
        fail("receipt_invalid")
    if content.startswith(b"%PDF-"):
        if not re.match(rb"%PDF-(?:1\.[0-7]|2\.0)(?:[\t\r\n ])", content) or not content.rstrip(b" \t\r\n\f\v").endswith(b"%%EOF"):
            fail("receipt_invalid")
        media_type, extension = "application/pdf", ".pdf"
    elif content.startswith(b"\x89PNG\r\n\x1a\n") or content.startswith(b"\xff\xd8\xff"):
        expected = "PNG" if content.startswith(b"\x89PNG") else "JPEG"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as picture:
                    if picture.format != expected or picture.width > MAX_DIMENSION or picture.height > MAX_DIMENSION or picture.width * picture.height > MAX_PIXELS or getattr(picture, "n_frames", 1) != 1:
                        fail("receipt_invalid")
                    picture.verify()
                with Image.open(BytesIO(content)) as picture:
                    picture.load()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError):
            fail("receipt_invalid")
        media_type, extension = ("image/png", ".png") if expected == "PNG" else ("image/jpeg", ".jpg")
    else:
        fail("receipt_type")
    return ValidatedReceipt(content, normalize_filename(filename, extension), media_type, sha256(content).hexdigest())


def download_headers(filename):
    fallback = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:180] or "receipt"
    return {**PRIVATE_HEADERS,
            "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}",
            "Content-Security-Policy": "sandbox; default-src 'none'", "Referrer-Policy": "no-referrer"}


async def load_parent(db, vehicle_id, record_id, actor, *, write=False):
    try:
        await external_service.load_vehicle(db, vehicle_id, actor, write=write)
        return await external_service.load_record(db, vehicle_id, record_id, actor, write=write)
    except HTTPException as error:
        if error.status_code == 404:
            fail("receipt_not_found")
        raise


async def load_receipt(db, record_id, receipt_id, actor, *, write=False):
    query = select(Receipt).where(Receipt.tenant_id == actor.tenant_id, Receipt.record_id == record_id, Receipt.id == receipt_id).execution_options(populate_existing=True)
    if write:
        query = query.with_for_update(of=Receipt)
    receipt = await db.scalar(query)
    if receipt is None:
        fail("receipt_not_found")
    return receipt


def item(receipt, record):
    return ReceiptItem(**{key: getattr(receipt, key) for key in ReceiptItem.model_fields if key != "vehicle_id"}, vehicle_id=record.vehicle_id)


def envelope(receipt, record, *, replayed=False):
    return ReceiptMutation(receipt=item(receipt, record), replayed=replayed, record_version=record.version, record_voided_at=record.voided_at)


async def page(db, vehicle_id, record_id, actor, *, include_removed=False):
    record = await load_parent(db, vehicle_id, record_id, actor)
    receipts = (await db.scalars(select(Receipt).where(Receipt.tenant_id == actor.tenant_id, Receipt.record_id == record_id).order_by(Receipt.created_at.desc(), Receipt.id.desc()))).all()
    visible = [item(row, record) for row in receipts if include_removed or row.removed_at is None]
    return ReceiptPage(items=visible, total=len(visible), retained_count=len(receipts), retained_bytes=sum(row.size_bytes for row in receipts), record_version=record.version, record_voided_at=record.voided_at)


async def history(db, vehicle_id, record_id, receipt_id, actor, *, skip=0, limit=10):
    await load_parent(db, vehicle_id, record_id, actor)
    await load_receipt(db, record_id, receipt_id, actor)
    conditions = (Event.tenant_id == actor.tenant_id, Event.record_id == record_id, Event.receipt_id == receipt_id)
    total = await db.scalar(select(func.count(Event.id)).where(*conditions))
    events = (await db.scalars(select(Event).where(*conditions).order_by(Event.version.desc()).offset(skip).limit(limit))).all()
    return ReceiptHistoryPage(items=[ReceiptHistoryItem.model_validate(row) for row in events], total=total, has_more=skip + len(events) < total)


async def download(db, vehicle_id, record_id, receipt_id, actor):
    # These checks provide useful lifecycle errors, but never authorize the blob
    # independently. Its single SELECT repeats the entire access/lifecycle chain.
    record = await load_parent(db, vehicle_id, record_id, actor)
    receipt = await load_receipt(db, record_id, receipt_id, actor)
    if record.voided_at is not None:
        fail("record_voided")
    if receipt.removed_at is not None:
        fail("receipt_removed")
    row = (await db.execute(select(Blob.content, Receipt.filename, Receipt.size_bytes)
        .join(Receipt, and_(Receipt.id == Blob.receipt_id, Receipt.tenant_id == Blob.tenant_id))
        .join(Record, and_(Record.id == Receipt.record_id, Record.tenant_id == Receipt.tenant_id))
        .join(Vehicle, and_(Vehicle.id == Record.vehicle_id, Vehicle.tenant_id == Record.tenant_id))
        .where(Blob.tenant_id == actor.tenant_id, Receipt.id == receipt_id, Record.id == record_id, Vehicle.id == vehicle_id,
               Vehicle.deleted_at.is_(None), Record.deleted_at.is_(None), Record.voided_at.is_(None), Receipt.removed_at.is_(None)))).one_or_none()
    if row is None:
        fail("receipt_not_found")
    content, filename, size_bytes = row
    if len(content) != size_bytes:
        raise RuntimeError("Receipt storage size mismatch")
    return content, download_headers(filename)


def request_hash(action, vehicle_id, record_id, receipt_id, body, upload):
    payload = {"action": action, "vehicle_id": str(vehicle_id), "record_id": str(record_id), "receipt_id": str(receipt_id) if receipt_id else None,
               "body": body.model_dump(mode="json", exclude={"request_id"})}
    if upload:
        payload["upload"] = {"filename": upload.filename, "media_type": upload.media_type, "size_bytes": len(upload.content), "content_sha256": upload.content_sha256}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def replay(db, record, receipt_id, actor, action, body, digest):
    event = await db.scalar(select(Event).where(Event.tenant_id == actor.tenant_id, Event.request_id == body.request_id))
    if event is None:
        return None
    if event.actor_user_id != actor.id or event.action != action or event.request_hash != digest or event.record_id != record.id or (receipt_id and event.receipt_id != receipt_id):
        fail("request_id_conflict")
    receipt = await load_receipt(db, record.id, event.receipt_id, actor, write=True)
    return envelope(receipt, record, replayed=True)


async def mutate(db, vehicle_id, record_id, actor, body, *, action="upload", receipt_id=None, upload=None):
    # Global ordering matches DB119 and merge: vehicle, record, receipt.
    record = await load_parent(db, vehicle_id, record_id, actor, write=True)
    receipt = await load_receipt(db, record_id, receipt_id, actor, write=True) if receipt_id else None
    digest = request_hash(action, vehicle_id, record_id, receipt_id, body, upload)
    repeated = await replay(db, record, receipt_id, actor, action, body, digest)
    if repeated is not None:
        return repeated
    if record.version != body.expected_record_version:
        fail("record_changed")
    if record.voided_at is not None:
        fail("record_voided")
    if receipt is not None:
        if receipt.version != body.expected_version:
            fail("receipt_changed")
        if action == "remove" and receipt.removed_at is not None:
            fail("receipt_already_removed")
        if action == "restore" and receipt.removed_at is None:
            fail("receipt_already_active")
    if action == "upload":
        if upload is None or receipt_id is not None:
            raise ValueError("Upload requires validated bytes and no receipt ID")
        duplicate = await db.scalar(select(Receipt).where(Receipt.tenant_id == actor.tenant_id, Receipt.record_id == record_id, Receipt.content_sha256 == upload.content_sha256))
        if duplicate:
            fail("duplicate_removed_receipt" if duplicate.removed_at else "duplicate_receipt", receipt_id=str(duplicate.id))
        count, size = (await db.execute(select(func.count(Receipt.id), func.coalesce(func.sum(Receipt.size_bytes), 0)).where(Receipt.tenant_id == actor.tenant_id, Receipt.record_id == record_id))).one()
        if count >= MAX_FILES or size + len(upload.content) > MAX_TOTAL_BYTES:
            fail("receipt_capacity")
    elif action not in {"remove", "restore"} or receipt is None:
        raise ValueError("Unknown receipt action or missing target")
    now, name = datetime.now(UTC), actor_name(actor)
    try:
        async with db.begin_nested():
            if action == "upload":
                receipt = Receipt(id=uuid4(), tenant_id=actor.tenant_id, record_id=record_id, uploaded_vehicle_id=vehicle_id,
                    filename=upload.filename, media_type=upload.media_type, size_bytes=len(upload.content), content_sha256=upload.content_sha256,
                    version=1, created_by_user_id=actor.id, created_by_name=name, created_at=now, updated_at=now)
                db.add(receipt)
            else:
                receipt.version += 1
                receipt.removed_at = now if action == "remove" else None
            receipt.updated_by_user_id, receipt.updated_by_name, receipt.updated_at = actor.id, name, now
            await db.flush()
            if action == "upload":
                db.add(Blob(id=uuid4(), tenant_id=actor.tenant_id, receipt_id=receipt.id, content=upload.content, created_at=now, updated_at=now))
            db.add(Event(id=uuid4(), tenant_id=actor.tenant_id, record_id=record_id, receipt_id=receipt.id, request_id=body.request_id,
                         request_hash=digest, version=receipt.version, action=action, actor_user_id=actor.id, actor_name=name,
                         reason=getattr(body, "reason", None), snapshot=item(receipt, record).model_dump(mode="json"), created_at=now, updated_at=now))
            await db.flush()
    except IntegrityError:
        # A competing request ID on another locked vehicle can win concurrently.
        # Only resolve the known event collision; unrelated integrity faults fail.
        repeated = await replay(db, record, receipt_id, actor, action, body, digest)
        if repeated is not None:
            return repeated
        raise
    return envelope(receipt, record)
