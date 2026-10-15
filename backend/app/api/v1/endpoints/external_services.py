"""Private staff-only vehicle history for work performed outside this shop."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.external_service import ExternalServiceCreate, ExternalServiceHistoryPage, ExternalServiceMutation, ExternalServicePage, ExternalServiceRestore, ExternalServiceUpdate, ExternalServiceVoid
from app.services import external_service
from app.api.v1.endpoints.external_service_receipts import router as receipt_router

def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/{vehicle_id}/external-services", dependencies=[Depends(private_response)])
router.include_router(receipt_router)


@router.get("", response_model=ExternalServicePage)
async def list_external_services(vehicle_id: UUID, skip: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), include_voided: bool = False, search: str | None = Query(None, max_length=200),
                                 db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return await external_service.page(db, vehicle_id, current_user, skip=skip, limit=limit, include_voided=include_voided, search=search)


@router.post("", response_model=ExternalServiceMutation, status_code=201)
async def create_external_service(vehicle_id: UUID, body: ExternalServiceCreate, response: Response,
                                  db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    result = await external_service.mutate(db, vehicle_id, current_user, body)
    await db.commit()
    if result.replayed:
        response.status_code = 200
    return result


@router.put("/{record_id}", response_model=ExternalServiceMutation)
async def update_external_service(vehicle_id: UUID, record_id: UUID, body: ExternalServiceUpdate,
                                  db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    result = await external_service.mutate(db, vehicle_id, current_user, body, action="update", record_id=record_id)
    await db.commit()
    return result


@router.post("/{record_id}/void", response_model=ExternalServiceMutation)
async def void_external_service(vehicle_id: UUID, record_id: UUID, body: ExternalServiceVoid,
                                db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    result = await external_service.mutate(db, vehicle_id, current_user, body, action="void", record_id=record_id)
    await db.commit()
    return result


@router.post("/{record_id}/restore", response_model=ExternalServiceMutation)
async def restore_external_service(vehicle_id: UUID, record_id: UUID, body: ExternalServiceRestore,
                                   db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    result = await external_service.mutate(db, vehicle_id, current_user, body, action="restore", record_id=record_id)
    await db.commit()
    return result


@router.get("/{record_id}/history", response_model=ExternalServiceHistoryPage)
async def external_service_history(vehicle_id: UUID, record_id: UUID, skip: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                                   db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return await external_service.history(db, vehicle_id, record_id, current_user, skip=skip, limit=limit)
