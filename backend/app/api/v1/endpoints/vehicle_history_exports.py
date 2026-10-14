"""Private CSV download endpoint; errors are JSON, never file attachments."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException

from app.core.dependencies import get_current_active_user
from app.core.logging import get_logger
from app.db.models.user import User
from app.db.session import get_db
from app.services import vehicle_history_export as service

PRIVATE_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
logger = get_logger(__name__)


class PrivateExportRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request):
            try:
                response = await handler(request)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            except RequestValidationError as exc:
                response = JSONResponse({"detail": jsonable_encoder(exc.errors())}, status_code=422)
            except Exception:
                logger.exception("Vehicle history export failed")
                response = JSONResponse({"detail": {"code": "history_export_failed", "message": "Could not export vehicle history. Try again."}}, status_code=500)
            response.headers.update(PRIVATE_HEADERS)
            return response

        return private_handler


router = APIRouter(route_class=PrivateExportRoute)


def parse_date(value):
    if value is None:
        return None
    try:
        result = date.fromisoformat(value)
        if result.year < 1900:
            raise ValueError()
        return result
    except ValueError:
        service.fail(422, "invalid_export_filter", "Use a valid history date on or after 1900-01-01.")


@router.get("/{vehicle_id}/service-history.csv")
async def export_vehicle_service_history(
    vehicle_id: UUID, request: Request,
    date_from: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    keys = list(request.query_params.keys())
    if any(key not in {"date_from", "date_to"} or len(request.query_params.getlist(key)) > 1 for key in keys):
        service.fail(422, "invalid_export_filter", "Only one History from and one History to date are supported.")
    content, count = await service.export_csv(db, vehicle_id, current_user, date_from=parse_date(date_from), date_to=parse_date(date_to))
    return Response(content, media_type="text/csv", headers={
        **PRIVATE_HEADERS,
        "Content-Disposition": f'attachment; filename="vehicle-service-history-{vehicle_id}.csv"',
        "Access-Control-Expose-Headers": "Content-Disposition, X-Export-Row-Count, X-Export-Vehicle-Id",
        "X-Export-Row-Count": str(count),
        "X-Export-Vehicle-Id": str(vehicle_id),
    })
