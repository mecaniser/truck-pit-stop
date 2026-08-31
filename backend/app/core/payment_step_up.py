"""Opaque, session-bound step-up authorization for payment-source settings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
import secrets
from typing import Optional
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.correlation import normalize_correlation_id
from app.core.dependencies import CurrentUser, get_current_active_user, get_token_from_request, user_has_permission
from app.core import redis as redis_store
from app.core.security import decode_token
from app.db.models.payment_step_up import PaymentStepUpAuditEvent, PaymentStepUpGrant
from app.db.models.user import UserRole


STEP_UP_HEADER = "X-Step-Up-Authorization"


class PaymentStepUpScope(str, Enum):
    MANAGE = "payment_sources.manage"
    ZELLE_DISABLE = "payment_sources.zelle.disable"
    ZELLE_QR_REMOVE = "payment_sources.zelle.qr.remove"
    STRIPE_DISCONNECT = "payment_sources.stripe.disconnect"
    QUICKBOOKS_DISCONNECT = "payment_sources.quickbooks.disconnect"
    PLATFORM_STRIPE_RESET = "platform.payment_sources.stripe.reset"
    PLATFORM_QUICKBOOKS_RESET = "platform.payment_sources.quickbooks.reset"
    # Voiding an order the financial-record guard protects. Not a payment
    # setting, but the same question: prove it is you before overriding a rule
    # that exists to stop an accident.
    REPAIR_ORDER_FORCE_VOID = "repair_orders.force_void"


DESTRUCTIVE_SCOPES = {
    PaymentStepUpScope.REPAIR_ORDER_FORCE_VOID,
    PaymentStepUpScope.ZELLE_DISABLE,
    PaymentStepUpScope.ZELLE_QR_REMOVE,
    PaymentStepUpScope.STRIPE_DISCONNECT,
    PaymentStepUpScope.QUICKBOOKS_DISCONNECT,
    PaymentStepUpScope.PLATFORM_STRIPE_RESET,
    PaymentStepUpScope.PLATFORM_QUICKBOOKS_RESET,
}

PLATFORM_SCOPES = {
    PaymentStepUpScope.PLATFORM_STRIPE_RESET,
    PaymentStepUpScope.PLATFORM_QUICKBOOKS_RESET,
}

# A successful top-level Payments & Accounting unlock is intentionally broader
# than a single provider action.  It may authorize tenant payment-source
# mutations for the lifetime of the reusable manage grant, but it must never
# cross into platform administration or unrelated destructive workflows.
MANAGE_AUTHORIZED_SCOPES = {
    PaymentStepUpScope.ZELLE_DISABLE,
    PaymentStepUpScope.ZELLE_QR_REMOVE,
    PaymentStepUpScope.STRIPE_DISCONNECT,
    PaymentStepUpScope.QUICKBOOKS_DISCONNECT,
}


@dataclass(frozen=True)
class PaymentStepUpContext:
    raw_grant: Optional[str]
    session_jti: str
    token_version: int
    current_user: CurrentUser
    correlation_id: str


def _origin(value: str) -> Optional[str]:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def require_trusted_cookie_origin(request: Request) -> None:
    """Reject cross-site cookie-authenticated step-up requests.

    Bearer clients are not subject to browser CSRF.  Browsers using the
    HttpOnly access cookie must present an exact configured Origin or Referer.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return
    if not request.cookies.get("access_token"):
        return

    supplied = _origin(request.headers.get("origin", ""))
    if supplied is None:
        supplied = _origin(request.headers.get("referer", ""))
    allowed = {_origin(origin) for origin in settings.CORS_ORIGINS}
    allowed.discard(None)
    if supplied not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trusted browser origin required",
        )


async def get_payment_step_up_context(
    request: Request,
    raw_grant: Optional[str] = Header(None, alias=STEP_UP_HEADER),
    primary_token: str = Depends(get_token_from_request),
    current_user: CurrentUser = Depends(get_current_active_user),
) -> PaymentStepUpContext:
    require_trusted_cookie_origin(request)
    claims = decode_token(primary_token) or {}
    session_jti = claims.get("jti")
    if not session_jti or claims.get("type") is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return PaymentStepUpContext(
        raw_grant=raw_grant,
        session_jti=str(session_jti),
        token_version=int(claims.get("ver", 0)),
        current_user=current_user,
        correlation_id=normalize_correlation_id(getattr(request.state, "correlation_id", None)),
    )


def _provider_for_scope(scope: PaymentStepUpScope) -> Optional[str]:
    if "stripe" in scope.value:
        return "stripe"
    if "quickbooks" in scope.value:
        return "quickbooks"
    if "zelle" in scope.value:
        return "zelle"
    return None


def payment_step_up_audit_event(
    *,
    context: PaymentStepUpContext,
    event_type: str,
    scope: PaymentStepUpScope,
    grant: Optional[PaymentStepUpGrant] = None,
    target_tenant_id: Optional[UUID] = None,
    metadata: Optional[dict] = None,
) -> PaymentStepUpAuditEvent:
    return PaymentStepUpAuditEvent(
        tenant_id=context.current_user.tenant_id,
        target_tenant_id=target_tenant_id,
        user_id=context.current_user.id,
        grant_id=grant.id if grant else None,
        event_type=event_type,
        scope=scope.value,
        provider=_provider_for_scope(scope),
        correlation_id=context.correlation_id,
        metadata_json=metadata or {},
    )


def payment_step_up_mutation_result(
    *,
    context: PaymentStepUpContext,
    scope: PaymentStepUpScope,
    grant: PaymentStepUpGrant,
    succeeded: bool,
    provider: Optional[str] = None,
    target_tenant_id: Optional[UUID] = None,
    metadata: Optional[dict] = None,
) -> PaymentStepUpAuditEvent:
    """Create a redacted terminal outcome for a protected configuration action."""
    return payment_step_up_mutation_result_for_ids(
        tenant_id=context.current_user.tenant_id,
        user_id=context.current_user.id,
        grant_id=grant.id,
        correlation_id=context.correlation_id,
        scope=scope,
        succeeded=succeeded,
        provider=provider,
        target_tenant_id=target_tenant_id,
        metadata=metadata,
    )


def payment_step_up_mutation_result_for_ids(
    *,
    tenant_id: Optional[UUID],
    user_id: UUID,
    grant_id: UUID,
    correlation_id: Optional[str],
    scope: PaymentStepUpScope,
    succeeded: bool,
    provider: Optional[str] = None,
    target_tenant_id: Optional[UUID] = None,
    metadata: Optional[dict] = None,
) -> PaymentStepUpAuditEvent:
    """Create a terminal outcome after ORM objects may have been expired."""
    return PaymentStepUpAuditEvent(
        tenant_id=tenant_id,
        target_tenant_id=target_tenant_id,
        user_id=user_id,
        grant_id=grant_id,
        event_type="mutation_succeeded" if succeeded else "mutation_failed",
        scope=scope.value,
        provider=provider or _provider_for_scope(scope),
        correlation_id=correlation_id,
        metadata_json=metadata or {},
    )


def validate_scope_authority(
    current_user: CurrentUser,
    scope: PaymentStepUpScope,
    target_tenant_id: Optional[UUID],
) -> None:
    if scope in PLATFORM_SCOPES:
        if current_user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
        if target_tenant_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Target tenant is required")
        return

    if target_tenant_id is not None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Target tenant is not allowed for this scope")
    if scope is PaymentStepUpScope.REPAIR_ORDER_FORCE_VOID:
        # Overriding the financial-record guard is the shop's call, not the
        # payment-settings permission's: this scope changes a repair order, and
        # gating it on "payments" would both admit and exclude the wrong people.
        if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the shop owner or an admin can void a finalized order",
            )
        if current_user.tenant_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A shop context is required")
        return
    if not user_has_permission(current_user, "payments"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this setting. Ask the shop owner to grant access.",
        )
    if current_user.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A shop context is required")


def issue_step_up_grant(
    *,
    context: PaymentStepUpContext,
    scope: PaymentStepUpScope,
    target_tenant_id: Optional[UUID],
) -> tuple[PaymentStepUpGrant, str]:
    raw_grant = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    one_time = scope in DESTRUCTIVE_SCOPES
    ttl = (
        settings.PAYMENT_STEP_UP_DESTRUCTIVE_TTL_SECONDS
        if one_time
        else settings.PAYMENT_STEP_UP_MANAGE_TTL_SECONDS
    )
    grant = PaymentStepUpGrant(
        tenant_id=context.current_user.tenant_id,
        target_tenant_id=target_tenant_id,
        user_id=context.current_user.id,
        session_jti=context.session_jti,
        token_version=context.token_version,
        scope=scope.value,
        token_digest=sha256(raw_grant.encode("utf-8")).hexdigest(),
        one_time=one_time,
        expires_at=now + timedelta(seconds=ttl),
    )
    return grant, raw_grant


def step_up_required(scope: PaymentStepUpScope) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_428_PRECONDITION_REQUIRED,
        detail={
            "code": "STEP_UP_REQUIRED",
            "message": (
                "Verify your password to void a finalized order."
                if scope is PaymentStepUpScope.REPAIR_ORDER_FORCE_VOID
                else "Verify your password to change payment sources."
            ),
            "required_scope": scope.value,
        },
    )


async def authorize_step_up(
    db: AsyncSession,
    *,
    context: PaymentStepUpContext,
    required_scope: PaymentStepUpScope,
    target_tenant_id: Optional[UUID] = None,
    consume: bool = False,
) -> PaymentStepUpGrant:
    """Validate a persisted grant and optionally consume it atomically.

    The caller retains transaction ownership so a destructive grant can be
    consumed in the same commit as the configuration mutation.
    """
    if not context.raw_grant:
        db.add(payment_step_up_audit_event(context=context, event_type="denied", scope=required_scope, target_tenant_id=target_tenant_id, metadata={"reason": "missing"}))
        await db.commit()
        raise step_up_required(required_scope)

    digest = sha256(context.raw_grant.encode("utf-8")).hexdigest()
    query = select(PaymentStepUpGrant).where(PaymentStepUpGrant.token_digest == digest)
    grant = (await db.execute(query)).scalar_one_or_none()
    if grant is None:
        db.add(payment_step_up_audit_event(context=context, event_type="denied", scope=required_scope, target_tenant_id=target_tenant_id, metadata={"reason": "unknown"}))
        await db.commit()
        raise step_up_required(required_scope)

    now = datetime.now(timezone.utc)
    reason: Optional[str] = None
    event_type = "denied"
    grant_expires_at = grant.expires_at
    if grant_expires_at.tzinfo is None:
        grant_expires_at = grant_expires_at.replace(tzinfo=timezone.utc)
    if grant_expires_at <= now:
        reason, event_type = "expired", "expired"
    elif grant.revoked_at is not None:
        reason = "revoked"
    elif grant.consumed_at is not None:
        reason = "consumed"
    elif grant.user_id != context.current_user.id:
        reason = "user_mismatch"
    elif grant.tenant_id != context.current_user.tenant_id:
        reason = "tenant_mismatch"
    elif grant.session_jti != context.session_jti:
        reason = "session_mismatch"
    elif grant.token_version != context.token_version:
        reason = "session_version_mismatch"
    grant_scope = PaymentStepUpScope(grant.scope)
    manage_authorizes_action = (
        grant_scope is PaymentStepUpScope.MANAGE
        and required_scope in MANAGE_AUTHORIZED_SCOPES
    )
    if reason is None and grant.scope != required_scope.value and not manage_authorizes_action:
        db.add(payment_step_up_audit_event(context=context, event_type="denied", scope=required_scope, grant=grant, target_tenant_id=target_tenant_id, metadata={"reason": "scope_mismatch"}))
        await db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Step-up grant scope is not allowed for this action")
    elif reason is None and grant.target_tenant_id != target_tenant_id:
        reason = "target_mismatch"
    elif reason is None and grant.one_time != (grant_scope in DESTRUCTIVE_SCOPES):
        reason = "grant_type_mismatch"

    current_version = await redis_store.get_token_version(str(context.current_user.id))
    if reason is None and grant.token_version != current_version:
        reason = "token_version_changed"

    if reason is not None:
        db.add(payment_step_up_audit_event(context=context, event_type=event_type, scope=required_scope, grant=grant, target_tenant_id=target_tenant_id, metadata={"reason": reason}))
        await db.commit()
        raise step_up_required(required_scope)

    if consume:
        if grant.one_time:
            claim = await db.execute(
                update(PaymentStepUpGrant)
                .where(
                    PaymentStepUpGrant.id == grant.id,
                    PaymentStepUpGrant.consumed_at.is_(None),
                    PaymentStepUpGrant.revoked_at.is_(None),
                )
                .values(consumed_at=now)
            )
            if claim.rowcount != 1:
                db.add(payment_step_up_audit_event(context=context, event_type="denied", scope=required_scope, grant=grant, target_tenant_id=target_tenant_id, metadata={"reason": "consumed"}))
                await db.commit()
                raise step_up_required(required_scope)
            grant.consumed_at = now
        elif not manage_authorizes_action:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A one-time step-up grant is required")

    db.add(payment_step_up_audit_event(context=context, event_type="used", scope=required_scope, grant=grant, target_tenant_id=target_tenant_id))
    return grant
