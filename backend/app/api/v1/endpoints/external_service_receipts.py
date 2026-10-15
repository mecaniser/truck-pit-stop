"""Authenticated, bounded binary uploads and forced private downloads."""
import re
from urllib.parse import unquote_to_bytes
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from app.core.dependencies import get_current_active_user
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.external_service_receipt import ReceiptHistoryPage, ReceiptMutation, ReceiptPage, ReceiptRemove, ReceiptRestore, ReceiptUpload
from app.services import external_service_receipt as service

logger = get_logger(__name__)


class PrivateReceiptRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request):
            try:
                response = await handler(request)
            except StarletteHTTPException as error:
                response = await http_exception_handler(request, error)
            except RequestValidationError as error:
                response = await request_validation_exception_handler(request, error)
            except Exception as error:
                # Do not pass SQL/blob/parser exception text or traceback into
                # global diagnostics. DB dependencies still close/roll back.
                logger.error("private_receipt_request_failed", error_type=type(error).__name__, correlation_id=getattr(request.state, "correlation_id", None))
                response = JSONResponse(status_code=500, content={"detail": "Receipt request failed. Please try again."})
            response.headers.update(service.PRIVATE_HEADERS)
            return response

        return private_handler


router = APIRouter(prefix="/{record_id}/receipts", route_class=PrivateReceiptRoute)


def upload_metadata(request):
    values = {}
    for key in ("x-request-id", "x-expected-record-version", "x-receipt-filename"):
        entries = request.headers.getlist(key)
        if len(entries) != 1:
            raise HTTPException(422, "Invalid receipt upload headers")
        values[key] = entries[0]
    request_id = values["x-request-id"]
    version = values["x-expected-record-version"]
    filename = values["x-receipt-filename"]
    try:
        identity = UUID(request_id)
        if str(identity) != request_id or not re.fullmatch(r"[1-9][0-9]{0,99}", version):
            raise ValueError
        if len(filename) > 2048 or not filename.isascii() or re.search(r"%(?![0-9a-fA-F]{2})", filename):
            raise ValueError
        filename = unquote_to_bytes(filename).decode("utf-8", errors="strict")
    except (ValueError, UnicodeError):
        raise HTTPException(422, "Invalid receipt upload headers") from None
    return ReceiptUpload(request_id=identity, expected_record_version=int(version)), filename


async def read_bounded_upload(request):
    declared = request.headers.getlist("content-type")
    if len(declared) != 1 or declared[0].lower().strip() != "application/octet-stream":
        service.fail("receipt_type")
    length = request.headers.get("content-length")
    if length and length.isascii() and length.isdecimal() and (len(length) > 10 or int(length) > service.MAX_FILE_BYTES):
        service.fail("receipt_too_large")
    content = bytearray()
    try:
        async for chunk in request.stream():
            if len(content) + len(chunk) > service.MAX_FILE_BYTES:
                service.fail("receipt_too_large")
            content.extend(chunk)
        return bytes(content)
    except ClientDisconnect:
        raise HTTPException(400, "Receipt upload disconnected") from None
    finally:
        content.clear()


@router.get("", response_model=ReceiptPage)
async def list_receipts(vehicle_id: UUID, record_id: UUID, include_removed: bool = False,
                        db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return await service.page(db, vehicle_id, record_id, current_user, include_removed=include_removed)


@router.post("", response_model=ReceiptMutation, status_code=201)
async def upload_receipt(vehicle_id: UUID, record_id: UUID, request: Request, response: Response,
                         db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    # No Body/File/form dependencies: role and parent authorization precede any
    # receive() call. Revalidation with write locks occurs after bounded parsing.
    await service.load_parent(db, vehicle_id, record_id, current_user)
    body, filename = upload_metadata(request)
    content = await read_bounded_upload(request)
    upload = await run_in_threadpool(service.validate_content, content, filename)
    result = await service.mutate(db, vehicle_id, record_id, current_user, body, upload=upload)
    await db.commit()
    if result.replayed:
        response.status_code = 200
    return result


@router.post("/{receipt_id}/remove", response_model=ReceiptMutation)
async def remove_receipt(vehicle_id: UUID, record_id: UUID, receipt_id: UUID, body: ReceiptRemove,
                         db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    result = await service.mutate(db, vehicle_id, record_id, current_user, body, action="remove", receipt_id=receipt_id)
    await db.commit()
    return result


@router.post("/{receipt_id}/restore", response_model=ReceiptMutation)
async def restore_receipt(vehicle_id: UUID, record_id: UUID, receipt_id: UUID, body: ReceiptRestore,
                          db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    result = await service.mutate(db, vehicle_id, record_id, current_user, body, action="restore", receipt_id=receipt_id)
    await db.commit()
    return result


@router.get("/{receipt_id}/history", response_model=ReceiptHistoryPage)
async def receipt_history(vehicle_id: UUID, record_id: UUID, receipt_id: UUID, skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100),
                           db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return await service.history(db, vehicle_id, record_id, receipt_id, current_user, skip=skip, limit=limit)


@router.get("/{receipt_id}/download")
async def download_receipt(vehicle_id: UUID, record_id: UUID, receipt_id: UUID,
                           db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    content, headers = await service.download(db, vehicle_id, record_id, receipt_id, current_user)
    return Response(content=content, media_type="application/octet-stream", headers=headers)
