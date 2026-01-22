from pydantic import BaseModel, EmailStr
from typing import Optional


class MechanicCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    address: Optional[str] = None
