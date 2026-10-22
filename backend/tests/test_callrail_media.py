"""Private media boundary tests. Synthetic pixels and mocked HTTP only."""
import io
import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from PIL import Image, PngImagePlugin
from sqlalchemy import select
from app.db.models.callrail import CallRailNumberBinding, CallRailConversation, CallRailMessageAlias
from app.db.models.sms_message import SMSMessage
from app.db.models.message_thread import MessageThread
from app.db.models.tenant import Tenant
from app.services import callrail_service as cr, callrail_media as media, communications_service as comm


def pixels(fmt='PNG', **kwargs):
    output = io.BytesIO()
    Image.new('RGB', (8, 9), 'red').save(output, format=fmt, **kwargs)
    return output.getvalue()


@pytest_asyncio.fixture
async def receipt(db_session, monkeypatch):
    db = db_session
    tenant = Tenant(name='Media synthetic', slug='media-'+uuid4().hex, messaging_enabled=True)
    db.add(tenant)
    await db.flush()
    binding = CallRailNumberBinding(tenant_id=tenant.id, account_id='ACCsynthetic', company_id='COMsynthetic',
        tracker_id='TRKsynthetic', sender_phone='+15005550011', credential_ref='CALLRAIL_MEDIA_TEST_API',
        signing_secret_ref='CALLRAIL_MEDIA_TEST_SIGN', enabled=True, accept_new_inquiries=True)
    db.add(binding)
    await db.commit()
    monkeypatch.setenv(binding.credential_ref, 'synthetic-only')
    event = dict(id=23456, resource_id='SCIexample', company_resource_id=binding.company_id,
        source_number='+15005550022', destination_number=binding.sender_phone, content='A caption',
        message_type='mms', timestamp=datetime.now(timezone.utc).isoformat(), conversation_id='CONsynthetic')
    result = await cr.apply_event(db, binding.id, event, 'received')
    await db.commit()
    message = await db.get(SMSMessage, result['message_id'])
    thread = await db.get(MessageThread, message.thread_id)
    context = await media.context_for(db, tenant.id, thread, message.id)
    return db, tenant, binding, thread, message, context


def record(context, **changes):
    value = dict(id=context.conversation, company_id=context.company, customer_phone_number=context.contact,
        page=1, per_page=100, total_pages=1, total_records=1, messages=[dict(id=23456,
            content='A caption', created_at=context.message.created_at.replace(tzinfo=timezone.utc).isoformat(), direction='incoming', type='MMS',
            media_urls=[f'https://api.callrail.com/v3/a/{context.account}/text-messages/SCIexample/media/0'])])
    value.update(changes)
    return value


def mock_provider(monkeypatch, context, *, payload=None, image=None, status=200, content_type='image/png'):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers['Authorization'] == 'Token token="synthetic-only"'
        if request.url.path.endswith('.json'):
            return httpx.Response(200, json=payload or record(context))
        return httpx.Response(status, content=pixels() if image is None else image, headers={'Content-Type':content_type})
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(media, 'httpx', SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport, **kw), HTTPError=httpx.HTTPError, TimeoutException=httpx.TimeoutException))
    return calls


@pytest.mark.asyncio
async def test_manifest_and_content_read_only(receipt, monkeypatch):
    db, tenant, binding, thread, message, context = receipt
    calls = mock_provider(monkeypatch, context)
    before = (message.body, message.created_at, thread.unread_count_staff, thread.last_message_at)
    assert (await comm.message_json(db, message))['has_attachments'] is True
    assert await media.retrieve(context) == {'items':[{'index':0,'kind':'image'}]}
    assert len(calls) == 1
    data, kind = await media.retrieve(context, 0)
    assert kind == 'image/jpeg'
    assert Image.open(io.BytesIO(data)).size == (8,9)
    assert before == (message.body, message.created_at, thread.unread_count_staff, thread.last_message_at)


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['disabled','deleted_binding','deleted_message','foreign','phone','mapping','from','account','alias','inquiry'])
async def test_context_fail_closed_before_credentials(receipt, monkeypatch, mutation):
    db, tenant, binding, thread, message, context = receipt
    monkeypatch.setattr(cr, 'secret', lambda _:pytest.fail('must not resolve credentials'))
    if mutation == 'disabled':binding.enabled=False
    elif mutation == 'deleted_binding':binding.deleted_at=datetime.now(timezone.utc)
    elif mutation == 'deleted_message':message.deleted_at=datetime.now(timezone.utc)
    elif mutation == 'foreign':message.tenant_id=uuid4()
    elif mutation == 'phone':thread.customer_phone='+15005550099'
    elif mutation == 'mapping':
        mapping=await db.scalar(select(CallRailConversation));mapping.provider_conversation_id='changed'
    elif mutation == 'from':message.from_number='+15005550099'
    elif mutation == 'account':message.provider_account_id='OTHER'
    elif mutation == 'alias':message.provider_message_id='SCIabsent'
    elif mutation == 'inquiry':thread.inquiry_binding_id=uuid4()
    await db.flush()
    with pytest.raises(HTTPException) as error:
        await media.context_for(db, tenant.id, thread, message.id)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_opted_out_and_unselected_binding_can_view(receipt):
    db, tenant, binding, thread, message, context = receipt
    thread.inquiry_opted_out=True
    mapping=await db.scalar(select(CallRailConversation));mapping.selected_for_sending=False
    await db.flush()
    assert (await media.context_for(db, tenant.id, thread, message.id)).account == binding.account_id


@pytest.mark.parametrize('url', ['http://api.callrail.com/v3/a/ACCsynthetic/text-messages/SCIexample/media/0',
 'https://api.callrail.com.evil/v3/a/ACCsynthetic/text-messages/SCIexample/media/0',
 'https://u@api.callrail.com/v3/a/ACCsynthetic/text-messages/SCIexample/media/0',
 'https://api.callrail.com:443/v3/a/ACCsynthetic/text-messages/SCIexample/media/0',
 'https://api.callrail.com/v3/a/OTHER/text-messages/SCIexample/media/0',
 'https://api.callrail.com/v3/a/ACCsynthetic/text-messages/SCIother/media/0',
 'https://api.callrail.com/v3/a/ACCsynthetic/text-messages/SCIexample/media/1',
 'https://api.callrail.com/v3/a/ACCsynthetic/text-messages/SCIexample/media/%30',
 'https://api.callrail.com/v3/a/ACCsynthetic/text-messages/SCIexample/media/0?token=x',
 'https://api.callrail.com/v3/a/ACCsynthetic/text-messages/SCIexample/media/0#x'])
def test_url_boundary(url):
    context=SimpleNamespace(account='ACCsynthetic', aliases={'resource:SCIexample'})
    with pytest.raises(HTTPException):media.media_url(url, context, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['timestamp','caption','direction','numeric','absent','duplicate','company','contact','conversation','pages','type'])
async def test_provider_identity_failures(receipt, monkeypatch, mutation):
    *_, context=receipt
    payload=record(context)
    item=payload['messages'][0]
    if mutation=='timestamp':item['created_at']='2020-01-01T00:00:00Z'
    elif mutation=='caption':item['content']='changed'
    elif mutation=='direction':item['direction']='outgoing'
    elif mutation=='numeric':item['id']=999
    elif mutation=='absent':payload['messages']=[]
    elif mutation=='duplicate':payload['messages'].append(dict(item))
    elif mutation=='company':payload['company_id']='OTHER'
    elif mutation=='contact':payload['customer_phone_number']='+15005550099'
    elif mutation=='conversation':payload['id']='OTHER'
    elif mutation=='pages':payload['total_pages']=11
    elif mutation=='type':item['type']=None
    calls=mock_provider(monkeypatch,context,payload=payload)
    with pytest.raises(HTTPException):await media.retrieve(context)
    assert len(calls)==1


@pytest.mark.asyncio
async def test_numeric_only_and_media_resource_alias(receipt, monkeypatch):
    *_, context=receipt
    for aliases in ({'id:23456'}, {'resource:SCIexample'}):
        altered=replace(context,aliases=frozenset(aliases))
        mock_provider(monkeypatch,altered)
        assert await media.retrieve(altered)=={'items':[{'index':0,'kind':'image'}]}


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [301,302,303,307,308,401,403,404,500])
async def test_provider_status_sanitized(receipt,monkeypatch,status):
    *_,context=receipt
    mock_provider(monkeypatch,context,status=status,image=b'secret upstream body')
    with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==502
    assert 'secret' not in str(error.value.detail)
    assert error.value.headers==media.HEADERS


@pytest.mark.parametrize('data,declared',[(b'<svg/>','image/svg+xml'),(b'<html/>','image/png'),(pixels(),'image/jpeg'),(pixels(),'')])
def test_invalid_raster(data,declared):
    with pytest.raises(HTTPException) as error:media.decode_raster(data,declared)
    assert error.value.status_code==422


@pytest.mark.parametrize('fmt,declared',[('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp'),('GIF','image/gif')])
def test_raster_reencoded(fmt,declared):
    data,kind=media.decode_raster(pixels(fmt)+b'private trailing bytes',declared)
    assert b'private trailing bytes' not in data
    result=Image.open(io.BytesIO(data))
    assert result.format in {'PNG','JPEG'} and getattr(result,'n_frames',1)==1


def test_metadata_removed():
    info=PngImagePlugin.PngInfo();info.add_text('private','synthetic metadata')
    data,_=media.decode_raster(pixels(pnginfo=info),'image/png')
    assert b'synthetic metadata' not in data


@pytest.mark.asyncio
async def test_oversize_and_wrong_declared_type(receipt,monkeypatch):
    *_,context=receipt
    mock_provider(monkeypatch,context,image=b'x'*(media.INPUT_LIMIT+1))
    with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==413
    mock_provider(monkeypatch,context,content_type='text/html')
    with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==422


@pytest.mark.asyncio
async def test_multiple_images_and_empty_manifest(receipt,monkeypatch):
    *_,context=receipt
    payload=record(context)
    payload['messages'][0]['media_urls'].append(f'https://api.callrail.com/v3/a/{context.account}/text-messages/SCIexample/media/1')
    mock_provider(monkeypatch,context,payload=payload)
    assert await media.retrieve(context)=={'items':[{'index':0,'kind':'image'},{'index':1,'kind':'image'}]}
    payload['messages'][0]['media_urls']=[]
    mock_provider(monkeypatch,context,payload=payload)
    assert await media.retrieve(context)=={'items':[]}
    with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==404


@pytest.mark.asyncio
async def test_image_only_legacy_receipt(receipt,monkeypatch):
    *_,context=receipt
    context.message.body=cr.ATTACHMENT_NOTICE
    payload=record(context);payload['messages'][0]['content']=None
    mock_provider(monkeypatch,context,payload=payload)
    assert await media.retrieve(context)=={'items':[{'index':0,'kind':'image'}]}


@pytest.mark.asyncio
async def test_pagination_reconstructed_and_ambiguity(receipt,monkeypatch):
    *_,context=receipt
    calls=[]
    def handler(request):
        calls.append(request)
        payload=record(context,page=int(request.url.params['page']),total_pages=2)
        if request.url.params['page']=='1':payload['messages']=[]
        payload['next_page']='https://evil.invalid/ignore'
        return httpx.Response(200,json=payload)
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr(media,'httpx',SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw),HTTPError=httpx.HTTPError,TimeoutException=httpx.TimeoutException))
    assert await media.retrieve(context)=={'items':[{'index':0,'kind':'image'}]}
    assert len(calls)==2 and all(r.url.host=='api.callrail.com' for r in calls)


@pytest.mark.asyncio
async def test_timeout_sanitized(receipt,monkeypatch):
    *_,context=receipt
    def handler(request):raise httpx.ReadTimeout('private-provider-identity',request=request)
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr(media,'httpx',SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw),HTTPError=httpx.HTTPError,TimeoutException=httpx.TimeoutException))
    with pytest.raises(HTTPException) as error:await media.retrieve(context)
    assert error.value.status_code==504 and 'private-provider' not in str(error.value.detail)


class Chunks(httpx.AsyncByteStream):
    def __init__(self,data):self.data=data
    async def __aiter__(self):
        for start in range(0,len(self.data),65536):yield self.data[start:start+65536]


@pytest.mark.asyncio
@pytest.mark.parametrize('compressed',[False,True])
async def test_stream_limit_without_content_length(receipt,monkeypatch,compressed):
    import gzip
    *_,context=receipt
    content=b'x'*(media.INPUT_LIMIT+1)
    if compressed:content=gzip.compress(content)
    def handler(request):
        if request.url.path.endswith('.json'):return httpx.Response(200,json=record(context))
        headers={'Content-Type':'image/png'}
        if compressed:headers['Content-Encoding']='gzip'
        return httpx.Response(200,stream=Chunks(content),headers=headers)
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr(media,'httpx',SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw),HTTPError=httpx.HTTPError,TimeoutException=httpx.TimeoutException))
    with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==(502 if compressed else 413)


@pytest.mark.parametrize('size',[(8193,1),(5001,5000)])
def test_dimension_limits(size):
    output=io.BytesIO();Image.new('L',size).save(output,format='PNG')
    with pytest.raises(HTTPException) as error:media.decode_raster(output.getvalue(),'image/png')
    assert error.value.status_code==413


def test_animated_input_static():
    output=io.BytesIO()
    Image.new('RGB',(8,8),'red').save(output,format='GIF',save_all=True,append_images=[Image.new('RGB',(8,8),'blue')])
    result,_=media.decode_raster(output.getvalue(),'image/gif')
    assert getattr(Image.open(io.BytesIO(result)),'n_frames',1)==1


@pytest.mark.asyncio
async def test_endpoint_authorization_and_headers(receipt,monkeypatch):
    from app.api.v1.endpoints import communications as api
    from fastapi import Response
    db,tenant,binding,thread,message,context=receipt
    async def allowed(*args):return tenant
    monkeypatch.setattr(comm,'authorize',allowed)
    mock_provider(monkeypatch,context)
    response=Response()
    assert await api.attachment_manifest(thread.id,message.id,response,db,object())=={'items':[{'index':0,'kind':'image'}]}
    assert {value.strip() for value in response.headers['cache-control'].split(',')} >= {'private','no-store'}
    image=await api.attachment_content(thread.id,message.id,0,db,object())
    assert image.headers['x-content-type-options']=='nosniff'
    assert image.headers['content-disposition']=='inline; filename="attachment-0.jpg"'
    async def denied(*args):raise HTTPException(403,detail={'code':'forbidden','message':'Denied.'})
    monkeypatch.setattr(comm,'authorize',denied)
    monkeypatch.setattr(cr,'secret',lambda _:pytest.fail('credentials before authorization'))
    with pytest.raises(HTTPException) as error:await api.attachment_manifest(thread.id,message.id,Response(),db,object())
    assert error.value.status_code==403 and error.value.headers==media.HEADERS


@pytest.mark.asyncio
async def test_httpx_logs_do_not_expose_media_urls(receipt,monkeypatch,caplog):
    import logging
    *_,context=receipt
    mock_provider(monkeypatch,context)
    with caplog.at_level(logging.INFO,logger='httpx'):
        await media.retrieve(context,0)
        logging.getLogger('httpx').info('unrelated logging preserved')
    assert 'api.callrail.com' not in caplog.text
    assert 'unrelated logging preserved' in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('logger_name',['httpcore.http11','httpcore.http2'])
async def test_debug_trace_headers_private_but_concurrent_logs_preserved(logger_name,caplog):
    import asyncio
    import logging
    from httpcore._trace import Trace
    from httpcore import Request
    logger=logging.getLogger(logger_name)
    entered=asyncio.Event();release=asyncio.Event()
    async def private():
        token=media._PRIVATE_REQUEST.set(True)
        try:
            entered.set()
            await release.wait()
            async with Trace('receive_response_headers',logger,Request('GET','https://api.callrail.com/')) as trace:
                trace.return_value=(b'HTTP/1.1',302,b'Found',[(b'Location',b'https://api.callrail.com/private-synthetic-locator')])
        finally:media._PRIVATE_REQUEST.reset(token)
    async def unrelated():
        await entered.wait()
        async with Trace('receive_response_headers',logger,Request('GET','https://example.invalid/')) as trace:
            trace.return_value=(b'HTTP/1.1',200,b'OK',[(b'X-Test',b'unrelated-concurrent-trace')])
        release.set()
    with caplog.at_level(logging.DEBUG,logger=logger_name):
        await asyncio.gather(private(),unrelated())
    assert 'private-synthetic-locator' not in caplog.text
    assert 'unrelated-concurrent-trace' in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('index,status,code',[(None,502,'attachment_unavailable'),(0,502,'attachment_unavailable'),
    (None,504,'attachment_timeout'),(0,504,'attachment_timeout')])
async def test_real_app_preserves_safe_media_error_contract(client,receipt,monkeypatch,index,status,code):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    db,tenant,binding,thread,message,context=receipt
    async def allowed(*args):return tenant
    monkeypatch.setattr(comm,'authorize',allowed)
    async def current_user():return SimpleNamespace(tenant_id=tenant.id)
    previous=app.dependency_overrides.get(get_current_active_user)
    app.dependency_overrides[get_current_active_user]=current_user
    async def rejected(*args,**kwargs):media.fail(code)
    monkeypatch.setattr(media,'retrieve',rejected)
    try:
        path=f'/api/v1/communications/conversations/{thread.id}/messages/{message.id}/attachments'
        if index is not None:path+=f'/{index}'
        response=await client.get(path)
        assert response.status_code==status
        assert response.json()['detail']=={'code':code,'message':media._ERRORS[code][1]}
        assert {value.strip() for value in response.headers['cache-control'].split(',')} >= {'private','no-store'}
        assert response.headers['x-content-type-options']=='nosniff'
        assert response.headers['referrer-policy']=='no-referrer'
    finally:
        if previous is None:app.dependency_overrides.pop(get_current_active_user,None)
        else:app.dependency_overrides[get_current_active_user]=previous


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_json',[b'['*2000+b'0'+b']'*2000,b'{"invalid":'])
async def test_malformed_or_deep_json_is_sanitized(receipt,monkeypatch,bad_json):
    *_,context=receipt
    transport=httpx.MockTransport(lambda request:httpx.Response(200,content=bad_json,headers={'Content-Type':'application/json'}))
    monkeypatch.setattr(media,'httpx',SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw),HTTPError=httpx.HTTPError,TimeoutException=httpx.TimeoutException))
    with pytest.raises(HTTPException) as error:await media.retrieve(context)
    assert error.value.status_code==502 and error.value.headers==media.HEADERS


@pytest.mark.asyncio
@pytest.mark.parametrize('media_body',[False,True])
async def test_unbounded_length_header_is_sanitized(media_body):
    transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'x',headers={
        'Content-Type':'image/png' if media_body else 'application/json','Content-Length':'1'*5000}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(HTTPException) as error:
            await media.bounded_get(client,'https://api.callrail.com/',{},media.INPUT_LIMIT,media=media_body)
    assert error.value.status_code==(413 if media_body else 502)
    assert error.value.headers==media.HEADERS


def test_phone_jpeg_orientation_applied_before_metadata_stripping():
    source=Image.new('RGB',(16,24),'red')
    source.paste(Image.new('RGB',(16,12),'blue'),(0,12))
    exif=Image.Exif();exif[274]=6
    output=io.BytesIO();source.save(output,format='JPEG',exif=exif,quality=100,subsampling=0)
    data,kind=media.decode_raster(output.getvalue(),'image/jpeg')
    result=Image.open(io.BytesIO(data))
    assert result.size==(24,16) and kind=='image/jpeg'
    left=result.getpixel((3,8));right=result.getpixel((20,8))
    assert left[2]>200 and left[0]<50
    assert right[0]>200 and right[2]<50
    assert not result.getexif()


@pytest.mark.asyncio
async def test_real_app_success_and_early_errors_keep_private_headers(client,receipt,monkeypatch):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    db,tenant,binding,thread,message,context=receipt
    async def allowed(*args):return tenant
    monkeypatch.setattr(comm,'authorize',allowed)
    async def current_user():return SimpleNamespace(tenant_id=tenant.id)
    previous=app.dependency_overrides.get(get_current_active_user)
    app.dependency_overrides[get_current_active_user]=current_user
    mock_provider(monkeypatch,context)
    base=f'/api/v1/communications/conversations/{thread.id}/messages/{message.id}/attachments'
    try:
        manifest=await client.get(base)
        content=await client.get(base+'/0')
        invalid=await client.get(base+'/invalid-index')
        assert manifest.status_code==200 and manifest.json()=={'items':[{'index':0,'kind':'image'}]}
        assert content.status_code==200 and content.headers['content-type']=='image/jpeg'
        assert invalid.status_code==422
        async def signed_out():raise HTTPException(401,detail='Authentication required')
        app.dependency_overrides[get_current_active_user]=signed_out
        unauthorized=await client.get(base)
        assert unauthorized.status_code==401
        for response in (manifest,content,invalid,unauthorized):
            assert 'no-store' in response.headers['cache-control']
            assert 'private' in response.headers['cache-control']
            assert response.headers['referrer-policy']=='no-referrer'
            assert response.headers['x-content-type-options']=='nosniff'
        unrelated=await client.get('/health/ready')
        assert unrelated.headers['referrer-policy']=='strict-origin-when-cross-origin'
    finally:
        if previous is None:app.dependency_overrides.pop(get_current_active_user,None)
        else:app.dependency_overrides[get_current_active_user]=previous
