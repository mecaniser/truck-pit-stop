from typing import Optional
from pydantic import BaseModel, EmailStr


class MechanicUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    address: Optional[str] = None
    core_hours_target_minutes_override: Optional[int] = None
    shift_start_local_override: Optional[str] = None
    shift_end_local_override: Optional[str] = None
