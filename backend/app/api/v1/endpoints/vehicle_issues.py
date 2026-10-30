"""Staff-only truck issues. All mutations are issue metadata transactions."""

from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.db.models.user import User
from app.schemas.vehicle_issue import (
    Issue,
    IssuePage,
    IssueMutation,
    IssueCreate,
    IssueEdit,
    IssueStateChange,
    IssueLinkCreate,
    IssueReason,
)
from app.services import vehicle_issues as service


class IssueRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(
                    422,
                    detail={
                        "code": "validation_error",
                        "message": "Check the issue fields and try again.",
                    },
                )

        return validated


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(route_class=IssueRoute, dependencies=[Depends(private_response)])


@router.get("/{vehicle_id}/issue-owners")
async def owners(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await service.list_owners(db, vehicle_id, current_user)


@router.get("/{vehicle_id}/issues", response_model=IssuePage)
async def issues(
    vehicle_id: UUID,
    customer_id: UUID | None = None,
    context_order_id: UUID | None = None,
    state: Literal["open", "resolved", "dismissed", "all"] = "open",
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await service.list_issues(
        db,
        vehicle_id,
        current_user,
        customer_id=customer_id,
        context_order_id=context_order_id,
        state=state,
        skip=skip,
        limit=limit,
    )


@router.get("/{vehicle_id}/issues/{issue_id}", response_model=Issue)
async def detail(
    vehicle_id: UUID,
    issue_id: UUID,
    customer_id: UUID | None = None,
    context_order_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await service.get_issue(
        db,
        vehicle_id,
        issue_id,
        current_user,
        customer_id=customer_id,
        context_order_id=context_order_id,
    )


@router.post("/{vehicle_id}/issues", response_model=IssueMutation, status_code=201)
async def create(
    vehicle_id: UUID,
    body: IssueCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result, created = await service.mutate(
        db, vehicle_id, current_user, body, operation="create"
    )
    await db.commit()
    if not created:
        response.status_code = 200
    return result


@router.patch("/{vehicle_id}/issues/{issue_id}", response_model=IssueMutation)
async def edit(
    vehicle_id: UUID,
    issue_id: UUID,
    body: IssueEdit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result, _ = await service.mutate(
        db, vehicle_id, current_user, body, operation="edit", issue_id=issue_id
    )
    await db.commit()
    return result


@router.post("/{vehicle_id}/issues/{issue_id}/state", response_model=IssueMutation)
async def change_state(
    vehicle_id: UUID,
    issue_id: UUID,
    body: IssueStateChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result, _ = await service.mutate(
        db, vehicle_id, current_user, body, operation="state", issue_id=issue_id
    )
    await db.commit()
    return result


@router.post(
    "/{vehicle_id}/issues/{issue_id}/links",
    response_model=IssueMutation,
    status_code=201,
)
async def link(
    vehicle_id: UUID,
    issue_id: UUID,
    body: IssueLinkCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result, created = await service.mutate(
        db, vehicle_id, current_user, body, operation="link", issue_id=issue_id
    )
    await db.commit()
    if not created:
        response.status_code = 200
    return result


@router.post(
    "/{vehicle_id}/issues/{issue_id}/links/{link_id}/end", response_model=IssueMutation
)
async def end_link(
    vehicle_id: UUID,
    issue_id: UUID,
    link_id: UUID,
    body: IssueReason,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result, _ = await service.mutate(
        db,
        vehicle_id,
        current_user,
        body,
        operation="end_link",
        issue_id=issue_id,
        link_id=link_id,
    )
    await db.commit()
    return result
