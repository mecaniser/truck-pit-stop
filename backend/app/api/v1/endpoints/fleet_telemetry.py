# ruff: noqa: B008
"""Staff-only capture, with domain replay authorization on every request."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.core.payment_step_up import require_trusted_cookie_origin
from app.schemas.fleet_telemetry import TelemetryCapture
from app.services import fleet_telemetry as service


class CaptureRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private(request: Request):
            try:
                require_trusted_cookie_origin(request)
                response = await handler(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            except RequestValidationError:
                service.fail(422, "invalid_request")
            except HTTPException as exc:
                if not isinstance(exc.detail, dict):
                    code = {
                        401: "authentication_required",
                        403: "forbidden",
                        404: "not_found",
                    }.get(exc.status_code, "invalid_request")
                    exc.detail = {"code": code, "message": code.replace("_", " ")}
                exc.headers = {**(exc.headers or {}), "Cache-Control": "no-store"}
                raise

        return private


router = APIRouter(route_class=CaptureRoute)


@router.post("/trucks/{vehicle_id}/telemetry-snapshots", status_code=201)
async def capture(
    vehicle_id: UUID,
    body: TelemetryCapture,
    response: Response,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_active_user),
):
    row, created = await service.capture(db, actor, vehicle_id, body)
    await db.commit()
    response.status_code = 201 if created else 200
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "vehicle_id",
            "fleet_customer_id",
            "source",
            "observed_at",
            "captured_at",
            "captured_by_user_id",
        )
    }
