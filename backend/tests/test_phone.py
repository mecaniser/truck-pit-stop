from __future__ import annotations

from app.core.phone import normalize_phone


class TestNormalizePhone:
    def test_strips_formatting(self):
        assert normalize_phone("(555) 123-4567") == "5551234567"

    def test_digits_only_passthrough(self):
        assert normalize_phone("5551234567") == "5551234567"

    def test_none_returns_none(self):
        assert normalize_phone(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_phone("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_phone("   ") is None

    def test_non_digit_only_returns_none(self):
        assert normalize_phone("no-digits-here!") is None

    def test_international_prefix(self):
        assert normalize_phone("+1 (555) 123-4567") == "15551234567"

    def test_mixed_separators(self):
        assert normalize_phone("555.123.4567") == "5551234567"
