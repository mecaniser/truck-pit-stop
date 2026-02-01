from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import stripe

from app.core.config import settings
from app.core.dependencies import get_db
from app.db.models.tenant import Tenant

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter()


@router.post("/connect")
async def stripe_connect_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe Connect webhooks for account updates"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )
    
    # Use Connect-specific webhook secret if available, otherwise fall back to main secret
    webhook_secret = settings.STRIPE_CONNECT_WEBHOOK_SECRET or settings.STRIPE_WEBHOOK_SECRET
    
    if not webhook_secret:
        # In development without webhook secret, just parse the event
        try:
            event = stripe.Event.construct_from(
                stripe.util.json.loads(payload), stripe.api_key
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload",
            )
    else:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature",
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload",
            )
    
    # Handle the event
    if event["type"] == "account.updated":
        account = event["data"]["object"]
        account_id = account["id"]
        
        # Find tenant by stripe_account_id
        result = await db.execute(
            select(Tenant).where(Tenant.stripe_account_id == account_id)
        )
        tenant = result.scalar_one_or_none()
        
        if tenant:
            # Update onboarding status based on account capabilities
            charges_enabled = account.get("charges_enabled", False)
            payouts_enabled = account.get("payouts_enabled", False)
            onboarding_complete = charges_enabled and payouts_enabled
            
            if tenant.stripe_onboarding_complete != onboarding_complete:
                tenant.stripe_onboarding_complete = onboarding_complete
                await db.commit()
    
    elif event["type"] == "account.application.deauthorized":
        # Tenant disconnected their Stripe account
        account = event["data"]["object"]
        account_id = account.get("id")
        
        if account_id:
            result = await db.execute(
                select(Tenant).where(Tenant.stripe_account_id == account_id)
            )
            tenant = result.scalar_one_or_none()
            
            if tenant:
                tenant.stripe_account_id = None
                tenant.stripe_onboarding_complete = False
                await db.commit()
    
    return {"status": "success"}
