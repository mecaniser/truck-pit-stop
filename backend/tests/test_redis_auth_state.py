from __future__ import annotations

import pytest

from app.core import redis as redis_module


class _Redis:
    def __init__(self, values):
        self.values = values
        self.calls = []

    async def mget(self, keys):
        self.calls.append(keys)
        return [self.values.get(key) for key in keys]


@pytest.mark.asyncio
async def test_auth_token_state_uses_one_redis_command(monkeypatch):
    redis = _Redis(
        {
            "token_blacklist:revoked-jti": "1",
            "token_version:user-1": "4",
        }
    )

    async def _get_redis():
        return redis

    monkeypatch.setattr(redis_module, "get_redis", _get_redis)

    state = await redis_module.get_auth_token_state("revoked-jti", "user-1")

    assert state == (True, 4)
    assert redis.calls == [["token_blacklist:revoked-jti", "token_version:user-1"]]


@pytest.mark.asyncio
async def test_auth_token_state_handles_access_token_without_jti(monkeypatch):
    redis = _Redis({"token_version:user-1": "2"})

    async def _get_redis():
        return redis

    monkeypatch.setattr(redis_module, "get_redis", _get_redis)

    state = await redis_module.get_auth_token_state(None, "user-1")

    assert state == (False, 2)
    assert redis.calls == [["token_version:user-1"]]
