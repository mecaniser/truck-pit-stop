"""Synthetic-only MMS browser fixture; never forwards a provider request."""
import io
import os
from types import SimpleNamespace
from datetime import datetime, timezone
from urllib.parse import urlencode

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
    # Genuine JPEG multipicture input; the secondary picture must never render.
    secondary = Image.new('RGB', image.size, '#ff00ff')
    exif = Image.Exif(); exif[270] = 'Synthetic private MPO metadata'
    output = io.BytesIO()
    image.save(output, format='MPO', save_all=True, append_images=[secondary], exif=exif)
    return output.getvalue()


def synthetic_locator():
    now = datetime.now(timezone.utc)
    query = urlencode({'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
        'X-Amz-Credential': f'SYNTHETIC/{now:%Y%m%d}/us-east-1/s3/aws4_request',
        'X-Amz-Date': now.strftime('%Y%m%dT%H%M%SZ'), 'X-Amz-Expires': '300',
        'X-Amz-Security-Token': 'synthetic-local-session-token', 'X-Amz-Signature': 'a' * 64,
        'X-Amz-SignedHeaders': 'host', 'response-content-disposition': 'inline',
        'response-content-type': 'image/jpeg'})
    return 'https://calltrk-mms-media-prod1.s3.amazonaws.com/synthetic-local-truck.jpg?' + query


async def respond(request):
    if request.method != 'GET':
        raise RuntimeError('Non-synthetic provider request prohibited')
    if request.url.host == 'calltrk-mms-media-prod1.s3.amazonaws.com':
        if (request.url.path != '/synthetic-local-truck.jpg'
            or any(name in request.headers for name in ('authorization', 'cookie', 'referer', 'request-from'))):
            raise RuntimeError('Non-synthetic or credential-bearing object request prohibited')
        callrail_media.signed_object_url(str(request.url))
        return httpx.Response(200, content=synthetic_image(), headers={'content-type': 'image/jpeg'})
    if request.url.host != 'api.callrail.com':
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
        return httpx.Response(302, headers={'location': synthetic_locator(),
            'set-cookie': 'synthetic-provider-cookie=private; Domain=api.callrail.com'})
    raise RuntimeError('Unknown synthetic media request prohibited')


def client(**kwargs):
    return original_client(transport=httpx.MockTransport(respond), **kwargs)


callrail_media.httpx = SimpleNamespace(AsyncClient=client, Timeout=httpx.Timeout,
    TimeoutException=httpx.TimeoutException, HTTPError=httpx.HTTPError)


async def deny_callrail_send(*args, **kwargs):
    raise RuntimeError('Outbound CallRail requests are disabled in the MMS image sandbox')


callrail_service.send = deny_callrail_send
