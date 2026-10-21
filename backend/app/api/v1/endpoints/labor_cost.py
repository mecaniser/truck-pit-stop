"""A1 protected management costing; dedicated read-only GET snapshots."""
from datetime import date, datetime, timezone
import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Header
from pydantic import ValidationError
from sqlalchemy import select, func, or_, text
from sqlalchemy.exc import DBAPIError
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from app.core.dependencies import CurrentUser, get_current_active_user
from app.db.session import AsyncSessionLocal
from app.db.models.user import User, UserRole
from app.schemas.labor_cost import RateRequest, ReviewRequest
from app.services.labor_cost import policy, report
from app.services.labor_cost.calculation import stamp

class ProtectedCostRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def protected(request):
            try:
                response = await handler(request)
                response.headers["Cache-Control"] = "private, no-store"
                return response
            except HTTPException as error:
                error.headers = {**(error.headers or {}), "Cache-Control": "private, no-store"}
                raise
            except RequestValidationError:
                raise HTTPException(422, "Invalid protected cost request", headers={"Cache-Control": "private, no-store"})
        return protected


router = APIRouter(route_class=ProtectedCostRoute)


def private(response):
    response.headers["Cache-Control"] = "private, no-store"


def pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


async def body_value(request, schema):
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, "Cost request exceeds safe size")
    try:
        payload = json.loads(raw, object_pairs_hook=pairs_unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        return schema.model_validate(payload)
    except (ValueError, TypeError, RecursionError, UnicodeError, ValidationError):
        raise HTTPException(422, "Invalid cost request")


def idempotency(value):
    try:
        result = UUID(value)
        if str(result) != value:
            raise ValueError()
        return result
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "UUID Idempotency-Key required")


async def read_call(actor, operation):
    policy.authorize(actor)
    async with AsyncSessionLocal() as db:
        try:
            # Authentication has its own session. This session has not queried
            # anything before establishing PostgreSQL snapshot semantics.
            if db.bind.dialect.name != "postgresql":
                raise HTTPException(503, "Safe cost snapshot unavailable")
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            return await operation(db)
        finally:
            await db.rollback()


@router.get("/technician-costs/time-boundaries")
async def time_boundary(request: Request, response: Response, local: str = Query(..., min_length=16, max_length=16,
                        pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d$"),
                        fold: str | None = Query(None, pattern=r"^[01]$"),
                        user: CurrentUser = Depends(get_current_active_user)):
    private(response)
    if (set(request.query_params) - {"local", "fold"}
            or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params)):
        raise HTTPException(422, "Invalid time boundary request")
    async def operation(db):
        tenant, zone, activation = await policy.context(db, user)
        from app.services.repair_order_schedule import resolve_wall, local_fields
        result = resolve_wall(local, int(fold) if fold is not None else None, zone, "local")
        return {"contract_version": 1, "shop_timezone": tenant.timezone, "local": local,
                "fold": local_fields(result, zone)[1], "effective_at": stamp(result), "activation_at": stamp(activation)}
    return await read_call(user, operation)


@router.get("/technician-costs")
async def list_costs(response: Response, limit: int = Query(50, ge=1, le=100),
                     cursor: str | None = Query(None, max_length=1024), q: str = Query("", max_length=100),
                     user: CurrentUser = Depends(get_current_active_user)):
    private(response)
    async def operation(db):
        tenant, _, _ = await policy.context(db, user)
        binding = {"tenant": str(tenant.id), "q": q.casefold(), "type": "technicians"}
        position = policy.cursor_decode(cursor, binding)
        name = func.coalesce(func.nullif(func.trim(func.coalesce(User.first_name, "") + " " + func.coalesce(User.last_name, "")), ""), "Technician")
        query = select(User).where(User.tenant_id == tenant.id, User.role == UserRole.MECHANIC, User.deleted_at.is_(None))
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(name.ilike(f"%{escaped}%", escape="\\"))
        if position is not None:
            try:
                if len(position) != 2 or any(not isinstance(item, str) for item in position):
                    raise ValueError()
                last_id = UUID(position[1])
            except (ValueError, TypeError):
                raise HTTPException(422, "Invalid cost report cursor")
            query = query.where(or_(name > position[0], (name == position[0]) & (User.id > last_id)))
        rows = list((await db.execute(query.order_by(name, User.id).limit(limit + 1))).scalars())
        items = []
        for mechanic in rows[:limit]:
            history = await policy.rate_history(db, tenant.id, mechanic.id)
            items.append(policy.rate_response(mechanic, history[0] if history else None))
        return {"contract_version": 1, "generated_at": stamp(datetime.now(timezone.utc)), "items": items,
                "next_cursor": policy.cursor_encode(binding, [policy.display_name(rows[limit-1]), str(rows[limit-1].id)]) if len(rows) > limit else None}
    return await read_call(user, operation)


@router.get("/technician-costs/{mechanic_id}")
async def cost_detail(mechanic_id: UUID, response: Response, limit: int = Query(50, ge=1, le=100),
                      cursor: str | None = Query(None, max_length=1024), user: CurrentUser = Depends(get_current_active_user)):
    private(response)
    async def operation(db):
        tenant, _, _ = await policy.context(db, user)
        mechanic = await policy.technician(db, tenant.id, mechanic_id)
        history = await policy.rate_history(db, tenant.id, mechanic_id)
        binding = {"tenant": str(tenant.id), "mechanic": str(mechanic_id), "type": "rate-history"}
        position = policy.cursor_decode(cursor, binding)
        if position is not None and (len(position) != 1 or type(position[0]) is not int):
            raise HTTPException(422, "Invalid cost report cursor")
        remaining = [revision for revision in history if position is None or revision.version < position[0]]
        page = remaining[:limit]
        return {**policy.rate_response(mechanic, history[0] if history else None),
                "history": [{"version": item.version, "revision_id": str(item.id), "supersedes_id": str(item.supersedes_id) if item.supersedes_id else None,
                             "approved_at": stamp(item.created_at)} for item in page],
                "next_cursor": policy.cursor_encode(binding, [page[-1].version]) if len(remaining) > limit else None}
    return await read_call(user, operation)


async def write_call(user, request, response, key, schema, operation):
    policy.authorize(user)
    private(response)
    parsed_key = idempotency(key)
    body = await body_value(request, schema)
    async with AsyncSessionLocal() as db:
        try:
            async with db.begin():
                result, created = await operation(db, body, parsed_key)
            response.status_code = 201 if created else 200
            return result
        except DBAPIError:
            await db.rollback()
            raise HTTPException(409, "Cost evidence changed; refresh before retrying")


@router.post("/technician-costs/{mechanic_id}")
async def write_cost(mechanic_id: UUID, request: Request, response: Response,
                     key: str | None = Header(None, alias="Idempotency-Key"), user: CurrentUser = Depends(get_current_active_user)):
    return await write_call(user, request, response, key, RateRequest,
                            lambda db, body, parsed: policy.append_rate(db, user, mechanic_id, body, parsed))


@router.get("/job-contribution")
async def contribution_report(response: Response, from_date: date | None = Query(None, alias="from"),
                              to_date: date | None = Query(None, alias="to"), limit: int = Query(50, ge=1, le=100),
                              cursor: str | None = Query(None, max_length=1024), q: str = Query("", max_length=100),
                              scope: str = Query("all", pattern=r"^(all|real|review|test|history)$"),
                              user: CurrentUser = Depends(get_current_active_user)):
    private(response)
    return await read_call(user, lambda db: report.report(db, user, from_date=from_date, to_date=to_date,
                                                         limit=limit, cursor=cursor, q=q, scope=scope))


@router.get("/job-contribution/{order_id}")
async def contribution_detail(order_id: UUID, response: Response, user: CurrentUser = Depends(get_current_active_user)):
    private(response)
    async def operation(db):
        bundle, activation = await report.detail(db, user, order_id)
        return report.detail_response(bundle, activation)
    return await read_call(user, operation)


@router.post("/job-contribution/{order_id}/review")
async def write_review(order_id: UUID, request: Request, response: Response,
                       key: str | None = Header(None, alias="Idempotency-Key"), user: CurrentUser = Depends(get_current_active_user)):
    return await write_call(user, request, response, key, ReviewRequest,
                            lambda db, body, parsed: report.append_review(db, user, order_id, body, parsed))
