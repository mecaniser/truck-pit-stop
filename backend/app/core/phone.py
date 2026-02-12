from typing import Optional


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Canonical phone format: digits-only, or None when empty."""
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits or None
