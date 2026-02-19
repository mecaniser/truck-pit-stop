from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.password_policy import validate_password, validate_password_strength


class TestValidatePassword:
    def test_strong_password_passes(self):
        validate_password("MyStr0ng@Pass!")  # should not raise

    def test_too_short_raises(self):
        with pytest.raises(HTTPException) as exc:
            validate_password("Aa1@xyz")
        assert "at least 8 characters" in exc.value.detail

    def test_no_uppercase_raises(self):
        with pytest.raises(HTTPException) as exc:
            validate_password("nostrongl0wer@")
        assert "one uppercase letter" in exc.value.detail

    def test_no_lowercase_raises(self):
        with pytest.raises(HTTPException) as exc:
            validate_password("ALLCAPS123@!")
        assert "one lowercase letter" in exc.value.detail

    def test_no_digit_raises(self):
        with pytest.raises(HTTPException) as exc:
            validate_password("NoDigits@Here!")
        assert "one digit" in exc.value.detail

    def test_no_special_char_raises(self):
        with pytest.raises(HTTPException) as exc:
            validate_password("NoSpecial1Char")
        assert "one special character" in exc.value.detail

    def test_common_password_raises(self):
        with pytest.raises(HTTPException) as exc:
            validate_password("P@ssw0rd")  # lowered = "p@ssw0rd" which is in common set
        assert "common password" in exc.value.detail

    def test_exact_common_password_raises(self):
        with pytest.raises(HTTPException) as exc:
            validate_password("P@ssw0rd")  # lowercase "p@ssw0rd" is in common set
        assert "common password" in exc.value.detail

    def test_custom_min_length(self):
        with pytest.raises(HTTPException) as exc:
            validate_password("Short1@a", min_length=12)
        assert "at least 12 characters" in exc.value.detail

    def test_multiple_failures_combined(self):
        with pytest.raises(HTTPException) as exc:
            validate_password("abc")
        detail = exc.value.detail
        assert "at least 8 characters" in detail
        assert "one uppercase letter" in detail
        assert "one digit" in detail


class TestPasswordStrength:
    def test_strong_password(self):
        result = validate_password_strength("MyStr0ng@Pass!")
        assert result["strength"] == "strong"
        assert result["passed"] == result["total"]

    def test_weak_password(self):
        result = validate_password_strength("abc")
        assert result["strength"] == "weak"

    def test_medium_password(self):
        result = validate_password_strength("Abcdefg1")
        # has uppercase, lowercase, digit, min_length, not_common = 5/6
        assert result["strength"] in ("medium", "strong")

    def test_checks_dict_keys(self):
        result = validate_password_strength("x")
        checks = result["checks"]
        expected_keys = {
            "min_length", "has_uppercase", "has_lowercase",
            "has_digit", "has_special", "not_common",
        }
        assert set(checks.keys()) == expected_keys
