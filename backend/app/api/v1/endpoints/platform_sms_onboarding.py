"""Platform-only preparation of a selected shop's registration; no submission."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.v1.endpoints.admin import require_super_admin
from app.core.dependencies import get_db
from app.db.models.tenant import Tenant
from app.schemas.sms_onboarding import (
    SMSOnboardingResponse,
    SMSOnboardingUpdate,
    SMSReviewRequest,
)
from app.services import sms_onboarding_service as service

router = APIRouter()
super_admin = require_super_admin()


async def registration_target(
    tenant_id: UUID,
    user=Depends(super_admin),
    db=Depends(get_db),
):
    # Platform maintenance may prepare an inactive shop, but never a deleted one.
    # The explicit target is independent of the administrator's session tenant.
    tenant = await db.scalar(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    if tenant is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return tenant


@router.get("/onboarding", response_model=SMSOnboardingResponse)
async def onboarding(tenant=Depends(registration_target), db=Depends(get_db)):
    return await service.onboarding(db, tenant)


@router.put("/onboarding", response_model=SMSOnboardingResponse)
async def save(
    body: SMSOnboardingUpdate,
    tenant=Depends(registration_target),
    user=Depends(super_admin),
    db=Depends(get_db),
):
    return await service.save_draft(db, tenant, user, body)


@router.post("/onboarding/review", response_model=SMSOnboardingResponse)
async def review(
    body: SMSReviewRequest,
    tenant=Depends(registration_target),
    user=Depends(super_admin),
    db=Depends(get_db),
):
    return await service.request_review(db, tenant, user, body.expected_version)


@router.get("/onboarding/review-package")
async def review_package(tenant=Depends(registration_target), db=Depends(get_db)):
    result = await service.onboarding(db, tenant)
    return dict(**result, review_only=True)
