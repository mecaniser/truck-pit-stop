"""Shared sender-name lookup for tenant-facing notifications."""
from __future__ import annotations

from html import escape
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import format_phone_display, normalize_phone
from app.db.models.tenant import Tenant


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
