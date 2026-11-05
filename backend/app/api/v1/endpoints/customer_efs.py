"""Dedicated EFS entry points; no secret-bearing request or response caching."""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter,Depends,Header,Request,Response
from app.core.dependencies import get_current_active_user,get_db,CurrentUser
from app.core.payment_privacy import SensitivePaymentRoute
from app.core.rate_limit import limiter
from app.db.models.user import UserRole
from app.schemas.efs_submission import EfsSubmit,GuestEfsSubmit,EfsReveal,EfsVerify
from app.schemas.invoice_settlement import PaymentAttemptResponse
from app.services import customer_efs as service

async def private(response:Response):
    response.headers.update({'Cache-Control':'no-store, private','Pragma':'no-cache','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})
payments_router=APIRouter(route_class=SensitivePaymentRoute,dependencies=[Depends(private)])
guest_router=APIRouter(route_class=SensitivePaymentRoute,dependencies=[Depends(private)])

@payments_router.post('/invoices/{invoice_id}/efs-submissions',response_model=PaymentAttemptResponse)
@limiter.limit('10/minute')
async def submit_customer_efs(request:Request,invoice_id:UUID,body:EfsSubmit,idempotency_key:Optional[str]=Header(default=None,alias='Idempotency-Key'),db=Depends(get_db),actor:CurrentUser=Depends(get_current_active_user)):
    from app.api.v1.endpoints.invoice_settlements import invoice_for_principal,attempt_response
    from app.services.financial_transaction_lock import lock_tenant_financials
    if actor.role!=UserRole.CUSTOMER:service.fail('invoice_not_found','Invoice not found.',404)
    await lock_tenant_financials(db,actor.tenant_id)
    invoice,tenant,customer_id=await invoice_for_principal(db,invoice_id,actor)
    a,s=await service.submit(db,invoice=invoice,tenant=tenant,customer_id=customer_id,actor=actor,body=body,idempotency_key=idempotency_key)
    await db.commit()
    return await attempt_response(db,a,s,tenant,audience='customer',current_user=actor)

@guest_router.post('/efs-submissions',response_model=PaymentAttemptResponse)
@limiter.limit('10/minute')
async def submit_guest_efs(request:Request,body:GuestEfsSubmit,idempotency_key:Optional[str]=Header(default=None,alias='Idempotency-Key'),db=Depends(get_db)):
    from app.api.v1.endpoints.invoice_access import _load_db048_guest_context
    from app.api.v1.endpoints.invoice_settlements import attempt_response
    invoice,_,customer,tenant=await _load_db048_guest_context(db,body.token.get_secret_value())
    a,s=await service.submit(db,invoice=invoice,tenant=tenant,customer_id=customer.id,actor=None,body=body,idempotency_key=idempotency_key)
    await db.commit()
    return await attempt_response(db,a,s,tenant,audience='guest')

@payments_router.post('/attempts/{attempt_id}/efs-code/reveal')
@limiter.limit('5/minute')
async def reveal_efs_code(request:Request,attempt_id:UUID,body:EfsReveal,db=Depends(get_db),actor:CurrentUser=Depends(get_current_active_user)):
    value=await service.reveal(db,attempt_id,actor,body)
    await db.commit()
    return value

@payments_router.post('/attempts/{attempt_id}/efs-verification',response_model=PaymentAttemptResponse)
@limiter.limit('10/minute')
async def verify_efs_receipt(request:Request,attempt_id:UUID,body:EfsVerify,idempotency_key:Optional[str]=Header(default=None,alias='Idempotency-Key'),db=Depends(get_db),actor:CurrentUser=Depends(get_current_active_user)):
    from app.api.v1.endpoints.invoice_settlements import attempt_response
    context=None
    if body.action=='resolve_received_difference':
        from app.core.payment_step_up import get_payment_step_up_context
        from app.core.dependencies import get_token_from_request
        from fastapi.security import HTTPAuthorizationCredentials
        scheme,_,bearer=request.headers.get('Authorization','').partition(' ')
        credentials=HTTPAuthorizationCredentials(scheme='Bearer',credentials=bearer) if scheme.lower()=='bearer' and bearer else None
        primary=await get_token_from_request(request,credentials=credentials,access_token=request.cookies.get('access_token'))
        context=await get_payment_step_up_context(request,raw_grant=request.headers.get('X-Step-Up-Authorization'),primary_token=primary,current_user=actor)
    a,s=await service.verify(db,attempt_id,actor,body,idempotency_key,step_up_context=context)
    tenant=await service.tenant_for(db,a.tenant_id)
    await db.commit()
    return await attempt_response(db,a,s,tenant,audience='staff',current_user=actor)
