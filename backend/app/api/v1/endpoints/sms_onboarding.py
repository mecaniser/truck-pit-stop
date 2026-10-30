"""Review-only SMS setup. No registration submission or activation endpoint."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_active_user, get_db
from app.schemas.sms_onboarding import SMSConsentCreate, SMSConsentResponse
from app.services import sms_onboarding_service as service
from app.services.communications_service import authorize

router=APIRouter()

@router.get('/onboarding')
@router.put('/onboarding')
@router.post('/onboarding/review')
@router.get('/onboarding/review-package')
async def retired_registration(user=Depends(get_current_active_user)):
    """Old clients must not infer a platform target from their tenant session."""
    raise HTTPException(
        status_code=403,
        detail={
            "code": "platform_registration_required",
            "message": "Registration is managed in the platform workspace.",
        },
    )


@router.get('/consents')
async def consents(customer_id:UUID,db=Depends(get_db),user=Depends(get_current_active_user)):
    tenant=await authorize(db,user)
    return await service.customer_consents(db,tenant,customer_id)

@router.post('/consents',response_model=SMSConsentResponse)
async def consent(body:SMSConsentCreate,db=Depends(get_db),user=Depends(get_current_active_user)):
    tenant=await authorize(db,user)
    return await service.record_customer_consent(db,tenant,user,body)
