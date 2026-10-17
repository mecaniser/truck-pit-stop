"""Explicit private price configuration and safe contextual confirmation."""
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, HTTPException, Body, Response
from sqlalchemy import select, func, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_active_user, get_db
from app.db.models.user import User
from app.schemas import parts_pricing as schema
from app.services import parts_pricing as pricing
from app.services.parts_pricing_rules import PricePolicy, resolve_price, cents, fail

async def private_response(response: Response):
    response.headers['Cache-Control'] = 'private, no-store'

router=APIRouter(dependencies=[Depends(private_response)])


@router.get('/matrices')
async def matrices(include_archived:bool=False,limit:int=Query(50,ge=1,le=100),cursor:str|None=None,db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    await pricing.authorize(db,actor,manager=True)
    scope=['matrices',str(actor.tenant_id),include_archived];key=pricing.cursor_decode(cursor,scope)
    stmt=select(pricing.Matrix).where(pricing.Matrix.tenant_id==actor.tenant_id)
    if not include_archived: stmt=stmt.where(pricing.Matrix.archived_at.is_(None))
    if key: stmt=stmt.where(tuple_(func.lower(pricing.Matrix.name),pricing.Matrix.id)>tuple_(key[0],UUID(key[1])))
    rows=list((await db.scalars(stmt.order_by(func.lower(pricing.Matrix.name),pricing.Matrix.id).limit(limit+1))).all())
    return {'schema_version':1,'items':[await pricing.matrix_view(db,r,detail=False) for r in rows[:limit]],'next_cursor':pricing.cursor_encode(scope,[rows[limit-1].name.lower(),str(rows[limit-1].id)]) if len(rows)>limit else None}


@router.get('/default')
async def get_default(db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    await pricing.authorize(db,actor,manager=True)
    return await pricing.default_view(db,actor.tenant_id)


@router.put('/default')
async def set_default(body:schema.DefaultUpdate,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    return await pricing.config_command(db,actor,idempotency_key,'default:update',body.model_dump(mode='json'),lambda:pricing.set_default(db,actor,body))


@router.post('/matrices',status_code=201)
async def create_matrix(body:schema.MatrixCreate,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    return await pricing.config_command(db,actor,idempotency_key,'matrix:create',body.model_dump(mode='json'),lambda:pricing.write_matrix(db,actor,body))


@router.get('/matrices/{matrix_id}')
async def get_matrix(matrix_id:UUID,db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    await pricing.authorize(db,actor,manager=True)
    return {'schema_version':1,'matrix':await pricing.matrix_view(db,await pricing.get_matrix(db,actor.tenant_id,matrix_id))}


@router.put('/matrices/{matrix_id}')
async def update_matrix(matrix_id:UUID,body:schema.MatrixUpdate,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    return await pricing.config_command(db,actor,idempotency_key,f'matrix:{matrix_id}:update',body.model_dump(mode='json'),lambda:pricing.write_matrix(db,actor,body,matrix_id))


@router.post('/matrices/{matrix_id}/archive')
async def archive_matrix(matrix_id:UUID,body:schema.MatrixArchive,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    return await pricing.config_command(db,actor,idempotency_key,f'matrix:{matrix_id}:archive',body.model_dump(mode='json'),lambda:pricing.write_matrix(db,actor,body,matrix_id,'archive'))


@router.post('/matrices/{matrix_id}/restore')
async def restore_matrix(matrix_id:UUID,body:schema.MatrixArchive,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    return await pricing.config_command(db,actor,idempotency_key,f'matrix:{matrix_id}:restore',body.model_dump(mode='json'),lambda:pricing.write_matrix(db,actor,body,matrix_id,'restore'))


@router.get('/matrices/{matrix_id}/revisions')
async def matrix_revisions(matrix_id:UUID,limit:int=Query(50,ge=1,le=100),cursor:str|None=None,db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    await pricing.authorize(db,actor,manager=True);await pricing.get_matrix(db,actor.tenant_id,matrix_id)
    scope=['revisions',str(actor.tenant_id),str(matrix_id)];key=pricing.cursor_decode(cursor,scope)
    stmt=select(pricing.Revision).where(pricing.Revision.tenant_id==actor.tenant_id,pricing.Revision.matrix_id==matrix_id)
    if key: stmt=stmt.where(tuple_(pricing.Revision.revision,pricing.Revision.id)<tuple_(key[0],UUID(key[1])))
    rows=list((await db.scalars(stmt.order_by(pricing.Revision.revision.desc(),pricing.Revision.id.desc()).limit(limit+1))).all())
    return {'schema_version':1,'items':[{'id':str(r.id),'matrix_id':str(r.matrix_id),'revision':r.revision,'name':r.name_snapshot,'bands':r.bands,'created_at':r.created_at.isoformat(),'created_by_user_id':str(r.created_by)} for r in rows[:limit]],'next_cursor':pricing.cursor_encode(scope,[rows[limit-1].revision,str(rows[limit-1].id)]) if len(rows)>limit else None}


@router.get('/inventory/{inventory_id}/pricing-policy')
async def get_policy(inventory_id:UUID,db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    await pricing.authorize(db,actor,manager=True)
    return pricing.policy_view((await pricing.inventory(db,actor.tenant_id,[inventory_id]))[inventory_id])


@router.patch('/inventory/{inventory_id}/pricing-policy')
async def patch_policy(inventory_id:UUID,body:schema.InventoryPolicyPatch,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    async def apply():
        item=(await pricing.inventory(db,actor.tenant_id,[inventory_id],lock=True))[inventory_id]
        changes=body.model_dump(exclude_unset=True);changes.pop('expected_pricing_version')
        await pricing.patch_inventory(db,actor,item,changes,body.expected_pricing_version)
        return pricing.policy_view(item)
    return await pricing.config_command(db,actor,idempotency_key,f'inventory:{inventory_id}:policy',body.model_dump(mode='json',exclude_unset=True),apply)


@router.get('/events')
async def events(entity_type:str,entity_id:UUID,limit:int=Query(50,ge=1,le=100),cursor:str|None=None,db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    await pricing.authorize(db,actor,manager=True)
    if entity_type not in {'matrix','default_policy','inventory','parts_usage','counter_sale_line'}: fail('invalid_entity','Unsupported pricing history type.')
    scope=['events',str(actor.tenant_id),entity_type,str(entity_id)];key=pricing.cursor_decode(cursor,scope)
    stmt=select(pricing.Event).where(pricing.Event.tenant_id==actor.tenant_id,pricing.Event.entity_type==entity_type,pricing.Event.entity_id==entity_id)
    if key: stmt=stmt.where(tuple_(pricing.Event.created_at,pricing.Event.id)<tuple_(datetime.fromisoformat(key[0]),UUID(key[1])))
    rows=list((await db.scalars(stmt.order_by(pricing.Event.created_at.desc(),pricing.Event.id.desc()).limit(limit+1))).all())
    users={u.id:u for u in (await db.scalars(select(User).where(User.tenant_id==actor.tenant_id,User.id.in_({r.actor_id for r in rows[:limit]})))).all()} if rows else {}
    fields={'name','bands','archived_at','matrix_id','cost','selling_price','pricing_cost_floor','minimum_sale_price','fixed_sales_price','quantity','unit_cost','unit_price','list_price','total_price','charged_unit_price','list_unit_price'}
    def scalar(v): return json.dumps(v,sort_keys=True,separators=(',',':')) if isinstance(v,(list,dict)) else (str(v) if v is not None else None)
    items=[]
    for r in rows[:limit]:
        user=users.get(r.actor_id)
        items.append({'id':str(r.id),'entity_type':r.entity_type,'entity_id':str(r.entity_id),'event_type':r.event_type,'occurred_at':r.created_at.isoformat(),'actor_user_id':str(r.actor_id),'actor_display_name':f'{user.first_name} {user.last_name}'.strip() if user else None,'correlation_id':str(r.correlation_id),'old_version':r.old_version,'new_version':r.new_version,'reason':r.reason,'snapshot_id':r.identity_snapshot.get('snapshot_id'),'changes':[{'field':k,'before':scalar(r.before_values.get(k)),'after':scalar(r.after_values.get(k))} for k in sorted(fields & (set(r.before_values)|set(r.after_values))) if r.before_values.get(k)!=r.after_values.get(k)]})
    return {'schema_version':1,'items':items,'next_cursor':pricing.cursor_encode(scope,[rows[limit-1].created_at.isoformat(),str(rows[limit-1].id)]) if len(rows)>limit else None}


def evaluate(item,policy,known):
    result={'status':'blocked','unit_price':None,'source':None,'pricing_basis':None,'effective_minimum':None,'band':None,'gross_profit':None,'markup_percent':None,'margin_percent':None,'warnings':[],'errors':[]}
    try:
        value=resolve_price(item,policy,actual_cost_known=known)
        snap=value.snapshot;result.update(status='priced',unit_price=cents(value.charged),source=snap['source'],pricing_basis=snap['pricing_basis'],effective_minimum=snap['effective_minimum'],band=snap['matrix']['band'] if snap['matrix'] else None)
        if known:
            profit=value.charged-value.actual_cost
            result.update(gross_profit=cents(profit),markup_percent=cents(profit/value.actual_cost*100) if value.actual_cost else None,margin_percent=cents(profit/value.charged*100) if value.charged else None)
        if value.warning: result['warnings']=[{'code':value.warning,'message':'Catalog price used because the calculated price has no positive cost basis.'}]
    except HTTPException as exc:
        result['errors']=[exc.detail if isinstance(exc.detail,dict) else {'code':'part_price_required','message':str(exc.detail)}]
    return result


@router.post('/preview')
async def preview(body:schema.SamplePreview | schema.InventoryPreview = Body(..., discriminator="mode"),db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    await pricing.authorize(db,actor,manager=True)
    current=await pricing.selected_policy(db,actor.tenant_id)
    proposed=PricePolicy(matrix_id='draft',revision_id='draft',revision=1,name='Draft',bands=[b.model_dump(mode='json') for b in body.bands])
    cases=[]
    if body.mode=='inventory':
        rows=await pricing.inventory(db,actor.tenant_id,body.inventory_ids)
        sources=[(str(i),str(i),rows[i].name,rows[i],not(rows[i].is_placeholder and not rows[i].cost)) for i in body.inventory_ids]
    else:
        sources=[(s.sample_key,None,s.label or s.sample_key,SimpleNamespace(cost=s.actual_unit_cost,selling_price=s.catalog_unit_price,pricing_cost_floor=s.pricing_cost_floor,minimum_sale_price=s.minimum_sale_price,fixed_sales_price=s.fixed_sales_price,is_placeholder=False),s.actual_unit_cost is not None) for s in body.samples]
    for key,inventory_id,label,item,known in sources:
        cases.append({'sample_key':key,'inventory_id':inventory_id,'label':label,'actual_unit_cost':cents(item.cost) if known else None,'actual_cost_known':known,'catalog_unit_price':cents(item.selling_price) if item.selling_price is not None else None,'current':evaluate(item,current,known),'proposed':evaluate(item,proposed,known)})
    return {'schema_version':1,'currency':'USD','current_default':await pricing.default_view(db,actor.tenant_id),'cases':cases}


@router.post('/resolve')
async def resolve(body:schema.ResolveRequest,db:AsyncSession=Depends(get_db),actor:User=Depends(get_current_active_user)):
    from app.services.parts_pricing_planner import build_plan
    return (await build_plan(db,actor,body)).response
