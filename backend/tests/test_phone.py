from __future__ import annotations

from app.core.phone import format_phone_display, normalize_phone


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


class TestFormatPhoneDisplay:
    def test_formats_ten_digit_us_number(self):
        assert format_phone_display("7045550199") == "(704) 555-0199"

    def test_formats_us_number_with_country_code(self):
        assert format_phone_display("17045550199") == "(704) 555-0199"

    def test_keeps_non_us_number_as_entered(self):
        assert format_phone_display("+44 20 7946 0958") == "+44 20 7946 0958"
