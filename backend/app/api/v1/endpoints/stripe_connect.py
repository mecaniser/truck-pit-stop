from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import stripe

from app.core.dependencies import get_db, get_current_active_user
from app.core.config import settings
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter()


class OnboardingLinkResponse(BaseModel):
    url: str


class ConnectStatusResponse(BaseModel):
    is_connected: bool
    onboarding_complete: bool
    charges_enabled: bool
    payouts_enabled: bool
    account_id: Optional[str]


class DashboardLinkResponse(BaseModel):
    url: str


def _require_garage_admin(current_user: User) -> None:
    """Only garage admins can manage Stripe Connect"""
    if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only garage administrators can manage Stripe settings",
        )


@router.post("/onboard", response_model=OnboardingLinkResponse)
async def create_onboarding_link(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create or retrieve Stripe Connect account and generate onboarding link"""
    _require_garage_admin(current_user)
    
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    
    # Get tenant
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    # Create Stripe Express account if not exists
    if not tenant.stripe_account_id:
        try:
            account = stripe.Account.create(
                type="express",
                country="US",
                email=tenant.email or current_user.email,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                business_type="company",
                metadata={
                    "tenant_id": str(tenant.id),
                    "tenant_name": tenant.name,
                },
            )
            tenant.stripe_account_id = account.id
            await db.commit()
        except stripe.error.StripeError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create Stripe account: {str(e)}",
            )
    
    # Generate onboarding link
    try:
        account_link = stripe.AccountLink.create(
            account=tenant.stripe_account_id,
            refresh_url=f"{settings.FRONTEND_URL}/dashboard/settings/stripe?refresh=true",
            return_url=f"{settings.FRONTEND_URL}/dashboard/settings/stripe?success=true",
            type="account_onboarding",
        )
        return OnboardingLinkResponse(url=account_link.url)
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create onboarding link: {str(e)}",
        )


@router.get("/status", response_model=ConnectStatusResponse)
async def get_connect_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Check Stripe Connect onboarding status"""
    _require_garage_admin(current_user)
    
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    
    if not tenant.stripe_account_id:
        return ConnectStatusResponse(
            is_connected=False,
            onboarding_complete=False,
            charges_enabled=False,
            payouts_enabled=False,
            account_id=None,
        )
    
    # Fetch account status from Stripe
    try:
        account = stripe.Account.retrieve(tenant.stripe_account_id)
        
        charges_enabled = account.charges_enabled
        payouts_enabled = account.payouts_enabled
        onboarding_complete = charges_enabled and payouts_enabled
        
        # Update local status if changed
        if tenant.stripe_onboarding_complete != onboarding_complete:
            tenant.stripe_onboarding_complete = onboarding_complete
            await db.commit()
        
        return ConnectStatusResponse(
            is_connected=True,
            onboarding_complete=onboarding_complete,
            charges_enabled=charges_enabled,
            payouts_enabled=payouts_enabled,
            account_id=tenant.stripe_account_id,
        )
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve account status: {str(e)}",
        )


@router.post("/dashboard", response_model=DashboardLinkResponse)
async def create_dashboard_link(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate a link to the Stripe Express dashboard"""
    _require_garage_admin(current_user)
    
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant or not tenant.stripe_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe account not connected",
        )
    
    try:
        login_link = stripe.Account.create_login_link(tenant.stripe_account_id)
        return DashboardLinkResponse(url=login_link.url)
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create dashboard link: {str(e)}",
        )


@router.post("/refresh", response_model=OnboardingLinkResponse)
async def refresh_onboarding_link(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Refresh the onboarding link if user needs to continue setup"""
    _require_garage_admin(current_user)
    
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    
    if not tenant or not tenant.stripe_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Stripe account found. Please start onboarding first.",
        )
    
    try:
        account_link = stripe.AccountLink.create(
            account=tenant.stripe_account_id,
            refresh_url=f"{settings.FRONTEND_URL}/dashboard/settings/stripe?refresh=true",
            return_url=f"{settings.FRONTEND_URL}/dashboard/settings/stripe?success=true",
            type="account_onboarding",
        )
        return OnboardingLinkResponse(url=account_link.url)
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create onboarding link: {str(e)}",
        )
