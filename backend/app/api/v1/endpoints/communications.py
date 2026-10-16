from __future__ import annotations
import hashlib
import json
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, BackgroundTasks, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, and_, or_
from app.core.dependencies import get_current_active_user, get_db
from app.db.session import AsyncSessionLocal
from app.db.models.user import User
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage
from app.db.models.communication import ConversationWorkflow, ConversationReadWatermark, SMSSendOperation
from app.services import communications_service as service

router = APIRouter()


class WorkflowPatch(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal['open', 'resolved'] | None = None
    assignee_id: UUID | None = None


class ReadRequest(BaseModel):
    through_message_id: UUID


class SendRequest(BaseModel):
    channel_account_id: UUID
    contact_identity_id: UUID
    body: str = Field(min_length=1, max_length=1600)
    expected_version: int = Field(ge=1)

    @field_validator('body')
    @classmethod
    def body_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Message cannot be blank')
        return value.strip()


async def dispatch_background(operation_id, sender):
    async with AsyncSessionLocal() as db:
        try:
            await service.dispatch_operation(db, operation_id, sender)
        except Exception:
            # Durable dispatching is held, never retried; recovery marks it unknown.
            await db.rollback()


async def messages_page(db, tenant_id, thread_id, limit=50, cursor=None):
    binding = f'{tenant_id}:{thread_id}:messages'
    decoded = service.cursor_decode(cursor, binding)
    query = select(SMSMessage).where(SMSMessage.tenant_id == tenant_id, SMSMessage.thread_id == thread_id, SMSMessage.deleted_at.is_(None))
    if decoded:
        dt, row_id = decoded
        query = query.where(or_(SMSMessage.created_at < dt, and_(SMSMessage.created_at == dt, SMSMessage.id < row_id)))
    rows = list((await db.execute(query.order_by(SMSMessage.created_at.desc(), SMSMessage.id.desc()).limit(limit + 1))).scalars())
    more = len(rows) > limit
    rows = rows[:limit]
    cursor = service.cursor_encode(binding, rows[-1].created_at, rows[-1].id) if rows and more else None
    return dict(items=[await service.message_json(db, m) for m in reversed(rows)], has_more=more, next_cursor=cursor)


@router.get('/bootstrap')
async def bootstrap(db=Depends(get_db), user=Depends(get_current_active_user), sender=Depends(service.get_sms_sender)):
    tenant = await service.authorize(db, user)
    users = (await db.execute(select(User).where(User.tenant_id == tenant.id, User.is_active.is_(True), User.deleted_at.is_(None)))).scalars().all()
    return dict(tenant_id=tenant.id, user_id=user.id, delivery_mode=sender.mode, assignees=[dict(id=u.id, name=f'{u.first_name} {u.last_name}') for u in users if service.permitted(u)], channels=[dict(channel='sms', connected=bool(tenant.sms_enabled and tenant.sms_phone_number and getattr(sender, 'ready', True))), dict(channel='whatsapp', connected=False), dict(channel='telegram', connected=False)])


@router.get('/conversations')
async def list_conversations(limit: int = Query(100, ge=1, le=100), cursor: str | None = None, channel: str | None = None, status: Literal['open', 'resolved'] | None = None, search: str = Query('', max_length=200), db=Depends(get_db), user=Depends(get_current_active_user), sender=Depends(service.get_sms_sender)):
    tenant = await service.authorize(db, user)
    binding = hashlib.sha256(json.dumps([str(tenant.id), channel, status, search]).encode()).hexdigest()
    decoded = service.cursor_decode(cursor, binding)
    if channel and channel != 'sms':
        return dict(items=[], has_more=False, next_cursor=None)
    ordering = func.coalesce(MessageThread.last_message_at, MessageThread.created_at)
    query = select(MessageThread).join(Customer, and_(Customer.id == MessageThread.customer_id, Customer.tenant_id == tenant.id)).outerjoin(ConversationWorkflow, and_(ConversationWorkflow.thread_id == MessageThread.id, ConversationWorkflow.tenant_id == tenant.id)).where(MessageThread.tenant_id == tenant.id, MessageThread.deleted_at.is_(None), MessageThread.archived_at.is_(None), Customer.deleted_at.is_(None))
    if status:
        query = query.where(func.coalesce(ConversationWorkflow.status, 'open') == status)
    if search:
        term = '%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        body_match = select(SMSMessage.id).where(SMSMessage.tenant_id == tenant.id, SMSMessage.thread_id == MessageThread.id, SMSMessage.deleted_at.is_(None), SMSMessage.body.ilike(term)).exists()
        query = query.where(or_(func.concat(Customer.first_name, ' ', Customer.last_name).ilike(term), Customer.company_name.ilike(term), Customer.phone.ilike(term), body_match))
    if decoded:
        dt, row_id = decoded
        query = query.where(or_(ordering < dt, and_(ordering == dt, MessageThread.id < row_id)))
    rows = list((await db.execute(query.order_by(ordering.desc(), MessageThread.id.desc()).limit(limit + 1))).scalars())
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = service.cursor_encode(binding, rows[-1].last_message_at or rows[-1].created_at, rows[-1].id) if rows and more else None
    return dict(items=[await service.conversation_json(db, tenant, user, t, sender) for t in rows], has_more=more, next_cursor=next_cursor)


@router.get('/conversations/{conversation_id}')
async def conversation(conversation_id: UUID, db=Depends(get_db), user=Depends(get_current_active_user), sender=Depends(service.get_sms_sender)):
    tenant = await service.authorize(db, user)
    thread = await service.thread_for(db, tenant.id, conversation_id)
    result = await service.conversation_json(db, tenant, user, thread, sender)
    page = await messages_page(db, tenant.id, thread.id)
    result.update(messages=page['items'], messages_has_more=page['has_more'], messages_next_cursor=page['next_cursor'])
    return result


@router.get('/conversations/{conversation_id}/messages')
async def messages(conversation_id: UUID, limit: int = Query(50, ge=1, le=100), cursor: str | None = None, db=Depends(get_db), user=Depends(get_current_active_user)):
    tenant = await service.authorize(db, user)
    thread = await service.thread_for(db, tenant.id, conversation_id)
    return await messages_page(db, tenant.id, thread.id, limit, cursor)


@router.patch('/conversations/{conversation_id}')
async def patch(conversation_id: UUID, body: WorkflowPatch, db=Depends(get_db), user=Depends(get_current_active_user), sender=Depends(service.get_sms_sender)):
    tenant = await service.authorize(db, user)
    thread = await service.thread_for(db, tenant.id, conversation_id, lock=True)
    wf = await service.workflow(db, thread)
    if wf.version != body.expected_version:
        service.fail('stale_version', 'Conversation changed. Refresh and try again.')
    if 'assignee_id' in body.model_fields_set:
        if body.assignee_id:
            assignee = await db.scalar(select(User).where(User.id == body.assignee_id, User.tenant_id == tenant.id))
            if not service.permitted(assignee):
                service.fail('not_found', 'Assignee not found.', 404)
        wf.assignee_id = body.assignee_id
    if body.status:
        wf.status = body.status
    wf.version += 1
    await db.commit()
    return await service.conversation_json(db, tenant, user, thread, sender)


@router.post('/conversations/{conversation_id}/read')
async def mark_read(conversation_id: UUID, body: ReadRequest, db=Depends(get_db), user=Depends(get_current_active_user)):
    tenant = await service.authorize(db, user)
    thread = await service.thread_for(db, tenant.id, conversation_id, lock=True)
    message = await db.scalar(select(SMSMessage).where(SMSMessage.id == body.through_message_id, SMSMessage.tenant_id == tenant.id, SMSMessage.thread_id == thread.id, SMSMessage.deleted_at.is_(None)))
    if not message:
        service.fail('not_found', 'Message not found.', 404)
    mark = await db.scalar(select(ConversationReadWatermark).where(ConversationReadWatermark.tenant_id == tenant.id, ConversationReadWatermark.thread_id == thread.id, ConversationReadWatermark.user_id == user.id))
    if not mark:
        mark = ConversationReadWatermark(tenant_id=tenant.id, thread_id=thread.id, user_id=user.id, through_created_at=message.created_at, through_message_id=message.id)
        db.add(mark)
    elif (message.created_at, message.id) > (mark.through_created_at, mark.through_message_id):
        mark.through_created_at = message.created_at
        mark.through_message_id = message.id
    await db.commit()
    return dict(unread_count=await service.unread_count(db, thread, user.id))


@router.post('/conversations/{conversation_id}/send-operations')
async def send(conversation_id: UUID, body: SendRequest, response: Response, background_tasks: BackgroundTasks, idempotency_key: str = Header(min_length=1, max_length=128), db=Depends(get_db), user=Depends(get_current_active_user), sender=Depends(service.get_sms_sender)):
    tenant = await service.authorize(db, user)
    if not idempotency_key.strip():
        service.fail('invalid_key', 'Idempotency-Key is required.', 422)
    op, replayed = await service.create_operation(db, user, tenant, conversation_id, body, idempotency_key, sender)
    result = await service.operation_json(db, op, replayed)
    response.status_code = 200 if replayed else 202
    if not replayed:
        background_tasks.add_task(dispatch_background, op.id, sender)
    return result


@router.get('/send-operations/{operation_id}')
async def get_operation(operation_id: UUID, db=Depends(get_db), user=Depends(get_current_active_user)):
    tenant = await service.authorize(db, user)
    op = await db.scalar(select(SMSSendOperation).where(SMSSendOperation.id == operation_id, SMSSendOperation.tenant_id == tenant.id))
    if not op:
        service.fail('not_found', 'Send operation not found.', 404)
    await service.thread_for(db, tenant.id, op.thread_id)
    return await service.operation_json(db, op)
