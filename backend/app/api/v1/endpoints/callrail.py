"""Signed CallRail callbacks; no settings, forwarding or provider provisioning writes."""
import json
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db
from app.db.models.callrail import CallRailNumberBinding
from app.services import callrail_service as service

router = APIRouter()


@router.post('/{binding_id}/{event_kind}')
async def callback(binding_id: UUID, event_kind: str, request: Request,
                   signature: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    if event_kind not in {'received', 'sent'}:
        raise HTTPException(404, 'Unknown event')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(413, 'Payload too large')
    binding = await db.get(CallRailNumberBinding, binding_id)
    if not binding:
        raise HTTPException(404, 'Unknown CallRail binding')
    try:
        signing_key = service.secret(binding.signing_secret_ref)
    except HTTPException:
        raise HTTPException(503, 'Callback verification unavailable') from None
    if not service.valid_signature(bytes(raw), signature, signing_key):
        raise HTTPException(403, 'Invalid signature')
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, 'Invalid JSON') from None
    result = await service.apply_event(db, binding_id, payload, event_kind)
    await db.commit()
    return result
