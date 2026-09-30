# ruff: noqa: SIM117
"""Bounded read-only Motive transport. All URLs are fixed, never caller supplied."""

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.core.config import settings

SCOPES = "companies.read locations.vehicle_locations_list"
AUTHORIZE_URL = "https://gomotive.com/oauth/authorize"
API_URL = "https://api.gomotive.com"


class MotiveProviderError(Exception):
    def __init__(self, code="provider_error", retry_after=0):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


class MotiveClient:
    def __init__(self, transport=None):
        self.transport = transport

    async def request(self, method, path, *, token=None, data=None, params=None):
        # The service additionally requires per-tenant approval before every call.
        if not settings.MOTIVE_ENABLED:
            raise MotiveProviderError("not_configured")
        headers = {
            "Accept": "application/json",
            "X-Time-Zone": "UTC",
            "X-Metric-Units": "true",
        }
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, transport=self.transport
            ) as client:
                async with client.stream(
                    method, API_URL + path, headers=headers, data=data, params=params
                ) as response:
                    if response.status_code == 403:
                        raise MotiveProviderError("insufficient_scope")
                    if response.status_code == 401:
                        raise MotiveProviderError("reauthorization_required")
                    if response.status_code == 429:
                        raise MotiveProviderError(
                            "rate_limited",
                            retry_after_seconds(response.headers.get("Retry-After")),
                        )
                    if response.status_code == 400 and path == "/oauth/token":
                        raise MotiveProviderError("reauthorization_required")
                    if not 200 <= response.status_code < 300:
                        raise MotiveProviderError("provider_error")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise MotiveProviderError("invalid_response")
                    result = json.loads(body)
                    if not isinstance(result, dict):
                        raise TypeError()
                    return result
        except (httpx.HTTPError, ValueError, TypeError, RecursionError):
            raise MotiveProviderError("provider_error") from None

    async def tokens(self, *, code=None, refresh_token=None):
        data = {
            "client_id": settings.MOTIVE_CLIENT_ID,
            "client_secret": settings.MOTIVE_CLIENT_SECRET,
            "redirect_uri": settings.MOTIVE_REDIRECT_URI,
            "grant_type": "authorization_code" if code else "refresh_token",
        }
        data.update({"code": code} if code else {"refresh_token": refresh_token})
        result = await self.request("POST", "/oauth/token", data=data)
        if refresh_token and "refresh_token" not in result:
            result["refresh_token"] = refresh_token
        if (
            not isinstance(result.get("access_token"), str)
            or not result["access_token"]
            or not isinstance(result.get("refresh_token"), str)
            or not result["refresh_token"]
            or str(result.get("token_type", "")).lower() != "bearer"
            or type(result.get("expires_in")) is not int
            or not 60 <= result["expires_in"] <= 31_536_000
            or len(result["access_token"]) > 16384
            or len(result["refresh_token"]) > 16384
        ):
            raise MotiveProviderError("invalid_response")
        if "scope" in result and not set(SCOPES.split()).issubset(
            str(result["scope"]).split()
        ):
            raise MotiveProviderError("insufficient_scope")
        return {
            key: result[key] for key in ("access_token", "refresh_token", "expires_in")
        }

    async def company(self, token):
        result = await self.request("GET", "/v1/companies", token=token)
        try:
            rows = result["companies"]
            if len(rows) != 1 or result.get("pagination", {}).get("total", 1) != 1:
                raise ValueError()
            company = rows[0]["company"]
            return identifier(company["id"]), safe_text(company.get("name"), 255)
        except (KeyError, TypeError, ValueError):
            raise MotiveProviderError("invalid_response") from None

    async def vehicles(self, token):
        vehicles = []
        seen = set()
        expected_total = None
        for page in range(1, 11):
            result = await self.request(
                "GET",
                "/v3/vehicle_locations",
                token=token,
                params={"page_no": page, "per_page": 100, "vehicle_status": "active"},
            )
            try:
                rows = result["vehicles"]
                pagination = result["pagination"]
                total = pagination["total"]
                if expected_total is not None and expected_total != total:
                    raise ValueError()
                expected_total = total
                if (
                    not isinstance(rows, list)
                    or len(rows) > 100
                    or type(total) is not int
                    or not 0 <= total <= 1000
                    or pagination["page_no"] != page
                ):
                    raise ValueError()
                for row in rows:
                    vehicle = row["vehicle"]
                    key = identifier(vehicle["id"])
                    if key in seen:
                        raise ValueError()
                    seen.add(key)
                    vehicles.append(vehicle)
                if len(vehicles) > total:
                    raise ValueError()
                if len(vehicles) == total:
                    return vehicles
                if not rows:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise MotiveProviderError("invalid_response") from None
        raise MotiveProviderError("sync_limit")


def identifier(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Invalid provider identifier")
    return str(value)


def safe_text(value, maximum):
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError("Invalid provider text")
    return value


def retry_after_seconds(value):
    if not value:
        return 0
    try:
        seconds = (
            int(value)
            if value.isdigit()
            else (
                parsedate_to_datetime(value) - datetime.now(timezone.utc)
            ).total_seconds()
        )
        return max(0, min(3600, int(seconds)))
    except (ValueError, TypeError, OverflowError):
        return 0
