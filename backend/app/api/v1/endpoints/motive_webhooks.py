# ruff: noqa: B008
"""Public signed ingress. Acknowledge only after a durable, bounded receipt."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.services.motive_ingestion import ingest_webhook

router = APIRouter()
MAX_BODY = 256 * 1024


@router.post("/{webhook_id}/{generation}")
async def receive(
    webhook_id: UUID,
    generation: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        async with asyncio.timeout(2.5):
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > MAX_BODY:
                    raise HTTPException(413, "Webhook body too large")
            await ingest_webhook(
                db,
                webhook_id,
                generation,
                bytes(raw),
                request.headers.get("X-KT-Webhook-Signature", ""),
            )
        return {"received": True}
    except (TimeoutError, SQLAlchemyError):
        await db.rollback()
        raise HTTPException(503, "Webhook receipt unavailable") from None
