from datetime import date
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, Field, field_validator
from sqlalchemy import select, func, and_
from app.core.dependencies import get_db,get_current_active_user
from app.core.pagination import paginated_or_list
from app.db.models.visit_request import VisitRequest
from app.db.models.service import Service
from app.db.models.user import UserRole
from app.services import booking_payments as booking
from app.services import booking_fulfillment as fulfillment
from datetime import datetime

router=APIRouter()
staff_router=APIRouter()
class VisitRequestCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    service_id:UUID
    vehicle_id:UUID|None=None
    preferred_date:date|None=None
    customer_notes:str|None=None

def response(row,service_name):
    return {'id':str(row.id),'booking_kind':'request','request_reference':row.request_reference,'status':row.status,'preferred_date':row.preferred_date,'service_id':str(row.service_id),'service_name':service_name,'vehicle_id':str(row.vehicle_id) if row.vehicle_id else None,'created_at':row.created_at}

@router.post('',status_code=201)
async def create_visit_request(body:VisitRequestCreate,db=Depends(get_db),actor=Depends(get_current_active_user),idempotency_key:str|None=Header(None,alias='Idempotency-Key')):
    request_key=booking.key(idempotency_key)
    if actor.role!=UserRole.CUSTOMER or not actor.tenant_id or not actor.customer_id: booking.fail('visit_request_unavailable','Visit requests are unavailable.',404)
    await fulfillment.request_lock(db,actor.tenant_id,request_key)
    tenant,service=await booking.principal(db,actor,body.service_id,body.vehicle_id)
    fingerprint=booking.digest({**body.model_dump(),'customer_id':actor.customer_id})
    existing=await db.scalar(select(VisitRequest).where(VisitRequest.tenant_id==tenant.id,VisitRequest.idempotency_key==request_key))
    if existing:
        if existing.customer_id!=actor.customer_id or existing.request_sha256!=fingerprint:booking.fail('idempotency_key_reused','This request key was already used.')
        return await fulfillment.request_dto(db,existing,actor)
    row=VisitRequest(id=uuid4(),tenant_id=tenant.id,customer_id=actor.customer_id,service_id=service.id,vehicle_id=body.vehicle_id,preferred_date=body.preferred_date,customer_notes=body.customer_notes,status='requested',request_reference=f'VR-{uuid4().hex[:12].upper()}',idempotency_key=request_key,request_sha256=fingerprint)
    db.add(row);await db.commit();await db.refresh(row)
    return await fulfillment.request_dto(db,row,actor)

@staff_router.get('')
@router.get('')
async def list_visit_requests(skip:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=100),paginated:bool=False,db=Depends(get_db),actor=Depends(get_current_active_user),customer_id:UUID|None=None):
    if not actor.tenant_id or actor.role not in {UserRole.CUSTOMER,*booking.STAFF}:booking.fail('visit_requests_unavailable','Visit requests are unavailable.',404)
    filters=[VisitRequest.tenant_id==actor.tenant_id,VisitRequest.deleted_at.is_(None)]
    if actor.role==UserRole.CUSTOMER:
        if not actor.customer_id:booking.fail('visit_requests_unavailable','Visit requests are unavailable.',404)
        filters.append(VisitRequest.customer_id==actor.customer_id)
    elif customer_id:
        authorized=await db.scalar(select(booking.Customer.id).where(booking.Customer.id==customer_id,booking.Customer.tenant_id==actor.tenant_id,booking.Customer.deleted_at.is_(None)))
        if not authorized:booking.fail('customer_unavailable','Customer not found.',404)
        filters.append(VisitRequest.customer_id==customer_id)
    total=await db.scalar(select(func.count(VisitRequest.id)).where(*filters))
    rows=(await db.execute(select(VisitRequest,Service.name).join(Service,and_(Service.id==VisitRequest.service_id,Service.tenant_id==VisitRequest.tenant_id)).where(*filters).order_by(VisitRequest.created_at.desc()).offset(skip).limit(limit))).all()
    return paginated_or_list([await fulfillment.request_dto(db,row,actor) for row,name in rows],total,skip,limit,paginated)


class VisitReviewBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
    internal_note: StrictStr | None = Field(default=None,max_length=4000)

class VisitAcceptBody(VisitReviewBody):
    arrival_date: date

    @field_validator('arrival_date',mode='before')
    @classmethod
    def calendar_only(cls,value):
        if isinstance(value,datetime):raise ValueError('Use an ISO calendar date')
        if isinstance(value,str) and (len(value)!=10 or value[4]!='-' or value[7]!='-'):raise ValueError('Use an ISO calendar date')
        return value

class VisitWithdrawBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
    reason: StrictStr | None = Field(default=None,max_length=4000)

class VisitFulfillBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
    repair_order_id: UUID
    reason: StrictStr = Field(min_length=3,max_length=4000)
    expected_vehicle_id: UUID | None = None

@staff_router.post('/{request_id}/review')
async def review_request(request_id:UUID,body:VisitReviewBody,db=Depends(get_db),actor=Depends(get_current_active_user),idempotency_key:str|None=Header(None,alias='Idempotency-Key')):
    return await fulfillment.request_action(db,actor,request_id,'review',body,idempotency_key)

@staff_router.post('/{request_id}/accept')
async def accept_request(request_id:UUID,body:VisitAcceptBody,db=Depends(get_db),actor=Depends(get_current_active_user),idempotency_key:str|None=Header(None,alias='Idempotency-Key')):
    return await fulfillment.request_action(db,actor,request_id,'accept',body,idempotency_key)

@staff_router.post('/{request_id}/decline')
async def decline_request(request_id:UUID,body:VisitReviewBody,db=Depends(get_db),actor=Depends(get_current_active_user),idempotency_key:str|None=Header(None,alias='Idempotency-Key')):
    return await fulfillment.request_action(db,actor,request_id,'decline',body,idempotency_key)

@staff_router.post('/{request_id}/withdraw')
async def withdraw_request(request_id:UUID,body:VisitWithdrawBody,db=Depends(get_db),actor=Depends(get_current_active_user),idempotency_key:str|None=Header(None,alias='Idempotency-Key')):
    return await fulfillment.request_action(db,actor,request_id,'withdraw',body,idempotency_key)

@staff_router.post('/{request_id}/fulfill')
async def fulfill_request(request_id:UUID,body:VisitFulfillBody,db=Depends(get_db),actor=Depends(get_current_active_user),idempotency_key:str|None=Header(None,alias='Idempotency-Key')):
    return await fulfillment.request_action(db,actor,request_id,'fulfill',body,idempotency_key)
