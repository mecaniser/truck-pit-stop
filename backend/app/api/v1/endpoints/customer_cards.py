"""Customer saved-card API; processor choice is resolved from shop settings."""
from typing import Annotated, Literal
import re

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.models.user import User
from app.services import customer_card_service as cards
from app.services.customer_card_context import PENDING, resolve_card_context

class CardRoute(APIRoute):
    """Never reflect rejected payment input into responses or validation logs."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request):
            try:
                return await original(request)
            except RequestValidationError:
                raise HTTPException(
                    status_code=422,
                    detail='Invalid card request. Refresh the form and try again.',
                ) from None

        return handle


router = APIRouter(route_class=CardRoute)


class CardConfiguration(BaseModel):
    provider: Literal['stripe_connect', 'quickbooks_payments'] | None = None
    context_key: str = ''
    available: bool
    save_pending: bool = False
    message: str | None = None
    stripe_account_id: str | None = None
    token_url: str | None = None


class SavedCard(BaseModel):
    id: str
    brand: str
    last4: str = Field(pattern=r'^[0-9]{4}$')
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=2000, le=9999)
    is_default: bool


class ExpectedContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_context: str = Field(min_length=64, max_length=64, pattern=r'^[a-f0-9]{64}$')


class CardSaveRequest(ExpectedContext):
    idempotency_key: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')


class TokenCardSaveRequest(CardSaveRequest):
    token: SecretStr = Field(min_length=1, max_length=2048)

    @field_validator('token')
    @classmethod
    def opaque_token_only(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if re.sub(r'[._~\-]', '', token).isdigit() or not re.fullmatch(r'[A-Za-z0-9._~\-]+', token):
            raise ValueError('A secure card token is required')
        return value


class PreparedCard(BaseModel):
    client_secret: str
    stripe_account_id: str


class SavedCardResult(BaseModel):
    status: Literal['saved']


@router.get('/config', response_model=CardConfiguration)
async def card_configuration(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        context = await resolve_card_context(db, current_user)
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        # Readiness is a capability state, not a successful empty-card list.
        return CardConfiguration(available=False, message=exc.detail)
    profile = await cards.get_profile(db, context)
    pending = await cards.pending_save(db, profile)
    return CardConfiguration(
        provider=context.provider, context_key=context.key, available=True,
        save_pending=pending, message=PENDING if pending else None,
        stripe_account_id=context.account if context.provider == 'stripe_connect' else None,
        token_url=(
            {'sandbox': 'https://sandbox.api.intuit.com', 'production': 'https://api.intuit.com'}[context.environment]
            + '/quickbooks/v4/payments/tokens'
        ) if context.provider == 'quickbooks_payments' else None,
    )


@router.get('', response_model=list[SavedCard])
async def list_saved_cards(
    expected_context: str | None = Query(default=None, min_length=64, max_length=64, pattern=r'^[a-f0-9]{64}$'),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    context = await resolve_card_context(db, current_user, expected=expected_context)
    return await cards.list_customer_cards(db, context)


@router.post('/prepare', response_model=PreparedCard)
async def prepare_card(
    body: CardSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await cards.prepare_stripe_card(db, current_user, body.expected_context, body.idempotency_key)


@router.post('/save', response_model=SavedCardResult)
async def save_card(
    body: TokenCardSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await cards.save_quickbooks_card(
        db, current_user, body.expected_context, body.idempotency_key, body.token.get_secret_value(),
    )


@router.post('/{method_id}/default', status_code=204)
async def set_default_card(
    method_id: Annotated[str, Path(min_length=1, max_length=255, pattern=r'^[A-Za-z0-9_-]+$')],
    body: ExpectedContext,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    await cards.mutate_card(db, current_user, body.expected_context, method_id, remove=False)
    return Response(status_code=204)


@router.delete('/{method_id}', status_code=204)
async def remove_card(
    method_id: Annotated[str, Path(min_length=1, max_length=255, pattern=r'^[A-Za-z0-9_-]+$')],
    expected_context: str = Query(min_length=64, max_length=64, pattern=r'^[a-f0-9]{64}$'),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    await cards.mutate_card(db, current_user, expected_context, method_id, remove=True)
    return Response(status_code=204)
