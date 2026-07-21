from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.core.config import settings
from app.db.models.tenant import Tenant


MAX_PLATFORM_FEE_PERCENT = Decimal("20.000")


def platform_fee_percent_for(tenant: Tenant) -> Decimal:
    """Return the tenant override, falling back to the deployment default."""
    configured = tenant.stripe_platform_fee_percent
    percent = Decimal(str(configured if configured is not None else settings.PLATFORM_FEE_PERCENT))
    if percent < 0 or percent > MAX_PLATFORM_FEE_PERCENT:
        raise ValueError("Platform fee must be between 0 and 20 percent")
    return percent.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def platform_fee_amount_cents(amount_cents: int, fee_percent: Decimal) -> int:
    return int(
        (Decimal(amount_cents) * fee_percent / Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
