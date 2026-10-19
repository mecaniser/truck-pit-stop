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


@router.post('/{anchor_binding_id}/company/{event_kind}')
async def company_callback(anchor_binding_id: UUID, event_kind: str, request: Request,
                           signature: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    """One company callback resolves one configured receiving/sending number."""
    from sqlalchemy import select
    from app.db.models.tenant import Tenant
    if event_kind not in {'received', 'sent'}:
        raise HTTPException(404, 'Unknown event')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(413, 'Payload too large')
    anchor = await db.get(CallRailNumberBinding, anchor_binding_id)
    if not anchor:
        raise HTTPException(404, 'Unknown CallRail binding')
    try:
        signing_key = service.secret(anchor.signing_secret_ref)
    except HTTPException:
        raise HTTPException(503, 'Callback verification unavailable') from None
    if not service.valid_signature(bytes(raw), signature, signing_key):
        raise HTTPException(403, 'Invalid signature')
    async def quarantine(payload, reason):
        await db.scalar(select(CallRailNumberBinding).where(CallRailNumberBinding.id == anchor.id).with_for_update())
        result = await service._quarantine(db, anchor, payload, reason)
        await db.commit()
        return result
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return await quarantine({'invalid_json_digest': __import__('hashlib').sha256(raw).hexdigest()}, 'invalid_json')
    if not isinstance(payload, dict):
        return await quarantine({'invalid_payload_type': type(payload).__name__}, 'invalid_payload')
    tenant = await db.get(Tenant, anchor.tenant_id)
    if (not anchor.enabled or anchor.deleted_at is not None or not tenant or not tenant.is_active
        or tenant.deleted_at is not None or not tenant.messaging_enabled):
        return await quarantine(payload, 'binding_disabled')
    if payload.get('company_resource_id') != anchor.company_id:
        return await quarantine(payload, 'company_mismatch')
    if any(str(payload[key]) != anchor.account_id for key in ('account_id', 'account_resource_id') if key in payload):
        return await quarantine(payload, 'account_mismatch')
    local = service._phone(payload.get('destination_number' if event_kind == 'received' else 'source_number'))
    candidates = (await db.scalars(select(CallRailNumberBinding).where(
        CallRailNumberBinding.tenant_id == anchor.tenant_id, CallRailNumberBinding.account_id == anchor.account_id,
        CallRailNumberBinding.company_id == anchor.company_id, CallRailNumberBinding.sender_phone == local,
        CallRailNumberBinding.enabled.is_(True), CallRailNumberBinding.deleted_at.is_(None)))).all()
    if len(candidates) != 1:
        return await quarantine(payload, 'unrecognized_company_number')
    binding = candidates[0]
    if binding.signing_secret_ref != anchor.signing_secret_ref:
        return await quarantine(payload, 'signing_reference_mismatch')
    result = await service.apply_event(db, binding.id, payload, event_kind)
    await db.commit()
    return result
