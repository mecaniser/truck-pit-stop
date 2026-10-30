"""Scoped nonfinancial wakeups captured with invoice changes; no billing grants."""
import hashlib,hmac,json,os,re
from datetime import datetime,timezone
from urllib.parse import urlsplit
from uuid import UUID,uuid4
from sqlalchemy import select
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.historical_invoice_export import HistoricalInvoiceMapping
from app.db.models.fleet_invoice_api_key import FleetInvoiceApiKey

EVENT='fleet.financial.wakeup.v1'
VERSION='db094-financial-wakeup-v1'


def destinations():
    raw=os.getenv('DIESELBRIDGE_FLEET_WEBHOOKS','').strip()
    if not raw:return {}
    try:
        entries=json.loads(raw)
        if not isinstance(entries,list) or len(entries)>100:raise ValueError()
        result={}
        for entry in entries:
            if set(entry)!={'shop_id','customer_id','url','secret_env'}:raise ValueError()
            scope=(UUID(entry['shop_id']),UUID(entry['customer_id']))
            u=urlsplit(entry['url'])
            if (u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment
                or not re.fullmatch(r'/api/v1/accounting/dieselbridge/webhooks/[a-z0-9][a-z0-9_-]{0,59}',u.path)
                or not re.fullmatch('[A-Z][A-Z0-9_]{2,120}',entry['secret_env']) or scope in result):raise ValueError()
            result[scope]=entry
        return result
    except (ValueError,TypeError,KeyError):
        raise ValueError('Fleet financial webhook configuration is invalid.') from None


async def enqueue_financial_wakeup(db,*,invoice,order,kind,settlement_event=None):
    if kind not in {'invoice_finalized','invoice_changed','invoice_cancelled'}:raise ValueError('Invalid wakeup kind.')
    configured=destinations()
    if not configured:return None
    if invoice.tenant_id!=order.tenant_id or invoice.is_internal or invoice.deleted_at or order.is_internal or order.deleted_at:return None
    target=invoice.billed_customer_id
    if target is None:
        target=await db.scalar(select(HistoricalInvoiceMapping.target_customer_id).where(HistoricalInvoiceMapping.invoice_id==invoice.id,HistoricalInvoiceMapping.tenant_id==invoice.tenant_id))
    if target is None or (invoice.tenant_id,target) not in configured:return None
    active=await db.scalar(select(FleetInvoiceApiKey.id).where(FleetInvoiceApiKey.tenant_id==invoice.tenant_id,FleetInvoiceApiKey.customer_id==target,FleetInvoiceApiKey.revoked_at.is_(None)))
    if not active:return None
    await db.flush()
    await db.refresh(invoice,attribute_names=['updated_at','created_at'])
    def utc(value):
        if value is None:return None
        value=value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value.isoformat()
    # RO occurrence/description corrections are meaningful even when the invoice
    # row does not change. Amounts also disambiguate same-clock-tick revisions.
    state={'invoice_updated_at':utc(invoice.updated_at or invoice.created_at),
           'service_completed_at':utc(order.work_completed_at),'description':order.description,
           'order_status':order.status.value,'vehicle_id':str(order.vehicle_id),
           'line_items':invoice.line_items_snapshot,
           'money':{field:str(getattr(invoice,field)) for field in
                    ('subtotal','shop_supplies_amount','service_fee_amount','tax_amount','discount_amount','total_amount')}}
    if settlement_event is not None:state['settlement_event']=settlement_event
    revision=hashlib.sha256(json.dumps(state,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
    key=f'db094:{invoice.id}:{target}:{kind}:{revision}'
    existing=await db.scalar(select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id==invoice.tenant_id,ProviderOutboxEvent.event_type==EVENT,ProviderOutboxEvent.idempotency_key==key))
    if existing:return existing
    now=datetime.now(timezone.utc);event_id=uuid4()
    event=ProviderOutboxEvent(id=event_id,tenant_id=invoice.tenant_id,event_type=EVENT,
        aggregate_type='repair_order',aggregate_id=order.id,idempotency_key=key,available_at=now,
        payload={'version':VERSION,'event_id':str(event_id),'shop_id':str(invoice.tenant_id),
                 'customer_id':str(target),'repair_order_id':str(order.id),'kind':kind,'occurred_at':now.isoformat()})
    db.add(event)
    return event


def _enabled():
    return os.getenv('DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED','').lower() in {'1','true'}


async def _delivery_config(db,event):
    from app.db.models.tenant import Tenant
    from app.db.models.customer import Customer
    try:
        p=event.payload
        if (set(p)!={'version','event_id','shop_id','customer_id','repair_order_id','kind','occurred_at'}
            or p['version']!=VERSION or UUID(p['event_id'])!=event.id
            or UUID(p['shop_id'])!=event.tenant_id or UUID(p['repair_order_id'])!=event.aggregate_id
            or p['kind'] not in {'invoice_finalized','invoice_changed','invoice_cancelled'}):return None
        scope=(event.tenant_id,UUID(p['customer_id']))
        config=destinations().get(scope)
        if not config or len(os.getenv(config['secret_env'],''))<32:return None
        tenant=await db.get(Tenant,scope[0]);customer=await db.get(Customer,scope[1])
        if not tenant or not tenant.is_active or not customer or customer.deleted_at or customer.tenant_id!=scope[0]:return None
        active=await db.scalar(select(FleetInvoiceApiKey.id).where(FleetInvoiceApiKey.tenant_id==scope[0],FleetInvoiceApiKey.customer_id==scope[1],FleetInvoiceApiKey.revoked_at.is_(None)))
        return config if active else None
    except (ValueError,TypeError,KeyError):return None


async def _deliver_payload(payload,config):
    import anyio,httpx
    from app.core import webhook_destination as boundary
    from app.services.provider_outbox_service import ProviderDeliveryError
    body=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    timestamp=str(int(datetime.now(timezone.utc).timestamp()))
    signature=hmac.new(os.environ[config['secret_env']].encode(),timestamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
    try:
        with anyio.fail_after(25):
            destination=await boundary.resolve_webhook_destination(config['url'])
            async with httpx.AsyncClient(timeout=httpx.Timeout(10,connect=3),follow_redirects=False,trust_env=False) as client:
                response=None
                for address in destination.addresses:
                    try:
                        response=await client.request('POST',httpx.URL(destination.original_url).copy_with(host=address),content=body,
                            headers={'Host':destination.host_header,'Content-Type':'application/json',
                                     'X-DBN-Event-Id':payload['event_id'],'X-DBN-Timestamp':timestamp,'X-DBN-Signature':'v1='+signature},
                            extensions={'sni_hostname':destination.tls_hostname})
                        break
                    except (httpx.ConnectError,httpx.ConnectTimeout):continue
                if response is None:raise ProviderDeliveryError('Fleet webhook connection failed.',retryable=True)
        if not 200<=response.status_code<300:
            raise ProviderDeliveryError('Fleet webhook rejected request.',retryable=response.status_code==429 or response.status_code>=500,response_code=response.status_code)
        return response.status_code
    except boundary.WebhookDestinationResolutionTimeout as exc:
        raise ProviderDeliveryError('Fleet webhook DNS timed out.',retryable=True) from exc
    except boundary.WebhookDestinationError as exc:
        raise ProviderDeliveryError('Fleet webhook destination rejected.',retryable=False) from exc
    except (httpx.HTTPError,TimeoutError) as exc:
        raise ProviderDeliveryError('Fleet webhook transport failed.',retryable=True) from exc


async def process_due_financial_wakeups(*,session_factory=None,limit=20):
    """Lease/commit before I/O; stale completions cannot overwrite a newer claim."""
    from datetime import timedelta
    from sqlalchemy import and_,or_
    from app.db.session import AsyncSessionLocal
    from app.services.provider_outbox_service import ProviderDeliveryError
    factory=session_factory or AsyncSessionLocal
    results={'claimed':0,'succeeded':0,'retried':0,'dead':0,'invalid':0}
    if not _enabled():return results
    now=datetime.now(timezone.utc);claims=[]
    async with factory() as db:
        events=(await db.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type==EVENT,
            or_(and_(ProviderOutboxEvent.status=='pending',ProviderOutboxEvent.available_at<=now),
                and_(ProviderOutboxEvent.status=='processing',ProviderOutboxEvent.locked_until<=now)))
            .order_by(ProviderOutboxEvent.available_at,ProviderOutboxEvent.id).limit(min(max(limit,1),100)).with_for_update(skip_locked=True))).scalars().all()
        for event in events:
            config=await _delivery_config(db,event)
            if not config:
                # Back off paused rows so one unconfigured customer cannot
                # starve configured customers behind the bounded claim window.
                event.status='pending';event.available_at=now+timedelta(seconds=60)
                event.lock_token=None;event.locked_at=None;event.locked_until=None
                results['paused']=results.get('paused',0)+1
                continue
            token=uuid4().hex;event.status='processing';event.lock_token=token
            event.locked_at=now;event.locked_until=now+timedelta(seconds=60)
            event.attempt_count+=1;event.last_attempt_at=now
            claims.append((event.id,token,dict(event.payload)))
        await db.commit()
    results['claimed']=len(claims)
    for event_id,token,payload in claims:
        # Re-read authorization/configuration immediately before every request.
        async with factory() as db:
            event=await db.get(ProviderOutboxEvent,event_id)
            if not event or event.status!='processing' or event.lock_token!=token:continue
            config=await _delivery_config(db,event)
        error=None;code=None
        if config:
            try:code=await _deliver_payload(payload,config)
            except ProviderDeliveryError as exc:error=exc
            except Exception:error=ProviderDeliveryError('Fleet webhook delivery failed.',retryable=True)
        async with factory() as db:
            event=await db.get(ProviderOutboxEvent,event_id)
            if not event or event.status!='processing' or event.lock_token!=token:continue
            current=datetime.now(timezone.utc)
            event.lock_token=None;event.locked_until=None;event.locked_at=None
            if not config:
                event.status='pending';event.attempt_count=max(event.attempt_count-1,0)
                event.available_at=current+timedelta(seconds=60);results['paused']=results.get('paused',0)+1
            elif error:
                event.last_response_code=error.response_code;event.last_error='Fleet webhook delivery failed.'
                if error.response_code==503:
                    event.status='pending';event.attempt_count=max(event.attempt_count-1,0)
                    event.available_at=current+timedelta(seconds=60);results['paused']=results.get('paused',0)+1
                elif error.retryable and event.attempt_count<12:
                    event.status='pending';event.available_at=current+timedelta(seconds=min(30*2**(event.attempt_count-1),3600));results['retried']+=1
                else:event.status='dead';results['dead']+=1
            else:
                event.status='succeeded';event.completed_at=current;event.last_error=None;event.last_response_code=code;results['succeeded']+=1
            await db.commit()
    return results


async def enqueue_invoice_financial_change(db,invoice):
    """Adjustment services already own the outer transaction and immutable audit."""
    if not destinations():return None
    from app.db.models.repair_order import RepairOrder
    order=await db.scalar(select(RepairOrder).where(RepairOrder.id==invoice.repair_order_id,RepairOrder.tenant_id==invoice.tenant_id))
    if order is None:return None
    return await enqueue_financial_wakeup(db,invoice=invoice,order=order,kind='invoice_changed')


async def enqueue_order_financial_change(db,order):
    """Publish supported RO corrections without exposing a new date-edit API."""
    if not destinations():return None
    from app.db.models.invoice import Invoice,InvoiceStatus
    invoice=await db.scalar(select(Invoice).where(Invoice.repair_order_id==order.id,Invoice.tenant_id==order.tenant_id,Invoice.status!=InvoiceStatus.CANCELLED))
    if invoice is None:return None
    return await enqueue_financial_wakeup(db,invoice=invoice,order=order,kind='invoice_changed')


async def enqueue_settlement_wakeup(db,settlement):
    """Called by the transactional source ledger, never by a read endpoint."""
    if not destinations():return None
    from app.db.models.invoice import Invoice
    from app.db.models.repair_order import RepairOrder
    pair=(await db.execute(select(Invoice,RepairOrder).join(RepairOrder,RepairOrder.id==Invoice.repair_order_id).where(
        Invoice.id==settlement.invoice_id,Invoice.tenant_id==settlement.tenant_id,
        RepairOrder.tenant_id==settlement.tenant_id,RepairOrder.customer_id==settlement.customer_id))).one_or_none()
    if pair is None:return None
    invoice,order=pair
    return await enqueue_financial_wakeup(db,invoice=invoice,order=order,kind='invoice_changed',
        settlement_event={'settlement_id':str(settlement.id),'sequence':settlement.last_event_sequence})
