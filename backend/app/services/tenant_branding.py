"""Shared sender-name lookup for tenant-facing notifications."""
from __future__ import annotations

import re
from html import escape
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import format_phone_display, normalize_phone
from app.db.models.tenant import Tenant

# US state/territory abbreviations, keyed by full lowercase name for lookups
# against addresses that spell the state out instead of abbreviating it.
_STATE_NAMES_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "puerto rico": "PR",
}
_STATE_ABBRS = set(_STATE_NAMES_TO_ABBR.values())
_ABBR_ZIP_RE = re.compile(r"\b([A-Za-z]{2})\s*\d{5}(?:-\d{4})?\b")
_ABBR_ONLY_RE = re.compile(r",\s*([A-Za-z]{2})\s*(?:,|$)")
_ABBR_TRAILING_RE = re.compile(r"\b([A-Za-z]{2})\s*$")


def extract_us_state(address: Optional[str]) -> Optional[str]:
    """
    Best-effort extraction of a US state abbreviation from a free-text address.

    Shop addresses are stored as a single free-text field (no structured
    city/state/zip columns), so this pattern-matches common US formats
    instead of requiring a schema change.
    """
    text = (address or "").strip()
    if not text:
        return None

    match = _ABBR_ZIP_RE.search(text)
    if match:
        candidate = match.group(1).upper()
        if candidate in _STATE_ABBRS:
            return candidate

    match = _ABBR_ONLY_RE.search(text)
    if match:
        candidate = match.group(1).upper()
        if candidate in _STATE_ABBRS:
            return candidate

    match = _ABBR_TRAILING_RE.search(text.strip())
    if match:
        candidate = match.group(1).upper()
        if candidate in _STATE_ABBRS:
            return candidate

    lowered = text.lower()
    for name, abbr in _STATE_NAMES_TO_ABBR.items():
        if name in lowered:
            return abbr

    return None


async def get_tenant_display_name(db: AsyncSession, tenant_id: UUID) -> str:
    """Return the tenant's current shop name without falling back to platform branding."""
    name = await db.scalar(select(Tenant.name).where(Tenant.id == tenant_id))
    return name.strip() if name and name.strip() else "Your repair shop"


def build_tenant_contact_html(tenant: Tenant | None) -> str:
    """Small customer-email contact block for tenant phone/email."""
    if not tenant:
        return ""
    rows = []
    if tenant.phone:
        phone_href = escape(normalize_phone(tenant.phone) or tenant.phone)
        phone_display = escape(format_phone_display(tenant.phone))
        rows.append(f'Phone: <a href="tel:{phone_href}" style="color: #d97706; text-decoration: none;">{phone_display}</a>')
    if tenant.email:
        email = escape(tenant.email)
        rows.append(f'Email: <a href="mailto:{email}" style="color: #d97706; text-decoration: none;">{email}</a>')
    if not rows:
        return ""
    shop_name = escape(tenant.name or "the shop")
    return f"""
        <p style="color: #666; font-size: 12px; text-align: center; line-height: 1.6;">
            Questions? Contact {shop_name} directly:<br>
            {'<br>'.join(rows)}
        </p>
    """
