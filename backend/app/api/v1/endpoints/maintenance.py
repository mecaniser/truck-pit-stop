"""Private, currently authorized DB134 program and maintenance work commands."""
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_active_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas import maintenance as wire
from app.services import maintenance as service


class MaintenanceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validate(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                field = next((str(part) for issue in error.errors() for part in reversed(issue['loc']) if part not in {'body', 'query', 'path'}), None)
                service.fail('maintenance_invalid_input', 'Check the maintenance fields and try again.', 422, **({'field': field} if field else {}))
        return validate


def private_response(response: Response):
    response.headers['Cache-Control'] = 'private, no-store'


router = APIRouter(route_class=MaintenanceRoute, dependencies=[Depends(private_response)])
work_router = APIRouter(route_class=MaintenanceRoute, dependencies=[Depends(private_response)])
Db = Annotated[AsyncSession, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_active_user)]
Key = Annotated[str, Header(alias='Idempotency-Key')]


@router.get('/vehicles/{vehicle_id}/maintenance-programs')
async def vehicle_programs(vehicle_id: UUID, db: Db, current_user: Actor, channel: wire.Channel,
                           include_archived: bool = False, skip: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    return await service.program_page(db, current_user, channel, vehicle_id=vehicle_id, include_archived=include_archived, skip=skip, limit=limit)


@router.get('/maintenance-programs')
async def programs(db: Db, current_user: Actor, channel: wire.Channel, vehicle_id: UUID | None = None, customer_id: UUID | None = None,
                   state: Literal['overdue', 'due', 'unknown', 'current', 'in_work', 'review_required'] | None = None,
                   search: str | None = Query(None, max_length=160), include_archived: bool = False,
                   skip: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    return await service.program_page(db, current_user, channel, vehicle_id=vehicle_id, customer_id=customer_id, state=state,
                                      search=search, include_archived=include_archived, skip=skip, limit=limit)


@router.post('/vehicles/{vehicle_id}/maintenance-programs', status_code=201)
async def create_program(vehicle_id: UUID, body: wire.ProgramCreate, response: Response, key: Key, db: Db, current_user: Actor):
    result = await service.program_command(db, current_user, vehicle_id, body, key)
    if result['replayed']:
        response.status_code = 200
    return result


@router.patch('/vehicles/{vehicle_id}/maintenance-programs/{program_id}')
async def update_program(vehicle_id: UUID, program_id: UUID, body: wire.ProgramUpdate, key: Key, db: Db, current_user: Actor):
    return await service.program_command(db, current_user, vehicle_id, body, key, program_id=program_id)


@router.post('/vehicles/{vehicle_id}/maintenance-programs/{program_id}/archive')
async def archive_program(vehicle_id: UUID, program_id: UUID, body: wire.ArchiveCommand, key: Key, db: Db, current_user: Actor):
    return await service.program_command(db, current_user, vehicle_id, body, key, program_id=program_id, action='archive')


@router.post('/vehicles/{vehicle_id}/maintenance-programs/{program_id}/restore')
async def restore_program(vehicle_id: UUID, program_id: UUID, body: wire.ArchiveCommand, key: Key, db: Db, current_user: Actor):
    return await service.program_command(db, current_user, vehicle_id, body, key, program_id=program_id, action='restore')


@router.get('/vehicles/{vehicle_id}/maintenance-programs/{program_id}/history')
async def program_history(vehicle_id: UUID, program_id: UUID, db: Db, current_user: Actor, channel: wire.Channel,
                          skip: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    return await service.program_history(db, current_user, channel, vehicle_id, program_id, skip=skip, limit=limit)


@router.post('/vehicles/{vehicle_id}/maintenance-readings', status_code=201)
async def record_reading(vehicle_id: UUID, body: wire.ReadingCreate, response: Response, key: Key, db: Db, current_user: Actor):
    result = await service.reading_command(db, current_user, vehicle_id, body, key)
    if result['replayed']:
        response.status_code = 200
    return result


@router.post('/vehicles/{vehicle_id}/maintenance-target-preview')
async def target_preview(vehicle_id: UUID, body: Annotated[wire.ConfigPreview | wire.CompletionPreview | wire.EvidencePreview, Body(discriminator='purpose')], db: Db, current_user: Actor):
    return await service.target_preview(db, current_user, vehicle_id, body)


@work_router.post('/vehicles/{vehicle_id}/maintenance-work-preview')
async def work_preview(vehicle_id: UUID, body: wire.WorkRequest, db: Db, current_user: Actor):
    return await service.work_preview(db, current_user, vehicle_id, body)


@work_router.post('/vehicles/{vehicle_id}/maintenance-work', status_code=201)
async def create_work(vehicle_id: UUID, body: wire.WorkCommit, response: Response, key: Key, db: Db, current_user: Actor):
    try:
        result = await service.work_command(db, current_user, vehicle_id, body, key)
    except HTTPException as error:
        detail = error.detail
        if isinstance(detail, dict) and ((detail.get('preview') or {}).get('schema_version') is not None or detail.get('code') in {
            'bundle_availability_changed', 'insufficient_stock', 'pricing_preview_changed', 'account_pricing_changed', 'core_requires_review'}):
            # A failed aggregate command rolls back all staged work before a
            # read-only retry preview. Never expose a raw P1 detail projection.
            await db.rollback()
            if hasattr(current_user, '_sa_instance_state'):
                await db.refresh(current_user)
            clean = {key: value for key, value in detail.items() if key != 'preview'}
            try:
                request = wire.WorkRequest.model_validate(body.model_dump(mode='json', exclude={'expected_work_fingerprint'}))
                clean['preview'] = await service.work_preview(db, current_user, vehicle_id, request)
            except HTTPException:
                pass  # A changed authorization or incompatible scope has no retry preview.
            raise HTTPException(error.status_code, clean, headers={'Cache-Control': 'private, no-store'}) from error
        raise
    if result['replayed'] or not result['created']:
        response.status_code = 200
    return result


@work_router.get('/repair-orders/{order_id}/maintenance')
async def order_maintenance(order_id: UUID, db: Db, current_user: Actor, channel: wire.Channel):
    return await service.order_maintenance(db, current_user, channel, order_id)


@work_router.post('/vehicles/{vehicle_id}/maintenance-programs/{program_id}/evidence', status_code=201)
async def record_evidence(vehicle_id: UUID, program_id: UUID, body: wire.EvidenceCommit, response: Response, key: Key, db: Db, current_user: Actor):
    if body.program.program_id != program_id:
        service.fail('maintenance_invalid_input', 'The evidence program does not match this request.', 422)
    result = await service.evidence_command(db, current_user, vehicle_id, body, key)
    if result['replayed']:
        response.status_code = 200
    return result


@work_router.post('/vehicles/{vehicle_id}/maintenance-programs/{program_id}/detach-work')
async def detach_work(vehicle_id: UUID, program_id: UUID, body: wire.DetachWork, key: Key, db: Db, current_user: Actor):
    return await service.detach_command(db, current_user, vehicle_id, program_id, body, key)
