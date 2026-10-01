# ruff: noqa: B008
"""Explicit fleet administrator Motive integration management. No token material in responses."""

import secrets
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import (
    get_current_active_user,
    get_current_user,
    get_db,
    get_token_from_request,
)
from app.core.payment_step_up import require_trusted_cookie_origin
from app.core.security import decode_token
from app.db.models.motive_oauth import (
    MotiveFault,
    MotiveRemoteVehicle,
    MotiveWebhookReceipt,
)
from app.services import motive_access as access
from app.services import motive_ingestion as ingestion
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


@router.get("/companies")
async def companies(
    db: AsyncSession = Depends(get_db), actor=Depends(get_current_active_user)
):
    return await access.companies(db, actor)


@router.get("/trucks")
async def trucks(
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await service.authorize(db, actor, fleet_customer_id)
    # Membership lookup works before any provider connection has been created.
    from types import SimpleNamespace

    rows = await service.active_trucks(
        db,
        SimpleNamespace(tenant_id=actor.tenant_id, fleet_customer_id=fleet_customer_id),
    )
    return {
        "items": [
            {"id": v.id, "unit_number": v.unit_number, "vin": v.vin} for v in rows
        ]
    }


@router.get("/grant-candidates")
async def grant_candidates(
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    return await access.candidates(db, actor, fleet_customer_id)


@router.get("/grants")
async def grants(
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    return await access.grants(db, actor, fleet_customer_id)


@router.put("/grants/{user_id}")
async def grant(
    user_id: UUID,
    body: CompanyRequest,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    return await access.set_grant(db, actor, body.fleet_customer_id, user_id)


@router.delete("/grants/{user_id}", status_code=204)
async def revoke_grant(
    user_id: UUID,
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await access.set_grant(db, actor, fleet_customer_id, user_id, revoke=True)
    return Response(status_code=204)


def webhook_base_url():
    value = settings.PUBLIC_API_BASE_URL.rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise HTTPException(503, "webhook_not_configured")
    return value


async def webhook_view(db, row):
    status = ingestion.webhook_status(row)
    # Only public deployment configuration is used, never request Host headers.
    status["url"] = None
    if row and row.webhook_id and row.encrypted_webhook_secret:
        try:
            status["url"] = (
                f"{webhook_base_url()}/api/v1/webhooks/motive/{row.webhook_id}/{row.webhook_generation}"
            )
        except HTTPException:
            status["status"] = "not_configured"
    status.setdefault("pending_count", 0)
    status.setdefault("failed_count", 0)
    if row:
        counts = (
            await db.execute(
                select(MotiveWebhookReceipt.status, func.count())
                .where(
                    MotiveWebhookReceipt.connection_id == row.id,
                    MotiveWebhookReceipt.tenant_id == row.tenant_id,
                    MotiveWebhookReceipt.connection_generation == row.generation,
                    MotiveWebhookReceipt.webhook_generation == row.webhook_generation,
                )
                .group_by(MotiveWebhookReceipt.status)
            )
        ).all()
        status["pending_count"] = sum(
            n for state, n in counts if state in ("pending", "retry", "processing")
        )
        status["failed_count"] = sum(
            n for state, n in counts if state in ("failed", "dead")
        )
    return status


@router.get("/webhook")
async def webhook(
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await service.authorize(db, actor, fleet_customer_id)
    row = await service.connection(db, actor.tenant_id, fleet_customer_id)
    return await webhook_view(db, row)


@router.post("/webhook/rotate")
async def rotate_webhook(
    body: CompanyRequest,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await service.authorize(db, actor, body.fleet_customer_id)
    webhook_base_url()
    secret = secrets.token_urlsafe(32)
    await ingestion.configure_webhook(db, actor, body.fleet_customer_id, secret)
    row = await service.connection(db, actor.tenant_id, body.fleet_customer_id)
    result = await webhook_view(db, row)
    return {**result, "shared_secret": secret}


@router.delete("/webhook", status_code=204)
async def disable_webhook(
    fleet_customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    await ingestion.disable_webhook(db, actor, fleet_customer_id)
    return Response(status_code=204)


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
    result = service.response(row, fleet_customer_id, actor.tenant_id)
    hook = await webhook_view(db, row)
    from app.db.models.user import UserRole

    result.update(
        can_manage_grants=actor.role in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN),
        webhook_status=hook["status"],
        last_webhook_at=hook.get("last_received_at"),
        last_reconciled_at=row.last_reconciled_at if row else None,
    )
    return result


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
    result = await service.sync(db, row, actor=actor)
    await service.authorize(db, actor, body.fleet_customer_id)
    return result


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
        eligible = (
            remote.vehicle_id in active_ids
            and remote.provider_status == "active"
            and service.configured(actor.tenant_id)
        )
        if eligible and remote.located_at and service.configured(actor.tenant_id):
            age = (stamp - service.utc(remote.located_at)).total_seconds()
            if -300 <= age <= 30 * 86400:
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
        metrics = None
        faults = []
        faults_synced_at = None
        if eligible:
            if (
                remote.metrics_observed_at
                and -300
                <= (stamp - service.utc(remote.metrics_observed_at)).total_seconds()
                <= 30 * 86400
            ):
                metrics = {
                    "odometer_miles": remote.true_odometer_miles,
                    "virtual_odometer_miles": remote.virtual_odometer_miles,
                    "engine_hours": remote.true_engine_hours,
                    "virtual_engine_hours": remote.virtual_engine_hours,
                    "observed_at": remote.metrics_observed_at,
                    "received_at": remote.metrics_received_at,
                    "source": "motive",
                }
            if (
                remote.faults_synced_at
                and -300
                <= (stamp - service.utc(remote.faults_synced_at)).total_seconds()
                <= 30 * 86400
            ):
                faults_synced_at = remote.faults_synced_at
            from datetime import timedelta

            records = (
                (
                    await db.execute(
                        select(MotiveFault)
                        .where(
                            MotiveFault.tenant_id == actor.tenant_id,
                            MotiveFault.connection_id == row.id,
                            MotiveFault.remote_vehicle_id == remote.id,
                            MotiveFault.mapping_epoch == remote.mapped_at,
                            MotiveFault.deleted_at.is_(None),
                            or_(
                                and_(
                                    MotiveFault.status == "open",
                                    MotiveFault.received_at
                                    >= stamp - timedelta(days=30),
                                ),
                                and_(
                                    MotiveFault.status == "closed",
                                    MotiveFault.last_observed_at
                                    >= stamp - timedelta(days=30),
                                ),
                            ),
                            MotiveFault.last_observed_at <= stamp,
                        )
                        .order_by(MotiveFault.last_observed_at.desc(), MotiveFault.id)
                    )
                )
                .scalars()
                .all()
            )
            faults = [
                {
                    "id": f.id,
                    "code": f.code,
                    "code_label": f.code_label,
                    "description": f.description,
                    "status": f.status,
                    "first_observed_at": f.first_observed_at,
                    "last_observed_at": f.last_observed_at,
                    "fmi": f.fmi,
                    "source": "motive",
                }
                for f in records
            ]
        items.append(
            {
                "provider_vehicle_id": remote.provider_vehicle_id,
                "number": remote.number,
                "vin": remote.vin,
                "gateway_id": remote.gateway_id,
                "gateway_identifier": remote.gateway_identifier,
                "gateway_model": remote.gateway_model,
                "provider_status": remote.provider_status,
                "metrics": metrics,
                "faults": faults,
                "faults_synced_at": faults_synced_at,
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
