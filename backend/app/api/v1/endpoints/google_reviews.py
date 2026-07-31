"""Tenant-scoped Google Business Profile review inbox and OAuth endpoints."""
from __future__ import annotations
import base64, hashlib, json
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_db
from app.db.models.google_review import GoogleBusinessConnection, GoogleBusinessOAuthState, GoogleReview, GoogleReviewSettings, GoogleReviewStatus
from app.db.models.user import User, UserRole
from app.services.google_reviews_service import audit, authorization_url, exchange_code, generate_draft, is_configured, list_locations, publish_reply, sync_connection

router = APIRouter()

class LocationSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=1, max_length=255)
    location_id: str = Field(min_length=1, max_length=255)
    location_name: str = Field(min_length=1, max_length=500)
class ReviewSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand_voice_prompt: str = Field(default="", max_length=4000)
    reply_policy: str = Field(default="", max_length=4000)
    auto_publish_five_star: bool = False
    alert_recipients: list[str] = Field(default_factory=list, max_length=20)
class ReplyEdit(BaseModel):
    reply_text: str = Field(min_length=1, max_length=600)

def _admin(user: User):
    if user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN) or not user.tenant_id:
        raise HTTPException(403, "Only shop administrators can manage Google Reviews")

def _staff(user: User):
    if user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST) or not user.tenant_id:
        raise HTTPException(403, "You do not have access to Google Reviews")

async def _connection(db, tenant_id):
    return (await db.execute(select(GoogleBusinessConnection).where(GoogleBusinessConnection.tenant_id == tenant_id))).scalar_one_or_none()
async def _review(db, tenant_id, review_id):
    item = (await db.execute(select(GoogleReview).where(GoogleReview.id == review_id, GoogleReview.tenant_id == tenant_id))).scalar_one_or_none()
    if not item: raise HTTPException(404, "Review not found")
    return item
def _serialize(item: GoogleReview):
    return {"id": item.id, "reviewer_name": item.reviewer_name, "rating": item.rating, "review_text": item.review_text, "review_created_at": item.review_created_at, "review_updated_at": item.review_updated_at, "ai_draft": item.ai_draft, "ai_model": item.ai_model, "reply_text": item.reply_text, "status": item.status, "requires_approval": item.requires_approval, "approved_at": item.approved_at, "published_at": item.published_at, "publish_failure_reason": item.publish_failure_reason, "publish_retry_count": item.publish_retry_count}

@router.get("/connection/status")
async def connection_status(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _admin(current_user); c = await _connection(db, current_user.tenant_id)
    return {"configured": is_configured(), "is_connected": bool(c and c.status == "connected"), "status": c.status if c else "disconnected", "location_name": c.location_name if c else None, "last_sync_at": c.last_sync_at if c else None, "last_sync_error": c.last_sync_error if c else None, "token_health": "reconnect_required" if c and c.last_token_refresh_error else "healthy" if c and c.status == "connected" else "not_connected"}

@router.post("/connection/authorize")
async def authorize(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _admin(current_user)
    if not is_configured(): raise HTTPException(503, "Google Business Profile integration is not configured")
    state = token_urlsafe(32)
    db.add(GoogleBusinessOAuthState(state_hash=hashlib.sha256(state.encode()).hexdigest(), tenant_id=current_user.tenant_id, initiated_by_user_id=current_user.id, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)))
    await db.commit()
    return {"url": authorization_url(state)}

@router.get("/connection/callback")
async def callback(code: str = Query(...), state: str = Query(...), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(GoogleBusinessOAuthState).where(GoogleBusinessOAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest()))).scalar_one_or_none()
    if not row or row.consumed_at or row.expires_at < datetime.now(timezone.utc):
        return RedirectResponse(f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/garage/reviews/settings?google-reviews=error", 303)
    row.consumed_at = datetime.now(timezone.utc)
    c = await _connection(db, row.tenant_id)
    if not c: c = GoogleBusinessConnection(tenant_id=row.tenant_id); db.add(c); await db.flush()
    try:
        await exchange_code(db, c, code); await audit(db, row.tenant_id, "connection_authorized", actor_user_id=row.initiated_by_user_id); await db.commit()
        result = "select-location"
    except Exception:
        await db.rollback(); result = "error"
    return RedirectResponse(f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/garage/reviews/settings?google-reviews={result}", 303)

@router.get("/connection/locations")
async def locations(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _admin(current_user); c = await _connection(db, current_user.tenant_id)
    if not c: raise HTTPException(409, "Connect Google before selecting a location")
    try: return await list_locations(db, c)
    except Exception: raise HTTPException(409, "Could not load Google locations; reconnect and try again")

@router.put("/connection/location")
async def select_location(payload: LocationSelection, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _admin(current_user); c = await _connection(db, current_user.tenant_id)
    if not c or c.status != "location_selection_required": raise HTTPException(409, "Google location selection is not pending")
    c.google_account_id, c.location_id, c.location_name, c.status, c.connected_at = payload.account_id, payload.location_id, payload.location_name, "connected", datetime.now(timezone.utc)
    await audit(db, current_user.tenant_id, "location_selected", actor_user_id=current_user.id, metadata={"location_id": payload.location_id})
    await db.commit(); return {"ok": True}

@router.delete("/connection")
async def disconnect(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _admin(current_user); c = await _connection(db, current_user.tenant_id)
    if c:
        c.status, c.encrypted_access_token, c.encrypted_refresh_token, c.google_account_id, c.location_id, c.location_name, c.disconnected_at = "disconnected", None, None, None, None, None, datetime.now(timezone.utc)
        await audit(db, current_user.tenant_id, "disconnected", actor_user_id=current_user.id); await db.commit()
    return {"ok": True}

@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _admin(current_user); item = (await db.execute(select(GoogleReviewSettings).where(GoogleReviewSettings.tenant_id == current_user.tenant_id))).scalar_one_or_none()
    return {"brand_voice_prompt": item.brand_voice_prompt if item else "", "reply_policy": item.reply_policy if item else "", "auto_publish_five_star": bool(item and item.auto_publish_five_star), "alert_recipients": item.alert_recipients if item else []}
@router.put("/settings")
async def save_settings(payload: ReviewSettingsPayload, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _admin(current_user); item = (await db.execute(select(GoogleReviewSettings).where(GoogleReviewSettings.tenant_id == current_user.tenant_id))).scalar_one_or_none()
    if not item: item = GoogleReviewSettings(tenant_id=current_user.tenant_id); db.add(item)
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    await audit(db, current_user.tenant_id, "settings_updated", actor_user_id=current_user.id); await db.commit(); return await get_settings(db, current_user)

@router.get("")
async def inbox(status_filter: Optional[str] = Query(None, alias="status"), rating: Optional[int] = Query(None, ge=1, le=5), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _staff(current_user); query = select(GoogleReview).where(GoogleReview.tenant_id == current_user.tenant_id)
    if status_filter == "unread": query = query.where(GoogleReview.status == GoogleReviewStatus.NEW.value)
    elif status_filter: query = query.where(GoogleReview.status == status_filter)
    if rating: query = query.where(GoogleReview.rating == rating)
    rows = (await db.execute(query.order_by(GoogleReview.review_created_at.desc()).limit(200))).scalars().all()
    return [_serialize(r) for r in rows]
@router.get("/metrics")
async def metrics(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _staff(current_user); tid = current_user.tenant_id
    avg = (await db.execute(select(func.avg(GoogleReview.rating)).where(GoogleReview.tenant_id == tid))).scalar() or 0
    unreplied = (await db.execute(select(func.count()).select_from(GoogleReview).where(GoogleReview.tenant_id == tid, GoogleReview.status != GoogleReviewStatus.PUBLISHED.value))).scalar_one()
    return {"new_reviews": (await db.execute(select(func.count()).select_from(GoogleReview).where(GoogleReview.tenant_id == tid, GoogleReview.status == "new"))).scalar_one(), "unreplied_reviews": unreplied, "average_rating": round(float(avg), 2), "average_response_time_hours": None}
@router.get("/{review_id}")
async def detail(review_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _staff(current_user); r = await _review(db, current_user.tenant_id, review_id)
    from app.db.models.google_review import GoogleReviewAuditEvent
    events = (await db.execute(select(GoogleReviewAuditEvent).where(GoogleReviewAuditEvent.tenant_id == current_user.tenant_id, GoogleReviewAuditEvent.review_id == r.id).order_by(GoogleReviewAuditEvent.created_at.desc()))).scalars().all()
    return {**_serialize(r), "audit_history": [{"event_type": e.event_type, "created_at": e.created_at, "metadata": e.metadata_json} for e in events]}
@router.put("/{review_id}/reply")
async def edit_reply(review_id: UUID, payload: ReplyEdit, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _staff(current_user); r = await _review(db, current_user.tenant_id, review_id); r.reply_text = payload.reply_text; r.requires_approval = True; r.status = GoogleReviewStatus.AWAITING_APPROVAL.value
    await audit(db, current_user.tenant_id, "reply_edited", review_id=r.id, actor_user_id=current_user.id); await db.commit(); return _serialize(r)
@router.post("/{review_id}/generate")
async def regenerate(review_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _staff(current_user); r = await generate_draft(db, tenant_id=current_user.tenant_id, review=await _review(db, current_user.tenant_id, review_id)); await db.commit(); return _serialize(r)
@router.post("/{review_id}/approve")
async def approve(review_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _staff(current_user); r = await _review(db, current_user.tenant_id, review_id); r.requires_approval, r.approved_at, r.approved_by_user_id = False, datetime.now(timezone.utc), current_user.id; await audit(db, current_user.tenant_id, "reply_approved", review_id=r.id, actor_user_id=current_user.id); await db.commit(); return _serialize(r)
@router.post("/{review_id}/publish")
async def publish(review_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _staff(current_user); r = await _review(db, current_user.tenant_id, review_id)
    if r.requires_approval: raise HTTPException(409, "Reply approval is required before publishing")
    try: await publish_reply(db, tenant_id=current_user.tenant_id, review=r); await db.commit()
    except Exception: await db.commit(); raise HTTPException(502, "Google could not publish this reply; it will be retried")
    return _serialize(r)

@router.post("/webhooks/pubsub")
async def pubsub(request: Request, db: AsyncSession = Depends(get_db)):
    # Pub/Sub push endpoint: provider payload contains a resource notification,
    # so reconciliation fetches the authoritative review via the official API.
    # Google Pub/Sub push authentication is mandatory in deployed environments.
    # Verify the signed OIDC token before using its resource routing fields.
    if settings.ENVIRONMENT != "development":
        bearer = request.headers.get("authorization", "")
        if not bearer.startswith("Bearer ") or not settings.GOOGLE_BUSINESS_PUBSUB_AUDIENCE:
            raise HTTPException(401, "Missing Pub/Sub authentication")
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            claims = id_token.verify_oauth2_token(bearer[7:], google_requests.Request(), settings.GOOGLE_BUSINESS_PUBSUB_AUDIENCE)
            if not claims.get("email_verified"):
                raise ValueError("unverified sender")
        except Exception:
            raise HTTPException(401, "Invalid Pub/Sub authentication")
    body = await request.json(); encoded = body.get("message", {}).get("data")
    if not encoded: raise HTTPException(400, "Invalid Pub/Sub message")
    try: event = json.loads(base64.b64decode(encoded).decode())
    except Exception: raise HTTPException(400, "Invalid Pub/Sub data")
    resource = event.get("resourceName") or event.get("resource_name") or ""
    parts = resource.split("/"); account = parts[1] if len(parts) > 3 else None; location = parts[3] if len(parts) > 3 else None
    if account and location:
        c = (await db.execute(select(GoogleBusinessConnection).where(GoogleBusinessConnection.google_account_id == account, GoogleBusinessConnection.location_id == location, GoogleBusinessConnection.status == "connected"))).scalar_one_or_none()
        if c:
            try: await sync_connection(db, c); await db.commit()
            except Exception: await db.rollback()
    return {"ok": True}
