"""Dedicated C1 manager configuration and authorized intake projection."""
import json
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Response, HTTPException
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_active_user, get_db
from app.db.models.user import User
from app.schemas.customer_pricing import CustomerPricingWrite
from app.services import customer_pricing as policy, parts_pricing as pricing
from app.services.parts_operations_service import validate_idempotency_key, canonical_fingerprint, find_idempotent_response, begin_idempotency, complete_idempotency


async def private_response(response:Response):response.headers['Cache-Control']='private, no-store'
router=APIRouter(dependencies=[Depends(private_response)])


@router.get('/{customer_id}/pricing-policy')
async def get_policy(customer_id:UUID,db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    tenant=await pricing.authorize(db,actor,manager=True)
    customer=await policy.live_customer(db,actor.tenant_id,customer_id)
    return await policy.config_view(db,tenant,customer)


@router.put('/{customer_id}/pricing-policy')
async def put_policy(customer_id:UUID,body:CustomerPricingWrite,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    await pricing.authorize(db,actor,manager=True)
    key=validate_idempotency_key(idempotency_key)
    await pricing.lock_tenant_financials(db,actor.tenant_id)
    await policy.live_customer(db,actor.tenant_id,customer_id,lock=True)
    digest=canonical_fingerprint(route=f'customer:{customer_id}:pricing',principal_id=actor.id,payload=body.model_dump(mode='json'))
    try: receipt=await find_idempotent_response(db,tenant_id=actor.tenant_id,family='c1_config',key=key,fingerprint=digest)
    except HTTPException as exc:
        if exc.status_code==409:pricing.fail('idempotency_conflict','This action key already belongs to a different request.',409)
        raise
    if receipt:return json.loads(receipt.response_body)
    receipt=begin_idempotency(tenant_id=actor.tenant_id,family='c1_config',key=key,fingerprint=digest);db.add(receipt)
    response=await policy.write_config(db,actor,body,customer_id)
    await db.flush();complete_idempotency(receipt,status_code=200,body=response);await db.commit()
    return response


@router.get('/{customer_id}/pricing-policy/history')
async def history(customer_id:UUID,limit:int=Query(25,ge=1,le=100),cursor:str|None=None,db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    await pricing.authorize(db,actor,manager=True);await policy.live_customer(db,actor.tenant_id,customer_id)
    scope=['c1_policy_history',str(actor.tenant_id),str(customer_id)];key=pricing.cursor_decode(cursor,scope)
    query=select(policy.Event).where(policy.Event.tenant_id==actor.tenant_id,policy.Event.entity_type=='customer_policy',policy.Event.entity_id==customer_id)
    if key:query=query.where(tuple_(policy.Event.new_version,policy.Event.id)<tuple_(key[0],UUID(key[1])))
    rows=list((await db.scalars(query.order_by(policy.Event.new_version.desc(),policy.Event.id.desc()).limit(limit+1))).all())
    return {'schema_version':1,'items':[{'id':str(row.id),'version':row.new_version,'before':row.before_values,'after':row.after_values,'actor_user_id':str(row.actor_id),
            'actor_display_name':row.actor_name,'reason':row.reason,'occurred_at':row.created_at.isoformat()} for row in rows[:limit]],
            'next_cursor':pricing.cursor_encode(scope,[rows[limit-1].new_version,str(rows[limit-1].id)]) if len(rows)>limit else None}


@router.get('/{customer_id}/pricing-preview')
async def intake_preview(customer_id:UUID,vehicle_id:UUID|None=None,pricing_presentation:str|None=Query(None,pattern='^(shop|fleet)$'),db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    _,view=await policy.capture(db,actor,customer_id,vehicle_id,presentation=pricing_presentation,lock=False)
    return view
