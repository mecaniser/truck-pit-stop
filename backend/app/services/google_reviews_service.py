"""Google Reviews provider and AI workflow. All entry points require tenant_id."""
from __future__ import annotations
import base64, hashlib, json
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Any
import anthropic, httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.google_business_crypto import decrypt_google_business_token, encrypt_google_business_token
from app.db.models.google_review import GoogleBusinessConnection, GoogleReview, GoogleReviewAuditEvent, GoogleReviewSettings, GoogleReviewStatus
from app.db.models.tenant import Tenant

MODEL = "claude-opus-4-8"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/business.manage"
DEFAULT_POLICY = "Professional, warm, concise, under 70 words. Use only facts in the review. Never invent facts, guarantee outcomes, discuss repair details or prices, blame customers, or request private information publicly. For negative reviews, apologize and invite offline resolution."


def is_configured() -> bool:
    return bool(settings.GOOGLE_BUSINESS_CLIENT_ID and settings.GOOGLE_BUSINESS_CLIENT_SECRET and settings.GOOGLE_BUSINESS_REDIRECT_URI and settings.GOOGLE_BUSINESS_TOKEN_ENCRYPTION_KEY)


def authorization_url(state: str) -> str:
    from urllib.parse import urlencode
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"client_id": settings.GOOGLE_BUSINESS_CLIENT_ID, "redirect_uri": settings.GOOGLE_BUSINESS_REDIRECT_URI, "response_type": "code", "scope": GOOGLE_SCOPE, "access_type": "offline", "prompt": "consent", "state": state})


async def audit(db: AsyncSession, tenant_id, event_type: str, *, review_id=None, actor_user_id=None, metadata: dict | None = None):
    db.add(GoogleReviewAuditEvent(tenant_id=tenant_id, review_id=review_id, actor_user_id=actor_user_id, event_type=event_type, metadata_json=metadata or {}))


async def _access_token(db: AsyncSession, connection: GoogleBusinessConnection) -> str:
    if not connection.encrypted_access_token or not connection.encrypted_refresh_token:
        raise RuntimeError("Google connection requires reconnection")
    now = datetime.now(timezone.utc)
    if connection.access_token_expires_at and connection.access_token_expires_at > now + timedelta(minutes=2):
        return decrypt_google_business_token(connection.encrypted_access_token)
    async with httpx.AsyncClient(timeout=settings.GOOGLE_BUSINESS_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post("https://oauth2.googleapis.com/token", data={"client_id": settings.GOOGLE_BUSINESS_CLIENT_ID, "client_secret": settings.GOOGLE_BUSINESS_CLIENT_SECRET, "refresh_token": decrypt_google_business_token(connection.encrypted_refresh_token), "grant_type": "refresh_token"})
    if response.is_error:
        connection.last_token_refresh_error = "Google token refresh failed; reconnect required"
        raise RuntimeError(connection.last_token_refresh_error)
    payload = response.json()
    connection.encrypted_access_token = encrypt_google_business_token(payload["access_token"])
    connection.access_token_expires_at = now + timedelta(seconds=int(payload.get("expires_in", 3600)))
    connection.last_token_refresh_at = now
    connection.last_token_refresh_error = None
    await db.flush()
    return payload["access_token"]


async def exchange_code(db: AsyncSession, connection: GoogleBusinessConnection, code: str) -> None:
    async with httpx.AsyncClient(timeout=settings.GOOGLE_BUSINESS_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post("https://oauth2.googleapis.com/token", data={"code": code, "client_id": settings.GOOGLE_BUSINESS_CLIENT_ID, "client_secret": settings.GOOGLE_BUSINESS_CLIENT_SECRET, "redirect_uri": settings.GOOGLE_BUSINESS_REDIRECT_URI, "grant_type": "authorization_code"})
        response.raise_for_status()
        token = response.json()
        userinfo = await client.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {token['access_token']}"})
    connection.google_account_id = userinfo.json().get("sub") if userinfo.is_success else None
    connection.encrypted_access_token = encrypt_google_business_token(token["access_token"])
    # Google only returns refresh_token on consent; preserve an existing valid one on reconnect.
    if token.get("refresh_token"):
        connection.encrypted_refresh_token = encrypt_google_business_token(token["refresh_token"])
    connection.access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token.get("expires_in", 3600)))
    connection.status = "location_selection_required"


async def list_locations(db: AsyncSession, connection: GoogleBusinessConnection) -> list[dict]:
    token = await _access_token(db, connection)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=settings.GOOGLE_BUSINESS_HTTP_TIMEOUT_SECONDS) as client:
        accounts_response = await client.get("https://mybusinessaccountmanagement.googleapis.com/v1/accounts", headers=headers)
        accounts_response.raise_for_status()
        locations: list[dict] = []
        for account in accounts_response.json().get("accounts", []):
            page = await client.get(f"https://mybusinessbusinessinformation.googleapis.com/v1/{account['name']}/locations?readMask=name,title", headers=headers)
            if page.is_error:
                continue
            for location in page.json().get("locations", []):
                locations.append({"account_id": account["name"].split("/")[-1], "location_id": location["name"].split("/")[-1], "name": location.get("title") or location["name"]})
    return locations


def _first_name(name: str | None) -> str | None:
    return name.strip().split()[0] if name and name.strip() else None


def _review_fields(payload: dict) -> tuple[str, int, str | None, str | None, datetime | None, datetime | None]:
    rid = payload.get("reviewId") or payload.get("name", "").rsplit("/", 1)[-1]
    rating_raw = payload.get("starRating", payload.get("rating", 0))
    if isinstance(rating_raw, int):
        rating = rating_raw
    else:
        normalized = str(rating_raw).replace("STAR_RATING_", "")
        rating = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}.get(normalized, 0)
    name = payload.get("reviewer", {}).get("displayName") or payload.get("reviewerName")
    text = payload.get("comment") or payload.get("reviewText")
    def parse(value): return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    return rid, rating, name, text, parse(payload.get("createTime") or payload.get("create_time")), parse(payload.get("updateTime") or payload.get("update_time"))


async def upsert_review(db: AsyncSession, *, tenant_id, connection: GoogleBusinessConnection, payload: dict) -> tuple[GoogleReview, bool]:
    review_id, rating, reviewer, text, created, updated = _review_fields(payload)
    if not review_id or not rating:
        raise ValueError("Google notification did not contain a review")
    review = (await db.execute(select(GoogleReview).where(GoogleReview.tenant_id == tenant_id, GoogleReview.google_review_id == review_id))).scalar_one_or_none()
    created_new = review is None
    if review is None:
        review = GoogleReview(tenant_id=tenant_id, connection_id=connection.id, google_review_id=review_id, rating=rating, reviewer_name=reviewer, review_text=text, review_created_at=created, review_updated_at=updated, raw_payload=payload)
        db.add(review)
        await db.flush()
        await audit(db, tenant_id, "review_ingested", review_id=review.id, metadata={"google_review_id": review_id})
    else:
        review.rating, review.reviewer_name, review.review_text, review.review_created_at, review.review_updated_at, review.raw_payload = rating, reviewer, text, created, updated, payload
    return review, created_new


async def generate_draft(db: AsyncSession, *, tenant_id, review: GoogleReview) -> GoogleReview:
    settings_row = (await db.execute(select(GoogleReviewSettings).where(GoogleReviewSettings.tenant_id == tenant_id))).scalar_one_or_none()
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
    if not review.review_text or not settings.ANTHROPIC_API_KEY:
        review.requires_approval, review.status = True, GoogleReviewStatus.AWAITING_APPROVAL.value
        await audit(db, tenant_id, "generation_failed", review_id=review.id, metadata={"reason": "empty review or unavailable AI"})
        return review
    policy = (settings_row.reply_policy if settings_row and settings_row.reply_policy else DEFAULT_POLICY)
    prompt = f"Business: {tenant.name}\nBrand voice: {settings_row.brand_voice_prompt if settings_row else ''}\nPolicy: {policy}\nRating: {review.rating}/5\nReviewer first name: {_first_name(review.reviewer_name) or 'not available'}\nReview: {review.review_text}\nWrite only the public reply."
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(model=MODEL, max_tokens=180, system="You write safe public Google Business Profile replies.", messages=[{"role": "user", "content": prompt}])
        draft = next((block.text for block in response.content if block.type == "text"), "").strip()
        if not draft: raise RuntimeError("AI returned no reply")
        review.ai_draft = review.reply_text = draft[:600]
        review.ai_model, review.ai_metadata = MODEL, {"word_count": len(draft.split())}
        auto = bool(settings_row and settings_row.auto_publish_five_star and review.rating == 5)
        review.requires_approval = not auto
        review.status = GoogleReviewStatus.NEW.value if auto else GoogleReviewStatus.AWAITING_APPROVAL.value
        await audit(db, tenant_id, "draft_generated", review_id=review.id, metadata={"model": MODEL, "auto_publish_eligible": auto})
    except Exception as exc:
        review.requires_approval, review.status = True, GoogleReviewStatus.AWAITING_APPROVAL.value
        review.ai_metadata = {"error": str(exc)[:300]}
        await audit(db, tenant_id, "generation_failed", review_id=review.id)
    return review


async def sync_connection(db: AsyncSession, connection: GoogleBusinessConnection) -> int:
    if not connection.tenant_id or not connection.google_account_id or not connection.location_id or connection.status != "connected": return 0
    token = await _access_token(db, connection)
    url = f"https://mybusiness.googleapis.com/v4/accounts/{connection.google_account_id}/locations/{connection.location_id}/reviews"
    async with httpx.AsyncClient(timeout=settings.GOOGLE_BUSINESS_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
    count = 0
    for item in response.json().get("reviews", []):
        review, created = await upsert_review(db, tenant_id=connection.tenant_id, connection=connection, payload=item)
        if created:
            await generate_draft(db, tenant_id=connection.tenant_id, review=review)
            count += 1
    connection.last_sync_at, connection.last_sync_error = datetime.now(timezone.utc), None
    return count


async def publish_reply(db: AsyncSession, *, tenant_id, review: GoogleReview) -> None:
    if review.tenant_id != tenant_id: raise ValueError("cross-tenant review publish blocked")
    connection = (await db.execute(select(GoogleBusinessConnection).where(GoogleBusinessConnection.id == review.connection_id, GoogleBusinessConnection.tenant_id == tenant_id))).scalar_one_or_none()
    if not connection or not review.reply_text: raise RuntimeError("Google connection or reply is missing")
    if review.status == GoogleReviewStatus.PUBLISHED.value: return
    review.status, review.last_publish_attempt_at = GoogleReviewStatus.PUBLISHING.value, datetime.now(timezone.utc)
    try:
        token = await _access_token(db, connection)
        url = f"https://mybusiness.googleapis.com/v4/accounts/{connection.google_account_id}/locations/{connection.location_id}/reviews/{review.google_review_id}/reply"
        async with httpx.AsyncClient(timeout=settings.GOOGLE_BUSINESS_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.put(url, headers={"Authorization": f"Bearer {token}"}, json={"comment": review.reply_text})
            response.raise_for_status()
        review.status, review.published_at, review.publish_response, review.publish_failure_reason = GoogleReviewStatus.PUBLISHED.value, datetime.now(timezone.utc), response.json(), None
        await audit(db, tenant_id, "reply_published", review_id=review.id)
    except Exception as exc:
        review.publish_retry_count += 1
        review.publish_failure_reason = str(exc)[:500]
        review.status = GoogleReviewStatus.FAILED.value
        await audit(db, tenant_id, "publish_failed", review_id=review.id, metadata={"attempt": review.publish_retry_count})
        raise
