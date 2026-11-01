"""Owner-reviewed source-debt collection; no remote financial actions."""
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_active_user,get_db,user_has_permission,CurrentUser
from app.db.models.user import UserRole
from app.db.models.source_debt_handoff import EtsReceiptUpdateTask
from app.schemas.source_debt_handoff import PreviewRequest,PrepareRequest,VersionRequest,SourceVersionRequest,AcknowledgeRequest,ReconcileRequest
from app.services import source_debt_handoff as service

router=APIRouter()

def staff(user:CurrentUser=Depends(get_current_active_user)):
    if user.role not in (UserRole.GARAGE_OWNER,UserRole.GARAGE_ADMIN) or not user.tenant_id or not user_has_permission(user,'payments'):
        service.fail('source_handoff_access_denied','Shop owner/admin payment permission required.',403)
    return user

def key(value):
    result=(value or '').strip()
    if not result or len(result)>255:service.fail('idempotency_key_required','A valid Idempotency-Key header is required.',422)
    return result

@router.post('/preview')
async def preview(body:PreviewRequest,db:AsyncSession=Depends(get_db),user=Depends(staff)):
    return await service.preview(db,user.tenant_id,body.source_invoice_id,body.target_customer_id)

@router.post('')
async def prepare(body:PrepareRequest,db:AsyncSession=Depends(get_db),user=Depends(staff),idempotency_key:str|None=Header(None)):
    row=await service.prepare(db,user.tenant_id,user,body,key(idempotency_key));await db.commit()
    return await service.summary(db,row)

@router.get('/ets-update-tasks')
async def tasks(state:str|None=None,handoff_id:UUID|None=None,skip:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:AsyncSession=Depends(get_db),user=Depends(staff)):
    filters=[EtsReceiptUpdateTask.tenant_id==user.tenant_id,EtsReceiptUpdateTask.deleted_at.is_(None)]
    if state:filters.append(EtsReceiptUpdateTask.state==state)
    if handoff_id:filters.append(EtsReceiptUpdateTask.handoff_id==handoff_id)
    rows=(await db.scalars(select(EtsReceiptUpdateTask).where(*filters).order_by(EtsReceiptUpdateTask.created_at,EtsReceiptUpdateTask.id).offset(skip).limit(limit))).all()
    total=await db.scalar(select(func.count()).select_from(EtsReceiptUpdateTask).where(*filters))
    return dict(items=[service.task_dto(t) for t in rows],total=total,skip=skip,limit=limit)

@router.post('/ets-update-tasks/{task_id}/claim')
async def claim(task_id:UUID,body:VersionRequest,db:AsyncSession=Depends(get_db),user=Depends(staff),idempotency_key:str|None=Header(None)):
    task=await service.task_for_tenant(db,user.tenant_id,task_id)
    task=await service.claim_task(db,task,user,body,key(idempotency_key));await db.commit()
    return service.task_dto(task)

@router.post('/ets-update-tasks/{task_id}/acknowledge')
async def acknowledge(task_id:UUID,body:AcknowledgeRequest,db:AsyncSession=Depends(get_db),user=Depends(staff),idempotency_key:str|None=Header(None)):
    task=await service.task_for_tenant(db,user.tenant_id,task_id)
    task=await service.acknowledge_task(db,task,user,body,key(idempotency_key));await db.commit()
    return service.task_dto(task)

@router.get('/{handoff_id}')
async def read(handoff_id:UUID,db:AsyncSession=Depends(get_db),user=Depends(staff)):
    return await service.summary(db,await service.get_handoff(db,user.tenant_id,handoff_id))

@router.post('/{handoff_id}/activate')
async def activate(handoff_id:UUID,body:SourceVersionRequest,db:AsyncSession=Depends(get_db),user=Depends(staff),idempotency_key:str|None=Header(None)):
    row=await service.get_handoff(db,user.tenant_id,handoff_id)
    row,replay=await service.activate(db,row,user,body,key(idempotency_key));await db.commit()
    return dict(handoff=await service.summary(db,row),native_invoice_id=str(row.native_invoice_id),already_active=replay)

@router.post('/{handoff_id}/reconcile')
async def reconcile(handoff_id:UUID,body:ReconcileRequest,db:AsyncSession=Depends(get_db),user=Depends(staff),idempotency_key:str|None=Header(None)):
    row=await service.get_handoff(db,user.tenant_id,handoff_id)
    row,conflict=await service.reconcile(db,row,user,body,key(idempotency_key));await db.commit()
    result=dict(handoff=await service.summary(db,row),conflict=conflict)
    return JSONResponse(result,status_code=409) if conflict else result
