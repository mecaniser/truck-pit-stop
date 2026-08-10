"""Narrow WorkOS HTTP/JWT boundary.

Only verified WorkOS access-token claims are authoritative for organization
membership and permissions. Authentication response fields are descriptive.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from jose import JWTError, jwt

from app.core.config import settings


class WorkOSProviderError(Exception):
    pass


_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cached_at: Optional[datetime] = None


async def _get_jwks(force: bool = False) -> Dict[str, Any]:
    global _jwks_cache, _jwks_cached_at
    now = datetime.now(timezone.utc)
    if not force and _jwks_cache and _jwks_cached_at and (now - _jwks_cached_at).total_seconds() < 3600:
        return _jwks_cache
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"https://api.workos.com/sso/jwks/{settings.WORKOS_CLIENT_ID}")
    if response.status_code >= 400:
        raise WorkOSProviderError("WorkOS signing keys are unavailable")
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
        raise WorkOSProviderError("WorkOS signing keys are malformed")
    _jwks_cache, _jwks_cached_at = payload, now
    return payload


async def verify_access_token(access_token: str) -> Dict[str, Any]:
    """Verify signature, issuer, application, active org, and permissions."""
    if not access_token or not isinstance(access_token, str):
        raise WorkOSProviderError("WorkOS access token is missing")
    try:
        header = jwt.get_unverified_header(access_token)
    except JWTError as exc:
        raise WorkOSProviderError("WorkOS access token is malformed") from exc
    kid = header.get("kid")
    alg = header.get("alg")
    if not kid or alg not in {"RS256"}:
        raise WorkOSProviderError("WorkOS access token algorithm is invalid")
    for force in (False, True):
        jwks = await _get_jwks(force=force)
        key = next((item for item in jwks["keys"] if item.get("kid") == kid), None)
        if key:
            break
    if not key:
        raise WorkOSProviderError("WorkOS access token signing key is unknown")
    try:
        claims = jwt.decode(
            access_token,
            key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise WorkOSProviderError("WorkOS access token verification failed") from exc
    issuer = str(claims.get("iss") or "").rstrip("/")
    if issuer != settings.WORKOS_ISSUER.rstrip("/"):
        # Issuer URLs are public configuration, not credentials. Include both
        # values in the internal exception so callback logs can diagnose an
        # environment mismatch without ever logging the JWT itself.
        raise WorkOSProviderError(
            f"WorkOS access token issuer is invalid "
            f"(received={issuer!r}, expected={settings.WORKOS_ISSUER.rstrip('/')!r})"
        )
    if claims.get("client_id") != settings.WORKOS_CLIENT_ID:
        raise WorkOSProviderError("WorkOS access token application is invalid")
    permissions = claims.get("permissions")
    if not claims.get("sub") or not claims.get("org_id"):
        raise WorkOSProviderError("WorkOS organization membership is missing")
    if not isinstance(permissions, list) or not all(isinstance(value, str) for value in permissions):
        raise WorkOSProviderError("WorkOS permissions are unavailable")
    return claims


async def authenticate(payload: Dict[str, Any]) -> Dict[str, Any]:
    body = {
        "client_id": settings.WORKOS_CLIENT_ID,
        "client_secret": settings.WORKOS_API_KEY,
        **payload,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post("https://api.workos.com/user_management/authenticate", json=body)
    if response.status_code >= 400:
        raise WorkOSProviderError("WorkOS authentication failed")
    result = response.json()
    if not isinstance(result, dict):
        raise WorkOSProviderError("WorkOS authentication response is malformed")
    return result


async def send_invitation(*, email: str, organization_id: str, role_slug: str, inviter_user_id: Optional[str]) -> Dict[str, Any]:
    body = {"email": email, "organization_id": organization_id, "role_slug": role_slug}
    if inviter_user_id:
        body["inviter_user_id"] = inviter_user_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.workos.com/user_management/invitations",
            headers={"Authorization": f"Bearer {settings.WORKOS_API_KEY}"},
            json=body,
        )
    if response.status_code >= 400:
        raise WorkOSProviderError("WorkOS invitation could not be created")
    result = response.json()
    if not isinstance(result, dict) or not result.get("id"):
        raise WorkOSProviderError("WorkOS invitation response is malformed")
    return result


async def get_invitation(invitation_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://api.workos.com/user_management/invitations/{invitation_id}",
            headers={"Authorization": f"Bearer {settings.WORKOS_API_KEY}"},
        )
    if response.status_code >= 400:
        raise WorkOSProviderError("WorkOS invitation is unavailable")
    result = response.json()
    if not isinstance(result, dict):
        raise WorkOSProviderError("WorkOS invitation response is malformed")
    return result


async def resend_invitation(invitation_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"https://api.workos.com/user_management/invitations/{invitation_id}/resend",
            headers={"Authorization": f"Bearer {settings.WORKOS_API_KEY}"},
        )
    if response.status_code >= 400:
        raise WorkOSProviderError("WorkOS invitation could not be resent")
    result = response.json()
    if not isinstance(result, dict) or result.get("id") != invitation_id:
        raise WorkOSProviderError("WorkOS invitation response is malformed")
    return result


async def revoke_invitation(invitation_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"https://api.workos.com/user_management/invitations/{invitation_id}/revoke",
            headers={"Authorization": f"Bearer {settings.WORKOS_API_KEY}"},
        )
    if response.status_code >= 400:
        raise WorkOSProviderError("WorkOS invitation could not be revoked")
    result = response.json()
    if not isinstance(result, dict) or result.get("id") != invitation_id:
        raise WorkOSProviderError("WorkOS invitation response is malformed")
    return result


async def get_or_create_organization(*, tenant_id: str, name: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {settings.WORKOS_API_KEY}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        lookup = await client.get(
            f"https://api.workos.com/organizations/external_id/{tenant_id}",
            headers=headers,
        )
        if lookup.status_code < 400:
            result = lookup.json()
        elif lookup.status_code == 404:
            created = await client.post(
                "https://api.workos.com/organizations",
                headers=headers,
                json={"name": name, "external_id": tenant_id},
            )
            if created.status_code >= 400:
                raise WorkOSProviderError("WorkOS organization could not be created")
            result = created.json()
        else:
            raise WorkOSProviderError("WorkOS organization lookup failed")
    if not isinstance(result, dict) or not result.get("id") or result.get("external_id") != tenant_id:
        raise WorkOSProviderError("WorkOS organization response is malformed")
    return result
