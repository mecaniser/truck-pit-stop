"""DB-076: the endpoint a long-lived tab polls to learn it is stale."""
import json

import pytest

from app.api.v1.endpoints import build_version as bv


@pytest.mark.asyncio
async def test_reports_the_built_sha(client, tmp_path, monkeypatch):
    stamp = tmp_path / "build-version.json"
    stamp.write_text(json.dumps({"sha": "a" * 40, "built_at": "2026-09-23T12:00:00Z"}))
    monkeypatch.setattr(bv, "_stamp_path", lambda: stamp)

    r = await client.get("/build-version")
    assert r.status_code == 200
    assert r.json() == {"sha": "a" * 40, "built_at": "2026-09-23T12:00:00Z"}


@pytest.mark.asyncio
async def test_sends_no_store_so_a_device_cannot_serve_a_cached_version(client, tmp_path, monkeypatch):
    stamp = tmp_path / "build-version.json"
    stamp.write_text(json.dumps({"sha": "b" * 40, "built_at": "2026-09-23T12:00:00Z"}))
    monkeypatch.setattr(bv, "_stamp_path", lambda: stamp)

    r = await client.get("/build-version")
    assert "no-store" in r.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_accepts_head_because_the_static_routes_are_get_only(client, tmp_path, monkeypatch):
    stamp = tmp_path / "build-version.json"
    stamp.write_text(json.dumps({"sha": "c" * 40, "built_at": "2026-09-23T12:00:00Z"}))
    monkeypatch.setattr(bv, "_stamp_path", lambda: stamp)

    r = await client.head("/build-version")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reports_unknown_rather_than_failing_when_no_build_stamp_exists(client, tmp_path, monkeypatch):
    monkeypatch.setattr(bv, "_stamp_path", lambda: tmp_path / "absent.json")

    r = await client.get("/build-version")
    assert r.status_code == 200
    assert r.json() == {"sha": None, "built_at": None}


@pytest.mark.asyncio
async def test_reports_unknown_rather_than_failing_on_a_corrupt_stamp(client, tmp_path, monkeypatch):
    stamp = tmp_path / "build-version.json"
    stamp.write_text("not json{")
    monkeypatch.setattr(bv, "_stamp_path", lambda: stamp)

    r = await client.get("/build-version")
    assert r.status_code == 200
    assert r.json() == {"sha": None, "built_at": None}


@pytest.mark.asyncio
async def test_needs_no_authentication(client, tmp_path, monkeypatch):
    """A signed-out long-lived tab still has to learn that it is stale."""
    stamp = tmp_path / "build-version.json"
    stamp.write_text(json.dumps({"sha": "d" * 40, "built_at": "2026-09-23T12:00:00Z"}))
    monkeypatch.setattr(bv, "_stamp_path", lambda: stamp)

    r = await client.get("/build-version")  # client sends no auth header
    assert r.status_code == 200


def test_stamp_path_matches_where_the_app_serves_the_frontend():
    """The unmocked path must point at the same dist/ main.py serves.

    Every other test monkeypatches _stamp_path, so a wrong real path would
    otherwise reach production reporting a permanently unknown version.
    """
    from app import main

    assert bv._stamp_path() == main.frontend_dist / "build-version.json"
