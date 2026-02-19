from __future__ import annotations

import time

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    get_token_expiry_seconds,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        plain = "Str0ng@Pass!"
        hashed = get_password_hash(plain)
        assert hashed != plain
        assert verify_password(plain, hashed)

    def test_wrong_password_fails(self):
        hashed = get_password_hash("CorrectHorse@1")
        assert not verify_password("WrongHorse@1", hashed)

    def test_different_hashes_for_same_password(self):
        h1 = get_password_hash("Same@Pass1")
        h2 = get_password_hash("Same@Pass1")
        assert h1 != h2  # bcrypt salt differs


class TestAccessToken:
    def test_create_and_decode(self):
        token = create_access_token({"sub": "user-123"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"

    def test_contains_jti_and_version(self):
        token = create_access_token({"sub": "u"}, token_version=5)
        payload = decode_token(token)
        assert "jti" in payload
        assert payload["ver"] == 5

    def test_has_expiration(self):
        token = create_access_token({"sub": "u"})
        payload = decode_token(token)
        assert "exp" in payload
        assert payload["exp"] > time.time()


class TestRefreshToken:
    def test_create_and_decode(self):
        token = create_refresh_token({"sub": "user-456"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"

    def test_remember_me_flag_persisted(self):
        token = create_refresh_token({"sub": "u"}, remember_me=True)
        payload = decode_token(token)
        assert payload["rem"] is True

    def test_non_remember_me(self):
        token = create_refresh_token({"sub": "u"}, remember_me=False)
        payload = decode_token(token)
        assert payload["rem"] is False


class TestDecodeToken:
    def test_invalid_token_returns_none(self):
        assert decode_token("not.a.valid.token") is None

    def test_empty_string_returns_none(self):
        assert decode_token("") is None

    def test_tampered_token_returns_none(self):
        token = create_access_token({"sub": "u"})
        tampered = token[:-4] + "XXXX"
        assert decode_token(tampered) is None


class TestTokenExpirySeconds:
    def test_valid_token_returns_positive(self):
        token = create_access_token({"sub": "u"})
        remaining = get_token_expiry_seconds(token)
        assert remaining > 0

    def test_invalid_token_returns_zero(self):
        assert get_token_expiry_seconds("garbage") == 0
