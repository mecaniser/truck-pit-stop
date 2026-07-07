from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user, get_db
from app.core.websocket import broadcast_sms_thread_event
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage, SMSMessageSource
from app.db.models.user import User, UserRole
from app.schemas.message import (
    CursorPageMessageThreads,
    CursorPageSMSMessages,
    SMSMessageResponse,
    SendSMSRequest,
    StartThreadRequest,
    ThreadActionResponse,
    UnreadSMSCountResponse,
)
from app.services.messaging_service import enforce_tenant_send_rate_limit, send_sms_with_tracking

router = APIRouter()


def require_staff_user():
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        # Owner/admin/receptionist/mechanic have messaging by role; other roles
        # (notably fleet managers) need the can_access_messaging grant.
        has_role_access = current_user.role in (
            UserRole.GARAGE_OWNER,
            UserRole.GARAGE_ADMIN,
            UserRole.RECEPTIONIST,
            UserRole.MECHANIC,
        )
        if not (has_role_access or current_user.can_access_messaging):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return role_checker


def require_manager_user():
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shop owner/admin permissions required")
        return current_user

    return role_checker


def _encode_cursor(dt: datetime, entity_id: UUID) -> str:
    return f"{dt.isoformat()}|{entity_id}"


def _decode_cursor(cursor: Optional[str]) -> tuple[Optional[datetime], Optional[UUID]]:
    if not cursor:
        return None, None
    try:
        raw_dt, raw_id = cursor.split("|", 1)
        return datetime.fromisoformat(raw_dt), UUID(raw_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor")


async def _get_customer_for_tenant(db: AsyncSession, tenant_id: UUID, customer_id: UUID) -> Customer:
    result = await db.execute(
        select(Customer).where(
            and_(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id,
            )
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.get("/threads", response_model=CursorPageMessageThreads)
async def list_message_threads(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_user()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    cursor_dt, cursor_id = _decode_cursor(cursor)
    conditions = [
        MessageThread.tenant_id == current_user.tenant_id,
        MessageThread.deleted_at.is_(None),
    ]
    if not include_archived:
        conditions.append(MessageThread.archived_at.is_(None))

    query = (
        select(MessageThread)
        .options(selectinload(MessageThread.customer))
        .where(and_(*conditions))
    )
    if cursor_dt and cursor_id:
        query = query.where(
            or_(
                MessageThread.last_message_at < cursor_dt,
                and_(MessageThread.last_message_at == cursor_dt, MessageThread.id < cursor_id),
            )
        )

    result = await db.execute(
        query.order_by(MessageThread.last_message_at.desc().nullslast(), MessageThread.id.desc()).limit(limit + 1)
    )
    rows = result.scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows and rows[-1].last_message_at:
        next_cursor = _encode_cursor(rows[-1].last_message_at, rows[-1].id)

    return CursorPageMessageThreads(
        items=rows,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/unread-summary", response_model=UnreadSMSCountResponse)
async def get_unread_sms_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_user()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    result = await db.execute(
        select(func.coalesce(func.sum(MessageThread.unread_count_staff), 0)).where(
            and_(
                MessageThread.tenant_id == current_user.tenant_id,
                MessageThread.deleted_at.is_(None),
                MessageThread.archived_at.is_(None),
            )
        )
    )
    unread_total = int(result.scalar() or 0)
    return UnreadSMSCountResponse(unread_count_staff=unread_total)


@router.get("/threads/{thread_id}/messages", response_model=CursorPageSMSMessages)
async def list_thread_messages(
    thread_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None, description="Oldest loaded message cursor"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_user()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    result = await db.execute(
        select(MessageThread).where(
            and_(
                MessageThread.id == thread_id,
                MessageThread.tenant_id == current_user.tenant_id,
                MessageThread.deleted_at.is_(None),
            )
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    cursor_dt, cursor_id = _decode_cursor(cursor)
    query = select(SMSMessage).where(
        and_(
            SMSMessage.tenant_id == current_user.tenant_id,
            SMSMessage.thread_id == thread_id,
            SMSMessage.deleted_at.is_(None),
        )
    )
    if cursor_dt and cursor_id:
        query = query.where(
            or_(
                SMSMessage.created_at < cursor_dt,
                and_(SMSMessage.created_at == cursor_dt, SMSMessage.id < cursor_id),
            )
        )

    result = await db.execute(query.order_by(SMSMessage.created_at.desc(), SMSMessage.id.desc()).limit(limit + 1))
    rows = result.scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows = list(reversed(rows))

    if thread.unread_count_staff:
        thread.unread_count_staff = 0
        await db.commit()
        await broadcast_sms_thread_event(
            tenant_id=str(current_user.tenant_id),
            thread_id=str(thread.id),
            customer_id=str(thread.customer_id),
            unread_count_staff=0,
            last_message_at=thread.last_message_at.isoformat() if thread.last_message_at else None,
            last_message_preview=thread.last_message_preview,
        )

    next_cursor = None
    if has_more and rows:
        oldest = rows[0]
        next_cursor = _encode_cursor(oldest.created_at, oldest.id)

    return CursorPageSMSMessages(
        items=rows,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/send", response_model=SMSMessageResponse)
async def send_message(
    body: SendSMSRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_user()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    within_limit = await enforce_tenant_send_rate_limit(current_user.tenant_id, limit=30, window_seconds=60)
    if not within_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="SMS send rate limit exceeded for this tenant",
        )

    customer = await _get_customer_for_tenant(db, current_user.tenant_id, body.customer_id)
    if not customer.phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer phone number is required")

    if body.thread_id:
        result = await db.execute(
            select(MessageThread).where(
                and_(
                    MessageThread.id == body.thread_id,
                    MessageThread.tenant_id == current_user.tenant_id,
                    MessageThread.customer_id == body.customer_id,
                    MessageThread.deleted_at.is_(None),
                )
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found for customer")

    _, sms_message, _ = await send_sms_with_tracking(
        db=db,
        tenant_id=current_user.tenant_id,
        to=customer.phone,
        body=body.body.strip(),
        template_name="manual_sms",
        customer_id=customer.id,
        source=SMSMessageSource.MANUAL,
        created_by_user_id=current_user.id,
        raise_on_failure=True,
    )
    if not sms_message:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create SMS message")
    return SMSMessageResponse.model_validate(sms_message)


@router.post("/threads/new", response_model=SMSMessageResponse)
async def start_thread(
    body: StartThreadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_user()),
):
    return await send_message(
        body=SendSMSRequest(customer_id=body.customer_id, body=body.body, thread_id=None),
        db=db,
        current_user=current_user,
    )


@router.post("/threads/{thread_id}/archive", response_model=ThreadActionResponse)
async def archive_thread(
    thread_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_user()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    result = await db.execute(
        select(MessageThread).where(
            and_(
                MessageThread.id == thread_id,
                MessageThread.tenant_id == current_user.tenant_id,
                MessageThread.deleted_at.is_(None),
            )
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    thread.archived_at = datetime.now(timezone.utc)
    thread.archived_by_user_id = current_user.id
    thread.unread_count_staff = 0
    await db.commit()
    await db.refresh(thread)

    await broadcast_sms_thread_event(
        tenant_id=str(current_user.tenant_id),
        thread_id=str(thread.id),
        customer_id=str(thread.customer_id),
        unread_count_staff=0,
        last_message_at=thread.last_message_at.isoformat() if thread.last_message_at else None,
        last_message_preview=thread.last_message_preview,
        action="archived",
    )

    return ThreadActionResponse(thread_id=thread.id, message="Thread archived")


@router.post("/threads/{thread_id}/unarchive", response_model=ThreadActionResponse)
async def unarchive_thread(
    thread_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff_user()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    result = await db.execute(
        select(MessageThread).where(
            and_(
                MessageThread.id == thread_id,
                MessageThread.tenant_id == current_user.tenant_id,
                MessageThread.deleted_at.is_(None),
            )
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    thread.archived_at = None
    thread.archived_by_user_id = None
    await db.commit()
    await db.refresh(thread)

    await broadcast_sms_thread_event(
        tenant_id=str(current_user.tenant_id),
        thread_id=str(thread.id),
        customer_id=str(thread.customer_id),
        unread_count_staff=thread.unread_count_staff,
        last_message_at=thread.last_message_at.isoformat() if thread.last_message_at else None,
        last_message_preview=thread.last_message_preview,
        action="unarchived",
    )

    return ThreadActionResponse(thread_id=thread.id, message="Thread unarchived")


@router.delete("/threads/{thread_id}", response_model=ThreadActionResponse)
async def delete_thread(
    thread_id: UUID,
    hard_delete: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_user()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    result = await db.execute(
        select(MessageThread)
        .options(selectinload(MessageThread.messages))
        .where(
            and_(
                MessageThread.id == thread_id,
                MessageThread.tenant_id == current_user.tenant_id,
                MessageThread.deleted_at.is_(None),
            )
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    deleted_thread_id = thread.id
    deleted_customer_id = thread.customer_id
    now = datetime.now(timezone.utc)
    if hard_delete:
        await db.delete(thread)
        action = "hard_deleted"
        message = "Thread permanently deleted"
    else:
        thread.deleted_at = now
        thread.unread_count_staff = 0
        for sms in thread.messages:
            sms.deleted_at = now
        action = "soft_deleted"
        message = "Thread deleted from inbox"
    await db.commit()

    await broadcast_sms_thread_event(
        tenant_id=str(current_user.tenant_id),
        thread_id=str(deleted_thread_id),
        customer_id=str(deleted_customer_id),
        unread_count_staff=0,
        last_message_at=None,
        last_message_preview=None,
        action=action,
    )

    return ThreadActionResponse(thread_id=deleted_thread_id, message=message)
