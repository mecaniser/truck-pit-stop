"""Sender authority comes from proven conversation evidence, never a chooser."""
from dataclasses import dataclass
import re
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.sms_message import SMSMessage, SMSMessageDirection as Direction, SMSDeliveryStatus as Status
from app.db.models.callrail import CallRailConversation
from app.services import callrail_service as cr, tenant_sms_routing as routing
from app.services.messaging_service import _normalize_for_twilio as phone


def deny(code='reply_route_unavailable'):
    raise HTTPException(409, detail={'code':code,'message':'This conversation number needs review.'})


@dataclass(frozen=True)
class Route:
    provider: str
    sender_number: str
    mode: str
    callrail: object = None
    twilio: object = None

    def fingerprint(self):
        if self.callrail:
            c=self.callrail
            return ('callrail',c.binding_id,c.account_id,c.company_id,c.tracker_id,c.sender_phone)
        if self.twilio:
            c=self.twilio
            return ('twilio',c.binding_id,c.account_sid,c.messaging_service_sid,c.sender_phone)
        return ('twilio',self.sender_number)

    def context(self):
        return dict(sms_provider=self.provider,sender_number=self.sender_number,sender_mode=self.mode,
            sender_selection_allowed=False,selected_sender_id=str(self.callrail.binding_id) if self.callrail else 'twilio')


async def exact_callrail(db, tenant, thread, binding_id):
    mapping=await db.scalar(select(CallRailConversation).where(CallRailConversation.tenant_id==tenant.id,
        CallRailConversation.thread_id==thread.id,CallRailConversation.binding_id==binding_id,
        CallRailConversation.deleted_at.is_(None)).execution_options(populate_existing=True))
    if not mapping:deny()
    return await cr._context_for_mapping(db,mapping,allow_opt_out=True)


async def evidence_route(db,tenant,thread,message,recipient,mode):
    if message.customer_id != thread.customer_id or message.thread_id != thread.id or message.tenant_id != tenant.id:
        deny()
    incoming=message.direction==Direction.INBOUND
    sender=phone(message.to_number if incoming else message.from_number)
    remote=phone(message.from_number if incoming else message.to_number)
    if remote!=recipient or not re.fullmatch(r'\+[1-9]\d{7,14}',sender):deny()
    if message.provider=='callrail':
        if not re.fullmatch(r'(SCI[A-Za-z0-9]{1,77}|[1-9][0-9]*)', message.provider_message_id or '') or not message.callrail_binding_id or message.binding_id or message.twilio_message_sid:deny()
        c=await exact_callrail(db,tenant,thread,message.callrail_binding_id)
        if (c.account_id,c.sender_phone,c.customer_phone)!=(message.provider_account_id,sender,recipient):deny()
        return Route('callrail',sender,mode,callrail=c)
    if message.provider not in (None,'twilio') or message.callrail_binding_id or message.provider_account_id:deny()
    if not re.fullmatch(r'SM[0-9a-fA-F]{32}',message.twilio_message_sid or ''):deny()
    if message.binding_id:
        if not routing.enabled():deny()
        c=await routing.resolve(db,tenant.id,message.binding_id)
        if (c.account_sid,c.messaging_service_sid,c.sender_phone)!=(message.twilio_account_sid,message.messaging_service_sid,sender):deny()
        return Route('twilio',sender,mode,twilio=c)
    if message.twilio_account_sid or message.messaging_service_sid:deny()
    if routing.enabled() or sender!=phone(tenant.sms_phone_number):deny()
    await routing.require_legacy_tenant(db,tenant.id)
    return Route('twilio',sender,mode)


async def resolve(db,tenant,thread,recipient):
    try:
        if thread.thread_kind=='inquiry':
            c=await exact_callrail(db,tenant,thread,thread.inquiry_binding_id)
            return Route('callrail',c.sender_phone,'reply',callrail=c)
        if thread.thread_kind!='customer' or not thread.customer_id:deny()
        rows=list((await db.scalars(select(SMSMessage).where(SMSMessage.tenant_id==tenant.id,
            SMSMessage.thread_id==thread.id,SMSMessage.deleted_at.is_(None)).order_by(SMSMessage.created_at.desc(),SMSMessage.id.desc()))).all())
        inbound=[m for m in rows if m.direction==Direction.INBOUND]
        candidates=inbound or [m for m in rows if m.direction==Direction.OUTBOUND and m.delivery_status in (Status.SENT,Status.DELIVERED)]
        if candidates:
            newest=[m for m in candidates if m.created_at==candidates[0].created_at]
            routes=[await evidence_route(db,tenant,thread,m,recipient,'reply') for m in newest]
            if len({r.fingerprint() for r in routes})!=1:deny('reply_route_ambiguous')
            return routes[0]
        # An explicit shop default can initiate; historical UI selection has no authority.
        if routing.enabled():
            c=await routing.resolve(db,tenant.id)
            return Route('twilio',c.sender_phone,'initiation',twilio=c)
        await routing.require_legacy_tenant(db,tenant.id)
        sender=phone(tenant.sms_phone_number)
        if not re.fullmatch(r'\+[1-9]\d{7,14}',sender):deny()
        return Route('twilio',sender,'initiation')
    except HTTPException as exc:
        if isinstance(exc.detail,dict) and exc.detail.get('code')=='reply_route_ambiguous':raise
        deny()
