"""
Password Policy Module

Enforces password complexity requirements for all user-facing password operations.
"""
import re
from fastapi import HTTPException, status


# Common weak passwords to reject
COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456", "12345678", "123456789",
    "qwerty", "abc123", "monkey", "master", "dragon", "111111", "baseball",
    "iloveyou", "trustno1", "sunshine", "princess", "welcome", "admin",
    "letmein", "login", "passw0rd", "p@ssword", "p@ssw0rd",
}


def validate_password(password: str, min_length: int = 8) -> None:
    """
    Validate password meets complexity requirements.
    
    Requirements:
    - Minimum length (default 8, recommended 12 for high-security)
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - Not a common weak password
    
    Raises HTTPException with 400 status if validation fails.
    """
    errors = []
    
    if len(password) < min_length:
        errors.append(f"at least {min_length} characters")
    
    if not re.search(r"[A-Z]", password):
        errors.append("one uppercase letter")
    
    if not re.search(r"[a-z]", password):
        errors.append("one lowercase letter")
    
    if not re.search(r"\d", password):
        errors.append("one digit")
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+\[\]\\;'/`~]", password):
        errors.append("one special character (!@#$%^&*...)")
    
    # Check against common passwords (case-insensitive)
    if password.lower() in COMMON_PASSWORDS:
        errors.append("not be a common password")
    
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must contain: {', '.join(errors)}"
        )


def validate_password_strength(password: str) -> dict:
    """
    Returns password strength analysis without raising exceptions.
    Useful for frontend password strength indicators.
    """
    checks = {
        "min_length": len(password) >= 8,
        "has_uppercase": bool(re.search(r"[A-Z]", password)),
        "has_lowercase": bool(re.search(r"[a-z]", password)),
        "has_digit": bool(re.search(r"\d", password)),
        "has_special": bool(re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+\[\]\\;'/`~]", password)),
        "not_common": password.lower() not in COMMON_PASSWORDS,
    }
    
    passed = sum(checks.values())
    total = len(checks)
    
    if passed == total:
        strength = "strong"
    elif passed >= 4:
        strength = "medium"
    else:
        strength = "weak"
    
    return {
        "checks": checks,
        "passed": passed,
        "total": total,
        "strength": strength,
    }
