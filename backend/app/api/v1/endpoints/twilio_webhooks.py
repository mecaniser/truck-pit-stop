from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.services.messaging_service import (
    handle_inbound_sms,
    process_twilio_status_callback,
    validate_twilio_signature,
)

router = APIRouter()


def _coerce_form_values(form_data) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in form_data.multi_items():
        normalized[str(key)] = str(value)
    return normalized


@router.post("/sms/inbound")
async def twilio_inbound_sms(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    values = _coerce_form_values(form_data)
    signature = request.headers.get("x-twilio-signature")
    if not validate_twilio_signature(str(request.url), values, signature):
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
    if not validate_twilio_signature(str(request.url), values, signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Twilio signature")

    await process_twilio_status_callback(
        db=db,
        message_sid=values.get("MessageSid"),
        message_status=values.get("MessageStatus"),
        error_code=values.get("ErrorCode"),
        error_message=values.get("ErrorMessage"),
    )
    return {"status": "success"}
