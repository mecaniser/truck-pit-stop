# ruff: noqa: B008
"""Owner/admin-only Motive integration management. No token material in responses."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_active_user,
    get_current_user,
    get_db,
    get_token_from_request,
)
from app.core.payment_step_up import require_trusted_cookie_origin
from app.core.security import decode_token
from app.db.models.motive_oauth import MotiveRemoteVehicle
from app.services import motive_oauth as service


class PrivateRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request: Request):
            try:
                if request.method in {"POST", "PUT", "DELETE"}:
                    require_trusted_cookie_origin(request)
                result = await handler(request)
                result.headers["Cache-Control"] = "no-store"
                return result
            except RequestValidationError:
                raise HTTPException(
                    422,
                    {"code": "invalid_request", "message": "Invalid Motive request"},
                    headers={"Cache-Control": "no-store"},
                ) from None
            except HTTPException as exc:
                message = str(exc.detail)
                code = (
                    message
                    if " " not in message
                    else {
                        400: "invalid_authorization",
                        401: "authentication_required",
                        403: "forbidden",
                        404: "not_found",
                        409: "connection_conflict",
                        429: "rate_limited",
                        503: "not_configured",
                    }.get(exc.status_code, "provider_error")
                )
                code = {
                    "Motive authorization was not completed": "oauth_denied",
                    "Authorization expired or invalid; connect again": "oauth_session_invalid",
                    "Connection changed; connect again": "oauth_session_invalid",
                    "Motive connection is busy; try again": "connection_busy",
                    "Disconnect before changing the Motive company": "company_mismatch",
                }.get(message, code)
                raise HTTPException(
                    exc.status_code,
                    {"code": code, "message": message},
                    headers={"Cache-Control": "no-store"},
                ) from None

        return private_handler


router = APIRouter(route_class=PrivateRoute)


class CompanyRequest(BaseModel):
    fleet_customer_id: UUID


class BindingRequest(CompanyRequest):
    vehicle_id: UUID


class CallbackRequest(BaseModel):
    state: str = Field(min_length=32, max_length=256)
    code: str | None = Field(default=None, min_length=1, max_length=4096)
    error: str | None = Field(default=None, max_length=120)


def session_id(token: str):
    payload = decode_token(token)
    if not payload or not payload.get("jti"):
        raise HTTPException(401, "Authenticated session required")
    return str(payload["jti"])


@router.get("/connection")
async def get_connection(
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await service.authorize(db, actor, fleet_customer_id)
    row = await service.connection(db, actor.tenant_id, fleet_customer_id)
    return service.response(row, fleet_customer_id, actor.tenant_id)


@router.post("/connect")
async def connect(
    body: CompanyRequest,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
    token=Depends(get_token_from_request),
):
    return await service.start(db, actor, body.fleet_customer_id, session_id(token))


@router.post("/callback")
async def callback(
    body: CallbackRequest,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
    token=Depends(get_token_from_request),
):
    async def revalidate():
        await get_current_user(token=token, db=db)

    return await service.callback(
        db,
        actor,
        session_id(token),
        body.state,
        body.code,
        body.error,
        revalidate=revalidate,
    )


@router.delete("/connection", status_code=204)
async def disconnect(
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await service.disconnect(db, actor, fleet_customer_id)
    return Response(status_code=204)


@router.put("/bindings/{provider_vehicle_id}")
async def bind(
    provider_vehicle_id: str,
    body: BindingRequest,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    return await service.bind(
        db, actor, body.fleet_customer_id, provider_vehicle_id, body.vehicle_id
    )


@router.delete("/bindings/{provider_vehicle_id}", status_code=204)
async def unbind(
    provider_vehicle_id: str,
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await service.bind(db, actor, fleet_customer_id, provider_vehicle_id, None)
    return Response(status_code=204)


@router.post("/sync")
async def sync(
    body: CompanyRequest,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await service.authorize(db, actor, body.fleet_customer_id)
    row = await service.connection(db, actor.tenant_id, body.fleet_customer_id, True)
    if not row:
        raise HTTPException(404, "Motive connection not found")
    return await service.sync(db, row)


@router.get("/vehicles")
async def vehicles(
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await service.authorize(db, actor, fleet_customer_id)
    row = await service.connection(db, actor.tenant_id, fleet_customer_id)
    if not row or row.status == "disconnected":
        return {"items": [], "synced_at": None}
    trucks = await service.active_trucks(db, row)
    active_ids = {v.id for v in trucks}
    remotes = (
        (
            await db.execute(
                select(MotiveRemoteVehicle)
                .where(
                    MotiveRemoteVehicle.connection_id == row.id,
                    MotiveRemoteVehicle.tenant_id == actor.tenant_id,
                )
                .order_by(MotiveRemoteVehicle.provider_vehicle_id)
            )
        )
        .scalars()
        .all()
    )
    vin_counts = {}
    for remote in remotes:
        if remote.vin:
            vin_counts[remote.vin.upper()] = vin_counts.get(remote.vin.upper(), 0) + 1
    items = []
    stamp = service.now()
    for remote in remotes:
        matches = [
            v
            for v in trucks
            if v.vin and remote.vin and v.vin.upper() == remote.vin.upper()
        ]
        candidates = (
            [{"vehicle_id": v.id, "unit_number": v.unit_number} for v in matches]
            if len(matches) == 1 and vin_counts.get((remote.vin or "").upper()) == 1
            else []
        )
        telemetry = None
        if (
            remote.vehicle_id in active_ids
            and remote.located_at
            and service.configured(actor.tenant_id)
        ):
            age = (stamp - service.utc(remote.located_at)).total_seconds()
            if age <= 30 * 86400:
                telemetry = {
                    "location": {
                        "lat": remote.lat,
                        "lng": remote.lng,
                        "located_at": remote.located_at,
                        "received_at": remote.received_at,
                    },
                    "speed_mph": remote.speed_mph,
                    "bearing_degrees": remote.bearing,
                    "state": "fresh"
                    if age <= 300
                    else "delayed"
                    if age <= 900
                    else "stale",
                    "source": "motive",
                }
        items.append(
            {
                "provider_vehicle_id": remote.provider_vehicle_id,
                "number": remote.number,
                "vin": remote.vin,
                "gateway_id": None,
                "vehicle_id": remote.vehicle_id,
                "match_candidates": candidates,
                "mapping_state": "unmapped"
                if not remote.vehicle_id
                else "mapped"
                if remote.vehicle_id in active_ids
                else "membership_ended",
                "telemetry": telemetry,
            }
        )
    return {"items": items, "synced_at": row.last_sync_at}
