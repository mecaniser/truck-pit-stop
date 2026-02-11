from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any, Callable

import pytest


# Ensure `app` package resolves from backend/.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Minimal config required to import app settings in test environment.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.ops: list[Callable[[], Any]] = []

    def zremrangebyscore(self, key: str, min_score: int, max_score: int) -> "FakePipeline":
        def _op() -> int:
            zset = self.redis.sorted_sets.setdefault(key, {})
            members_to_remove = [member for member, score in zset.items() if min_score <= score <= max_score]
            for member in members_to_remove:
                zset.pop(member, None)
            return len(members_to_remove)

        self.ops.append(_op)
        return self

    def zadd(self, key: str, mapping: dict[str, int]) -> "FakePipeline":
        def _op() -> int:
            zset = self.redis.sorted_sets.setdefault(key, {})
            added = 0
            for member, score in mapping.items():
                if member not in zset:
                    added += 1
                zset[member] = score
            return added

        self.ops.append(_op)
        return self

    def zcard(self, key: str) -> "FakePipeline":
        def _op() -> int:
            return len(self.redis.sorted_sets.setdefault(key, {}))

        self.ops.append(_op)
        return self

    def expire(self, key: str, ttl: int) -> "FakePipeline":
        def _op() -> bool:
            return True

        self.ops.append(_op)
        return self

    async def execute(self) -> list[Any]:
        return [op() for op in self.ops]


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.sorted_sets: dict[str, dict[str, int]] = {}

    async def get(self, key: str):
        return self.kv.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        return True

    async def setex(self, key: str, ttl: int, value: str):
        self.kv[key] = value
        return True

    async def delete(self, key: str):
        self.kv.pop(key, None)
        return 1

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()
