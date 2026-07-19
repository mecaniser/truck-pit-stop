from typing import Optional


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Canonical phone format: digits-only, or None when empty."""
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits or None


def format_phone_display(phone: Optional[str]) -> str:
    """Human-friendly US phone display when possible."""
    digits = normalize_phone(phone)
    if not digits:
        return ""
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone.strip() if phone else digits
