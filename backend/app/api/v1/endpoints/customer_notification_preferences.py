from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.models.user import User
from app.services.customer_notification_preferences import get_preferences, save_preferences

router = APIRouter()


class PreferencesResponse(BaseModel):
    context_key: str
    revision: int
    invoice_email: bool
    invoice_sms: bool
    repair_email: bool
    repair_sms: bool
    has_email: bool
    has_phone: bool
    sms_opted_out: bool


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_context: str = Field(pattern=r"^[a-f0-9]{64}$")
    base_revision: StrictInt = Field(ge=0)
    invoice_email: StrictBool
    invoice_sms: StrictBool
    repair_email: StrictBool
    repair_sms: StrictBool


@router.get("", response_model=PreferencesResponse)
async def read_preferences(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return await get_preferences(db, current_user)


@router.put("", response_model=PreferencesResponse)
async def update_preferences(body: PreferencesUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return await save_preferences(db, current_user, body)
