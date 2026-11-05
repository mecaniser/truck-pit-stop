"""Secret-bearing request DTOs never leave their sanitized route boundary."""
from decimal import Decimal,DecimalException
from typing import Literal,Optional
from uuid import UUID
from pydantic import BaseModel,ConfigDict,SecretStr,StrictBool,Field,field_validator,model_validator
from app.core.efs_crypto import normalize

def exact_money(value):
    try:
        if not value.is_finite() or value < Decimal('.01') or value > Decimal('9999999999.99') or value != value.quantize(Decimal('.01')):
            raise ValueError()
    except (DecimalException,ValueError):
        raise ValueError('Enter a valid positive amount with at most two decimals.') from None
    return value

class EfsSummary(BaseModel):
    provider:Literal['EFS']='EFS'
    code_last4:str
    status:Literal['awaiting_verification','received','rejected','cancelled','review_required']
    can_cancel:bool=False
    can_reveal:bool=False
    can_verify:bool=False
    can_reject:bool=False
    can_resolve_received_difference:bool=False
    difference_review:Optional[dict]=None

class EfsSubmit(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    code:SecretStr
    amount:Decimal
    expected_settlement_version:int=Field(ge=1,strict=True)
    submitted_for_verification:StrictBool
    @field_validator('code')
    @classmethod
    def valid_code(cls,v):return SecretStr(normalize(v.get_secret_value()))
    @field_validator('amount')
    @classmethod
    def exact_amount(cls,v):
        return exact_money(v)

class GuestEfsSubmit(EfsSubmit):
    token:SecretStr

class EfsReveal(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    expected_attempt_version:int=Field(ge=1,strict=True)
    reason:str=Field(min_length=3,max_length=1000)

class EfsVerify(EfsReveal):
    action:Literal['confirm_received','reject','resolve_received_difference']
    expected_settlement_version:int=Field(ge=1,strict=True)
    observation_id:Optional[UUID]=None
    merchant_authorized:StrictBool=False
    authorization_reference:Optional[str]=Field(default=None,max_length=255)
    received_amount:Optional[Decimal]=None
    @field_validator('received_amount')
    @classmethod
    def exact_amount(cls,v):
        return exact_money(v) if v is not None else None

    @model_validator(mode='after')
    def discrepancy_wire(self):
        if self.action=='resolve_received_difference':
            if not self.observation_id or self.model_fields_set.intersection({'received_amount','authorization_reference','merchant_authorized'}):
                raise ValueError('Use the recorded receipt observation without amount or reference overrides.')
        elif self.observation_id is not None:
            raise ValueError('Observation is only used when recording an existing receipt difference.')
        return self
