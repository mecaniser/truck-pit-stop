"""Synthetic-only MMS browser fixture; never forwards a provider request."""
import io
import os
from types import SimpleNamespace

import httpx
from PIL import Image, ImageDraw
from sqlalchemy import select
from communications_local_app import app
from app.core.config import settings
from app.db.models.sms_message import SMSMessage
from app.db.session import AsyncSessionLocal
from app.services import callrail_media, callrail_service

if ('@127.0.0.1:55460/communications_local_inline_mms_20261022' not in settings.DATABASE_URL
    or any(getattr(settings, key) for key in (
        'SMS_TENANT_ROUTING_ENABLED', 'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED'))):
    raise RuntimeError('Dedicated MMS synthetic runtime with all SMS flags off required')
os.environ['CALLRAIL_LOCAL_API'] = 'synthetic-local-key-not-a-provider-credential'
original_client = httpx.AsyncClient


def synthetic_image():
    image = Image.new('RGB', (640, 360), '#e8eef0')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((55, 70, 585, 285), 18, fill='#315a59')
    draw.rectangle((80, 95, 400, 225), fill='#aec8c6')
    draw.ellipse((105, 220, 205, 320), fill='#202b30')
    draw.ellipse((435, 220, 535, 320), fill='#202b30')
    draw.text((95, 115), 'SYNTHETIC TRUCK PHOTO', fill='#162d30')
    output = io.BytesIO(); image.save(output, format='PNG'); return output.getvalue()


async def respond(request):
    if request.method != 'GET' or request.url.host != 'api.callrail.com':
        raise RuntimeError('Non-synthetic provider request prohibited')
    if request.url.path == '/v3/a/ACCsynthetic/text-messages/InlineMmsDemo.json':
        async with AsyncSessionLocal() as db:
            message = await db.scalar(select(SMSMessage).where(
                SMSMessage.provider_message_id == 'SCIinlineMmsDemo',
                SMSMessage.provider_account_id == 'ACCsynthetic'))
            if not message:
                return httpx.Response(404)
            return httpx.Response(200, json={
                'id': 'InlineMmsDemo', 'company_id': 'COMsynthetic',
                'customer_phone_number': '+15005550222',
                'current_tracking_number': '+15005550011',
                'current_tracker_id': 'TRKsynthetic',
                'page': 1, 'per_page': 100, 'total_pages': 1, 'total_records': 1,
                'messages': [{'id': 17001, 'content': 'Photo of the truck for the repair.',
                    'created_at': message.created_at.isoformat(), 'direction': 'incoming',
                    'type': 'mms', 'media_urls': [
                        'https://api.callrail.com/v3/a/ACCsynthetic/text-messages/SCIinlineMmsDemo/media/0']}],
            })
    if request.url.path == '/v3/a/ACCsynthetic/text-messages/SCIinlineMmsDemo/media/0':
        return httpx.Response(200, content=synthetic_image(), headers={'content-type': 'image/png'})
    raise RuntimeError('Unknown synthetic media request prohibited')


def client(**kwargs):
    return original_client(transport=httpx.MockTransport(respond), **kwargs)


callrail_media.httpx = SimpleNamespace(AsyncClient=client, Timeout=httpx.Timeout,
    TimeoutException=httpx.TimeoutException, HTTPError=httpx.HTTPError)


async def deny_callrail_send(*args, **kwargs):
    raise RuntimeError('Outbound CallRail requests are disabled in the MMS image sandbox')


callrail_service.send = deny_callrail_send
