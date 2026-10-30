"""Complete current-invoice authority; RO visibility never grants billing access."""
from datetime import date,datetime
from decimal import Decimal
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from sqlalchemy import and_,select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.endpoints.fleet_invoice_exports import _active_key
from app.api.v1.endpoints.fleet_repair_history_exports import _digest,_utc,MAX_REPAIR_HISTORY_ROWS
from app.core.dependencies import get_db
from app.db.models.fleet_invoice_api_key import FleetInvoiceApiKey
from app.db.models.historical_invoice_export import HistoricalInvoiceMapping
from app.db.models.invoice import Invoice,InvoiceStatus
from app.db.models.repair_order import RepairOrder,RepairOrderStatus
from app.db.models.vehicle import Vehicle

router=APIRouter()
VERSION='db094-repair-financial-v1'


def _json_value(value):
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,(datetime,date)):return value.isoformat()
    return value


def _lines(invoice):
    # Export only immutable financial line facts, never notes or contact fields.
    snapshot=invoice.line_items_snapshot or {}
    allowed={'description','name','hours','quantity','unit_price','total_price','total_cost','rate','hourly_rate'}
    return {kind:[{k:_json_value(v) for k,v in line.items() if k in allowed and isinstance(v,(str,int,float,Decimal,type(None)))}
                  for line in snapshot.get(kind,[]) if isinstance(line,dict)]
            for kind in ('labor','parts')}


def _invoice_payload(invoice,order):
    imported=invoice.source=='easy_truck_shop_import' or order.source=='easy_truck_shop_import'
    if imported:
        issued=invoice.ets_invoiced_at
        basis='preserved_issue_date' if issued else 'unknown'
    else:
        issued=_utc(invoice.created_at).date() if invoice.created_at else None
        basis='native_issue_timestamp' if issued else 'unknown'
    value={'invoice_id':str(invoice.id),'invoice_number':invoice.invoice_number,
           'status':'current_finalized','invoice_date':issued.isoformat() if issued else None,
           'invoice_date_basis':basis,'currency':'USD','total_amount':format(invoice.total_amount,'.2f'),
           'line_items':_lines(invoice),'pdf_sha256':None}
    value['revision']=_digest(value)
    return value


@router.get('/repair-orders/financial')
async def repair_financial_manifest(request:Request,response:Response,
    db:AsyncSession=Depends(get_db),key:FleetInvoiceApiKey=Depends(_active_key)):
    if request.query_params:
        raise HTTPException(422,detail={'code':'invalid_financial_filters','message':'A complete scoped financial snapshot is required.'})
    # The active unique index is canonical. Include a draft then deny it; never
    # select an older visible invoice just because the actual active one is hidden.
    rows=(await db.execute(select(RepairOrder,Vehicle,Invoice,HistoricalInvoiceMapping)
        .join(Vehicle,and_(Vehicle.id==RepairOrder.vehicle_id,Vehicle.tenant_id==key.tenant_id))
        .outerjoin(Invoice,and_(Invoice.repair_order_id==RepairOrder.id,
                               Invoice.tenant_id==key.tenant_id,Invoice.status!=InvoiceStatus.CANCELLED))
        .outerjoin(HistoricalInvoiceMapping,and_(HistoricalInvoiceMapping.invoice_id==Invoice.id,HistoricalInvoiceMapping.tenant_id==key.tenant_id))
        .where(RepairOrder.tenant_id==key.tenant_id,RepairOrder.customer_id==key.customer_id,
               RepairOrder.deleted_at.is_(None),RepairOrder.is_internal.is_(False),
               RepairOrder.status.in_((RepairOrderStatus.COMPLETED,RepairOrderStatus.INVOICED,RepairOrderStatus.PAID)))
        .order_by(RepairOrder.id).limit(MAX_REPAIR_HISTORY_ROWS+1))).all()
    if len(rows)>MAX_REPAIR_HISTORY_ROWS:
        raise HTTPException(409,detail={'code':'financial_snapshot_too_large','message':'Complete financial snapshot exceeds its limit.'})
    seen=set();items=[]
    for order,vehicle,invoice,mapping in rows:
        if order.id in seen:
            raise HTTPException(409,detail={'code':'ambiguous_current_invoice','message':'Current invoice requires review.'})
        seen.add(order.id)
        authorization='unavailable';payload=None
        if invoice and not invoice.deleted_at and not invoice.is_internal and not invoice.voided_at:
            if invoice.status==InvoiceStatus.DRAFT:
                authorization='not_finalized'
            elif invoice.billed_customer_id==key.customer_id or (invoice.billed_customer_id is None and mapping and mapping.target_customer_id==key.customer_id):
                authorization='authorized';payload=_invoice_payload(invoice,order)
            else:
                authorization='attribution_required'
        completed=_utc(order.work_completed_at) if order.work_completed_at else None
        item={'repair_order_id':str(order.id),'order_number':order.order_number,'vehicle_id':str(vehicle.id),
              'vin':vehicle.vin,'unit_number':vehicle.unit_number,'description':order.description,
              'work_completed_at':completed.isoformat() if completed else None,
              'service_date':completed.date().isoformat() if completed else None,
              'authorization':authorization,'invoice':payload}
        item['revision']=_digest(item);items.append(item)
    scope={'version':VERSION,'shop_id':str(key.tenant_id),'customer_id':str(key.customer_id),'items':items}
    response.headers['Cache-Control']='private, no-store'
    return {**scope,'complete':True,'count':len(items),'snapshot_id':_digest(scope)}
