"""Review-only SMS setup. No registration submission or activation endpoint."""
from uuid import UUID
from fastapi import APIRouter, Depends
from app.core.dependencies import get_current_active_user, get_db
from app.schemas.sms_onboarding import SMSOnboardingUpdate, SMSReviewRequest, SMSOnboardingResponse, SMSConsentCreate, SMSConsentResponse
from app.services import sms_onboarding_service as service
from app.services.communications_service import authorize

router=APIRouter()

@router.get('/onboarding',response_model=SMSOnboardingResponse)
async def onboarding(db=Depends(get_db),user=Depends(get_current_active_user)):
    tenant=await service.owner_tenant(db,user)
    return await service.onboarding(db,tenant)

@router.put('/onboarding',response_model=SMSOnboardingResponse)
async def save(body:SMSOnboardingUpdate,db=Depends(get_db),user=Depends(get_current_active_user)):
    tenant=await service.owner_tenant(db,user)
    return await service.save_draft(db,tenant,user,body)

@router.post('/onboarding/review',response_model=SMSOnboardingResponse)
async def review(body:SMSReviewRequest,db=Depends(get_db),user=Depends(get_current_active_user)):
    tenant=await service.owner_tenant(db,user)
    return await service.request_review(db,tenant,user,body.expected_version)

@router.get('/onboarding/review-package')
async def review_package(db=Depends(get_db),user=Depends(get_current_active_user)):
    tenant=await service.owner_tenant(db,user)
    result=await service.onboarding(db,tenant)
    return dict(**result,review_only=True)

@router.get('/consents')
async def consents(customer_id:UUID,db=Depends(get_db),user=Depends(get_current_active_user)):
    tenant=await authorize(db,user)
    return await service.customer_consents(db,tenant,customer_id)

@router.post('/consents',response_model=SMSConsentResponse)
async def consent(body:SMSConsentCreate,db=Depends(get_db),user=Depends(get_current_active_user)):
    tenant=await authorize(db,user)
    return await service.record_customer_consent(db,tenant,user,body)
