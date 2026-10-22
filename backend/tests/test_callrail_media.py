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
    assert kind == 'image/png'
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
    assert image.headers['content-disposition']=='inline; filename="attachment-0.png"'
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
    assert result.size==(24,16) and kind=='image/png'
    left=result.getpixel((3,8));right=result.getpixel((20,8))
    assert left[2]>200 and left[0]<50
    assert right[0]>200 and right[2]<50
    assert not result.getexif()


@pytest.mark.asyncio
@pytest.mark.parametrize('redirected',[False,True])
async def test_real_app_success_and_early_errors_keep_private_headers(client,receipt,monkeypatch,redirected):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    db,tenant,binding,thread,message,context=receipt
    async def allowed(*args):return tenant
    monkeypatch.setattr(comm,'authorize',allowed)
    async def current_user():return SimpleNamespace(tenant_id=tenant.id)
    previous=app.dependency_overrides.get(get_current_active_user)
    app.dependency_overrides[get_current_active_user]=current_user
    if redirected:redirect_provider(monkeypatch,context)
    else:mock_provider(monkeypatch,context)
    base=f'/api/v1/communications/conversations/{thread.id}/messages/{message.id}/attachments'
    try:
        manifest=await client.get(base)
        content=await client.get(base+'/0')
        invalid=await client.get(base+'/invalid-index')
        assert manifest.status_code==200 and manifest.json()=={'items':[{'index':0,'kind':'image'}]}
        assert content.status_code==200 and content.headers['content-type']=='image/png'
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


def signed_locator(*, now=None, changes=None, path='/synthetic-private-object.jpg', **query_changes):
    from urllib.parse import urlencode
    now=now or datetime.now(timezone.utc)
    values={'X-Amz-Algorithm':'AWS4-HMAC-SHA256',
        'X-Amz-Credential':f'SYNTHETIC/{now:%Y%m%d}/us-east-1/s3/aws4_request',
        'X-Amz-Date':now.strftime('%Y%m%dT%H%M%SZ'),'X-Amz-Expires':'300',
        'X-Amz-Security-Token':'synthetic-private-security-token','X-Amz-Signature':'a'*64,
        'X-Amz-SignedHeaders':'host','response-content-disposition':'inline; filename="private.jpg"',
        'response-content-type':'image/jpeg'}
    values.update(query_changes)
    if changes:changes(values)
    return 'https://calltrk-mms-media-prod1.s3.amazonaws.com'+path+'?'+urlencode(values)


def redirect_provider(monkeypatch, context, *, locator=None, first_status=302,
                      object_status=200, object_headers=None, object_data=None, timeout=False):
    locator=locator or signed_locator()
    requests=[];options=[];clients=[];responses=[]
    async def handler(request):
        requests.append(request)
        if request.url.host=='api.callrail.com':
            assert request.headers['authorization']=='Token token="synthetic-only"'
            if request.url.path.endswith('.json'):return httpx.Response(200,json=record(context))
            response=httpx.Response(first_status,headers=[('Location',locator),
                ('Set-Cookie','provider-secret=private; Path=/; Domain=api.callrail.com')])
            responses.append(response)
            return response
        assert request.url.host=='calltrk-mms-media-prod1.s3.amazonaws.com'
        assert responses[0].is_closed, 'Authenticated response must close before downstream GET'
        assert not any(name in request.headers for name in ('authorization','cookie','referer','request-from'))
        assert set(request.headers)=={'host','accept','accept-encoding'}
        if timeout:raise httpx.ReadTimeout('private-upstream-exception',request=request)
        headers={'Content-Type':'image/jpeg',**(object_headers or {})}
        return httpx.Response(object_status,content=pixels('JPEG') if object_data is None else object_data,headers=headers)
    def factory(**kwargs):
        options.append(kwargs)
        result=httpx.AsyncClient(transport=httpx.MockTransport(handler),**kwargs)
        clients.append(result)
        return result
    monkeypatch.setattr(media,'httpx',SimpleNamespace(AsyncClient=factory,HTTPError=httpx.HTTPError,TimeoutException=httpx.TimeoutException))
    return requests,options,clients


@pytest.mark.asyncio
async def test_signed_redirect_private_isolated_client_and_read_only(receipt,monkeypatch,caplog):
    import logging
    db,tenant,binding,thread,message,context=receipt
    monkeypatch.setenv('HTTPS_PROXY','http://untrusted-synthetic-proxy.invalid:8080')
    monkeypatch.setenv('NETRC','/nonexistent/synthetic-netrc')
    before=(message.body,message.created_at,thread.last_message_at,thread.unread_count_staff)
    requests,options,clients=redirect_provider(monkeypatch,context)
    with caplog.at_level(logging.DEBUG):
        data,kind=await media.retrieve(context,0)
    assert kind=='image/png' and Image.open(io.BytesIO(data)).size==(8,9)
    assert len(requests)==3 and len(options)==2
    assert options[1]['trust_env'] is False and all(v['follow_redirects'] is False for v in options)
    assert all(client.is_closed for client in clients)
    assert clients[0].cookies.get('provider-secret')=='private' and not clients[1].cookies
    assert before==(message.body,message.created_at,thread.last_message_at,thread.unread_count_staff)
    assert not any(value in caplog.text for value in ('synthetic-private','X-Amz-','synthetic-only','provider-secret'))


@pytest.mark.parametrize('mutation',[
    lambda u:u.replace('https://','http://'), lambda u:u.replace('https://','HTTPS://'),
    lambda u:u.replace('calltrk-mms-media-prod1.s3.amazonaws.com','calltrk-mms-media-prod1.s3.amazonaws.com.evil'),
    lambda u:u.replace('calltrk-mms-media-prod1.s3.amazonaws.com','127.0.0.1'),
    lambda u:u.replace('calltrk-mms-media-prod1.s3.amazonaws.com','localhost'),
    lambda u:u.replace('https://','https://user@'),lambda u:u.replace('.com/','.com:443/'),
    lambda u:u+'#fragment',lambda u:u+'\n',lambda u:u.replace('/synthetic','/\\synthetic'),
    lambda u:u.replace('/synthetic-private-object.jpg','/%73ynthetic.jpg'),
    lambda u:u.replace('/synthetic-private-object.jpg','/../private.jpg'),
    lambda u:u.replace('/synthetic-private-object.jpg','/prefix/private.jpg'),
    lambda u:u.replace('/synthetic-private-object.jpg','/'+'a'*1024),
    lambda u:u.replace('X-Amz-Algorithm=','Unknown='),
    lambda u:u+'&X-Amz-Expires=300',lambda u:u.replace('X-Amz-Expires=300&',''),
    lambda u:u.replace('X-Amz-Expires=300','X-Amz-Expires='),
    lambda u:u.replace('X-Amz-Security-Token=','X-Amz-Security-Token=%zz'),
    lambda u:u.replace('X-Amz-Security-Token=','X-Amz-Security-Token=%00'),
    lambda u:u+'&unused='+('a'*17000),
])
def test_signed_locator_rejects_host_path_and_query_attacks(mutation):
    with pytest.raises(HTTPException) as error:media.signed_object_url(mutation(signed_locator()))
    assert error.value.status_code==502 and error.value.headers==media.HEADERS


@pytest.mark.parametrize('changes',[
    {'X-Amz-Algorithm':'OTHER'}, {'X-Amz-Signature':'A'*64},{'X-Amz-Signature':'a'*63},
    {'X-Amz-SignedHeaders':'host;authorization'}, {'X-Amz-Credential':'bad/scope'},
    {'X-Amz-Credential':'ACCESS/20000101/us-east-1/s3/aws4_request'},
    {'X-Amz-Credential':'a'*513}, {'X-Amz-Security-Token':'a'*8193},
    {'X-Amz-Security-Token':'x\r\ny'}, {'X-Amz-Expires':'301'}, {'X-Amz-Expires':'0'},
    {'X-Amz-Expires':'-1'}, {'X-Amz-Expires':'3000'}, {'X-Amz-Expires':'1.0'},
    {'X-Amz-Date':'20260230T000000Z'}, {'response-content-type':'image/svg+xml'},
    {'response-content-disposition':'a'*1025},
])
def test_signed_locator_rejects_signing_shapes(changes):
    with pytest.raises(HTTPException):media.signed_object_url(signed_locator(**changes))


def test_signed_locator_expiry_and_future_bounds():
    from datetime import timedelta
    now=datetime.now(timezone.utc).replace(microsecond=0)
    assert media.signed_object_url(signed_locator(now=now),now=now)
    for signed_at in (now-timedelta(seconds=300),now+timedelta(seconds=61)):
        with pytest.raises(HTTPException):media.signed_object_url(signed_locator(now=signed_at),now=now)


@pytest.mark.asyncio
@pytest.mark.parametrize('status',[301,303,307,308])
async def test_callrail_other_redirects_fail_without_object_request(receipt,monkeypatch,status):
    *_,context=receipt
    requests,_,clients=redirect_provider(monkeypatch,context,first_status=status)
    with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==502 and len(requests)==2 and all(c.is_closed for c in clients)


@pytest.mark.asyncio
@pytest.mark.parametrize('status',[301,302,303,307,308,403,500])
async def test_second_redirect_or_object_error_is_not_followed(receipt,monkeypatch,status):
    *_,context=receipt
    requests,_,clients=redirect_provider(monkeypatch,context,object_status=status,
        object_headers={'Location':'https://evil.invalid/private-second-hop'})
    with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==502 and len(requests)==3 and all(c.is_closed for c in clients)


@pytest.mark.asyncio
@pytest.mark.parametrize('headers,data,status',[
    ({'Content-Type':'text/html'},b'<html>private</html>',422),
    ({'Content-Type':'image/jpeg'},b'not a raster',422),
    ({'Content-Length':str(media.INPUT_LIMIT+1)},b'x',413),
    ({'Content-Encoding':'gzip'},b'encoded',502),
])
async def test_signed_object_raster_boundaries(receipt,monkeypatch,headers,data,status):
    *_,context=receipt
    requests,_,clients=redirect_provider(monkeypatch,context,object_headers=headers,object_data=data)
    with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==status and len(requests)==3 and all(c.is_closed for c in clients)


@pytest.mark.asyncio
async def test_signed_object_timeout_sanitized_private_and_closed(receipt,monkeypatch,caplog):
    import logging
    *_,context=receipt
    requests,_,clients=redirect_provider(monkeypatch,context,timeout=True)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==504 and len(requests)==3 and all(c.is_closed for c in clients)
    assert not any(value in caplog.text for value in ('synthetic-private','X-Amz-','private-upstream-exception'))


@pytest.mark.asyncio
@pytest.mark.parametrize('locations',[[],['https://evil.invalid/private-object'],[signed_locator(),signed_locator()]])
async def test_missing_duplicate_or_untrusted_location_never_fetches_object(receipt,monkeypatch,locations):
    *_,context=receipt
    requests=[]
    def handler(request):
        requests.append(request)
        assert request.url.host=='api.callrail.com'
        if request.url.path.endswith('.json'):return httpx.Response(200,json=record(context))
        return httpx.Response(302,headers=[('Location',value) for value in locations])
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr(media,'httpx',SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw),HTTPError=httpx.HTTPError,TimeoutException=httpx.TimeoutException))
    with pytest.raises(HTTPException) as error:await media.retrieve(context,0)
    assert error.value.status_code==502 and len(requests)==2


@pytest.mark.asyncio
async def test_discovery_never_allows_signed_object_redirect(receipt,monkeypatch):
    *_,context=receipt
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(302,headers={'Location':signed_locator()})
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr(media,'httpx',SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw),HTTPError=httpx.HTTPError,TimeoutException=httpx.TimeoutException))
    with pytest.raises(HTTPException) as error:await media.retrieve(context)
    assert error.value.status_code==502 and len(requests)==1


@pytest.mark.asyncio
async def test_signed_query_preserved_and_cancellation_closes_private_chain(receipt,monkeypatch,caplog):
    import asyncio
    import logging
    from urllib.parse import urlsplit
    from httpcore._trace import Trace
    from httpcore import Request
    *_,context=receipt
    locator=signed_locator();entered=asyncio.Event();clients=[]
    async def handler(request):
        if request.url.host=='api.callrail.com':
            if request.url.path.endswith('.json'):return httpx.Response(200,json=record(context))
            return httpx.Response(302,headers={'Location':locator})
        assert request.url.query.decode()==urlsplit(locator).query
        async with Trace('receive_response_headers',logging.getLogger('httpcore.http11'),Request('GET',str(request.url))) as trace:
            trace.return_value=(b'HTTP/1.1',302,b'Found',[(b'Location',locator.encode())])
        entered.set()
        await asyncio.Event().wait()
    def factory(**kwargs):
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler),**kwargs);clients.append(client);return client
    monkeypatch.setattr(media,'httpx',SimpleNamespace(AsyncClient=factory,HTTPError=httpx.HTTPError,TimeoutException=httpx.TimeoutException))
    with caplog.at_level(logging.DEBUG):
        task=asyncio.create_task(media.retrieve(context,0))
        await entered.wait()
        logging.getLogger('httpcore.http11').debug('unrelated-concurrent-request-visible')
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        logging.getLogger('httpx').info('unrelated-after-cancel-visible')
    assert all(c.is_closed for c in clients) and not media._PRIVATE_REQUEST.get()
    assert not any(value in caplog.text for value in ('synthetic-private','X-Amz-','synthetic-only'))
    assert 'unrelated-concurrent-request-visible' in caplog.text
    assert 'unrelated-after-cancel-visible' in caplog.text


def test_rgb_jpeg_becomes_lossless_metadata_free_png():
    original=Image.new('RGB',(31,19),(80,160,210))
    exif=Image.Exif();exif[270]='private synthetic EXIF'
    encoded=io.BytesIO();original.save(encoded,format='JPEG',exif=exif)
    source=Image.open(io.BytesIO(encoded.getvalue()));source.load()
    data,kind=media.decode_raster(encoded.getvalue(),'image/jpeg')
    result=Image.open(io.BytesIO(data));result.load()
    assert kind=='image/png' and result.format=='PNG'
    assert result.tobytes()==source.tobytes()
    assert not result.getexif() and b'private synthetic EXIF' not in data


def test_png_output_cap_checked_during_encoding(monkeypatch):
    monkeypatch.setattr(media,'OUTPUT_LIMIT',40)
    with pytest.raises(HTTPException) as error:media.decode_raster(pixels(),'image/png')
    assert error.value.status_code==413


def test_large_photographic_png_output_fails_existing_ten_mib_cap():
    import random
    source=Image.frombytes('RGB',(2048,2048),random.Random(17017).randbytes(2048*2048*3))
    output=io.BytesIO();source.save(output,format='JPEG',quality=85)
    assert len(output.getvalue())<media.INPUT_LIMIT
    with pytest.raises(HTTPException) as error:media.decode_raster(output.getvalue(),'image/jpeg')
    assert error.value.status_code==413 and media.OUTPUT_LIMIT==10*1024*1024


def mpo_pixels(*, pictures=2, size=(80,48), orientation=6):
    primary=Image.new('RGB',size,'red')
    primary.paste(Image.new('RGB',(size[0]//2,size[1]),'blue'),(0,0))
    secondary_size=(min(size[0],80),min(size[1],48))
    secondary=[Image.new('RGB',secondary_size,'green') for _ in range(pictures-1)]
    exif=Image.Exif();exif[270]='Private synthetic primary description';exif[305]='Private synthetic software'
    if orientation:exif[274]=orientation
    output=io.BytesIO();primary.save(output,format='MPO',save_all=True,append_images=secondary,exif=exif)
    return output.getvalue()


@pytest.mark.parametrize('orientation',[6,8])
def test_genuine_mpo_only_primary_pixels_orientation_and_no_metadata(monkeypatch,orientation):
    from PIL import ImageOps,MpoImagePlugin
    raw=mpo_pixels(pictures=2,orientation=orientation)
    with Image.open(io.BytesIO(raw)) as source:
        assert source.format=='MPO' and source.n_frames==2
        primary=ImageOps.exif_transpose(source).convert('RGB')
        source.seek(1)
        source.load()
        assert source.size==(80,48) and source.getpixel((16,12))!=primary.getpixel((24,40))
    seeks=[];loads=[]
    original_seek=MpoImagePlugin.MpoImageFile.seek
    original_load=MpoImagePlugin.MpoImageFile.load
    def seek(image,frame):seeks.append(frame);return original_seek(image,frame)
    def load(image,*args,**kwargs):loads.append(image.tell());return original_load(image,*args,**kwargs)
    monkeypatch.setattr(MpoImagePlugin.MpoImageFile,'seek',seek)
    monkeypatch.setattr(MpoImagePlugin.MpoImageFile,'load',load)
    data,kind=media.decode_raster(raw+b'private synthetic trailing auxiliary marker','image/jpeg')
    with Image.open(io.BytesIO(data)) as result:
        assert kind=='image/png' and result.format=='PNG' and getattr(result,'n_frames',1)==1
        assert result.size==(48,80) and result.tobytes()==primary.tobytes()
        assert not result.info and not result.getexif()
    assert seeks and loads and set(seeks)=={0} and set(loads)=={0}
    assert b'Private synthetic' not in data and b'MPF\0' not in data and b'auxiliary marker' not in data


@pytest.mark.parametrize('declared',['image/png','image/webp','image/gif','image/mpo','application/octet-stream',''])
def test_mpo_only_allowed_under_exact_jpeg_mime(declared):
    with pytest.raises(HTTPException) as error:media.decode_raster(mpo_pixels(),declared)
    assert error.value.status_code==422 and error.value.headers==media.HEADERS


@pytest.mark.parametrize('size',[(8193,1),(5001,5000)])
def test_mpo_primary_dimension_and_pixel_cap(size):
    with pytest.raises(HTTPException) as error:media.decode_raster(mpo_pixels(size=size,orientation=None),'image/jpeg')
    assert error.value.status_code==413


def test_mpo_primary_truncation_and_malformed_mpf_rejected():
    raw=mpo_pixels()
    first_end=raw.index(b'\xff\xd9')
    malformed=bytearray(raw);tiff=raw.index(b'MPF\0')+4;malformed[tiff:tiff+2]=b'ZZ'
    for data in (raw[:first_end//2],bytes(malformed)):
        with pytest.raises(HTTPException) as error:media.decode_raster(data,'image/jpeg')
        assert error.value.status_code==422


def test_mpo_existing_input_and_output_limits(monkeypatch):
    raw=mpo_pixels()
    with pytest.raises(HTTPException) as error:media.decode_raster(raw+b'x'*media.INPUT_LIMIT,'image/jpeg')
    assert error.value.status_code==413
    monkeypatch.setattr(media,'OUTPUT_LIMIT',16)
    with pytest.raises(HTTPException) as error:media.decode_raster(raw,'image/jpeg')
    assert error.value.status_code==413


@pytest.mark.asyncio
async def test_signed_object_mpo_primary_preview_preserves_privacy(receipt,monkeypatch):
    *_,context=receipt
    requests,_,clients=redirect_provider(monkeypatch,context,object_data=mpo_pixels())
    data,kind=await media.retrieve(context,0)
    with Image.open(io.BytesIO(data)) as image:
        assert kind=='image/png' and image.size==(48,80) and getattr(image,'n_frames',1)==1
    assert len(requests)==3 and all(client.is_closed for client in clients)


def test_installed_three_picture_writer_malformed_mpf_is_rejected():
    # Pillow 10.1 reserves an 82-byte MPF block sized for two pictures; a third
    # append overwrites primary JPEG data. Do not downgrade that broken container.
    raw=mpo_pixels(pictures=3)
    import warnings
    from PIL import UnidentifiedImageError
    # The broken writer output has two independently reproduced parser outcomes:
    # it may be unidentifiable, or downgrade to JPEG with a malformed-MPO warning.
    # Neither outcome may become a successful application attachment.
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter('always')
        try:
            with Image.open(io.BytesIO(raw)) as source:
                assert source.format=='JPEG'
        except UnidentifiedImageError:
            pass
        else:
            assert any('Image appears to be a malformed MPO file' in str(item.message) for item in seen)
    with pytest.raises(HTTPException) as error:media.decode_raster(raw,'image/jpeg')
    assert error.value.status_code==422
