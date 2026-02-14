from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.logging import get_logger
from app.services.messaging_service import (
    handle_inbound_sms,
    process_twilio_status_callback,
    validate_twilio_signature,
)

router = APIRouter()
logger = get_logger(__name__)


def _coerce_form_values(form_data) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in form_data.multi_items():
        normalized[str(key)] = str(value)
    return normalized


def _candidate_signature_urls(request: Request) -> list[str]:
    """
    Build possible request URLs for Twilio signature verification.

    Behind reverse proxies, Starlette can expose an internal `http://` URL even
    when the public URL is `https://`. Twilio signs the public URL, so we check
    both raw and forwarded variants.
    """
    candidates: list[str] = []
    raw_url = str(request.url)
    if raw_url:
        candidates.append(raw_url)

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip()
    forwarded_host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",", 1)[0].strip()
    if forwarded_proto and forwarded_host:
        path = request.url.path
        query = request.url.query
        forwarded_url = f"{forwarded_proto}://{forwarded_host}{path}"
        if query:
            forwarded_url = f"{forwarded_url}?{query}"
        if forwarded_url not in candidates:
            candidates.append(forwarded_url)

    if raw_url.startswith("http://"):
        https_url = "https://" + raw_url[len("http://") :]
        if https_url not in candidates:
            candidates.append(https_url)

    return candidates


def _has_valid_signature(request: Request, values: dict[str, str], signature: Optional[str]) -> bool:
    for candidate_url in _candidate_signature_urls(request):
        if validate_twilio_signature(candidate_url, values, signature):
            return True
    return False


@router.post("/sms/inbound")
async def twilio_inbound_sms(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    values = _coerce_form_values(form_data)
    signature = request.headers.get("x-twilio-signature")
    if not _has_valid_signature(request, values, signature):
        logger.warning(
            "twilio_signature_invalid",
            endpoint="inbound",
            request_url=str(request.url),
            forwarded_proto=request.headers.get("x-forwarded-proto"),
            forwarded_host=request.headers.get("x-forwarded-host"),
            host=request.headers.get("host"),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Twilio signature")

    await handle_inbound_sms(
        db=db,
        to_number=values.get("To", ""),
        from_number=values.get("From", ""),
        body=values.get("Body", ""),
        twilio_message_sid=values.get("MessageSid"),
    )
    return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/sms/status")
async def twilio_sms_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    values = _coerce_form_values(form_data)
    signature = request.headers.get("x-twilio-signature")
    if not _has_valid_signature(request, values, signature):
        logger.warning(
            "twilio_signature_invalid",
            endpoint="status",
            request_url=str(request.url),
            forwarded_proto=request.headers.get("x-forwarded-proto"),
            forwarded_host=request.headers.get("x-forwarded-host"),
            host=request.headers.get("host"),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Twilio signature")

    await process_twilio_status_callback(
        db=db,
        message_sid=values.get("MessageSid"),
        message_status=values.get("MessageStatus"),
        error_code=values.get("ErrorCode"),
        error_message=values.get("ErrorMessage"),
    )
    return {"status": "success"}
