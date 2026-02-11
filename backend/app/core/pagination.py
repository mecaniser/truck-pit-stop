from __future__ import annotations

from typing import Any, Sequence

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def build_paginated_payload(items: Sequence[Any], total: int, skip: int, limit: int) -> dict[str, Any]:
    """Build a standard offset pagination payload."""
    return {
        "items": list(items),
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(items)) < total,
    }


def paginated_or_list(items: Sequence[Any], total: int, skip: int, limit: int, paginated: bool):
    """Return legacy list by default, or an envelope when paginated=true."""
    if not paginated:
        return list(items)

    payload = build_paginated_payload(items=items, total=total, skip=skip, limit=limit)
    return JSONResponse(content=jsonable_encoder(payload))
