from pydantic import BaseModel, EmailStr
from typing import Optional


class MechanicCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    core_hours_target_minutes_override: Optional[int] = None
    shift_start_local_override: Optional[str] = None
    shift_end_local_override: Optional[str] = None
