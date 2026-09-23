"""DB-076: build identity for a long-lived tab to poll.

A tab parked for days keeps running the build it loaded and never asks the
server for anything that would reveal a newer one. This endpoint is the one
fact it needs. See the DB-076 contract in docs/PROJECT_BOARD.md.
"""
import json
from pathlib import Path

from fastapi import APIRouter, Response

router = APIRouter()


def _stamp_path() -> Path:
    """The stamp the frontend build writes into its own dist/."""
    return Path(__file__).resolve().parents[4] / "frontend" / "dist" / "build-version.json"


def _read_stamp() -> dict[str, str | None]:
    """Never raise: an unbuilt or corrupt stamp must not trigger reloads.

    The client treats a null sha as "unknown" and does nothing, so a
    misconfigured deploy degrades to silence rather than to a reload loop.
    """
    unknown: dict[str, str | None] = {"sha": None, "built_at": None}
    try:
        raw = json.loads(_stamp_path().read_text())
    except (OSError, ValueError):
        return unknown
    if not isinstance(raw, dict):
        return unknown
    sha, built_at = raw.get("sha"), raw.get("built_at")
    if not isinstance(sha, str) or not isinstance(built_at, str):
        return unknown
    return {"sha": sha, "built_at": built_at}


# HEAD as well as GET: the public/ asset routes in main.py are GET-only, which
# is why HEAD /robots.txt answers 405. A polling client must not trip over it.
@router.api_route("/build-version", methods=["GET", "HEAD"], include_in_schema=False)
async def build_version(response: Response) -> dict[str, str | None]:
    # Mandatory: FileResponse sets no Cache-Control and index.html none at all,
    # so without this a device can serve back the very version it already has.
    response.headers["Cache-Control"] = "no-store"
    return _read_stamp()
