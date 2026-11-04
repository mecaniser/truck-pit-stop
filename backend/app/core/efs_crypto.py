"""Dedicated, versioned EFS bearer-secret encryption and tenant-scoped lookup."""
import hashlib
import hmac
import json
import re
from cryptography.fernet import Fernet,InvalidToken
from app.core.config import settings

PURPOSE='customer_efs_moneycode:v1'
class EfsCryptoUnavailable(ValueError):pass

def keys():
    try:
        values=json.loads(settings.EFS_INSTRUMENT_ENCRYPTION_KEYS)
        active=settings.EFS_INSTRUMENT_ENCRYPTION_ACTIVE_KEY
        if not isinstance(values,dict) or not values or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',active):raise ValueError()
        if any(not isinstance(version,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',version) for version in values):raise ValueError()
        ciphers={version:Fernet(value.encode()) for version,value in values.items()}
        fingerprint_key=settings.EFS_INSTRUMENT_FINGERPRINT_KEY
        if not isinstance(fingerprint_key,str) or len(fingerprint_key.encode())<32 or active not in ciphers:raise ValueError()
        other_keys={value for value in (getattr(settings,'SECRET_KEY',''),getattr(settings,'QUICKBOOKS_TOKEN_ENCRYPTION_KEY',''),getattr(settings,'GOOGLE_BUSINESS_TOKEN_ENCRYPTION_KEY',''),getattr(settings,'PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY','')) if value}
        for field in ('MOTIVE_TOKEN_ENCRYPTION_KEYS','PAID_INVOICE_WEBHOOK_ENCRYPTION_KEYS'):
            try:other_keys.update(json.loads(getattr(settings,field,'{}') or '{}').values())
            except (ValueError,AttributeError):pass
        if fingerprint_key in other_keys or fingerprint_key in values.values() or any(value in other_keys for value in values.values()):raise ValueError()
        return active,ciphers,fingerprint_key.encode()
    except (ValueError,TypeError,KeyError,AttributeError):raise EfsCryptoUnavailable('EFS secret storage is unavailable') from None

def normalize(value):
    if not isinstance(value,str):raise ValueError('Enter a ten-digit EFS MoneyCode.')
    value=value.strip()
    if not re.fullmatch(r'[0-9]{10}',value):raise ValueError('Enter a ten-digit EFS MoneyCode.')
    return value

def keyed(value,*,purpose,tenant_id):
    _,_,key=keys()
    return hmac.new(key,json.dumps([PURPOSE,purpose,str(tenant_id),value],separators=(',',':')).encode(),hashlib.sha256).hexdigest()

def key_identity():
    _,_,key=keys()
    return hmac.new(key,(PURPOSE+":stable-key-identity").encode(),hashlib.sha256).hexdigest()

def fingerprint(code,tenant_id):return keyed(normalize(code),purpose='instrument',tenant_id=tenant_id)
def command_key(key,tenant_id):return 'efs:'+keyed(key,purpose='command',tenant_id=tenant_id)

def context(row):return [PURPOSE,row.key_version,str(row.tenant_id),str(row.invoice_id),str(row.attempt_id),str(row.customer_id),str(row.id)]

def encrypt(code,row):
    active,ciphers,_=keys()
    if row.key_version!=active:raise EfsCryptoUnavailable('EFS secret storage is unavailable')
    return ciphers[active].encrypt(json.dumps({'context':context(row),'code':normalize(code)},separators=(',',':')).encode()).decode()

def decrypt(row):
    try:
        _,ciphers,_=keys();data=json.loads(ciphers[row.key_version].decrypt(row.secret_ciphertext.encode()))
        if data['context']!=context(row):raise ValueError()
        value=normalize(data['code'])
        if not hmac.compare_digest(fingerprint(value,row.tenant_id),row.code_fingerprint) or value[-4:]!=row.last4:raise ValueError()
        return value
    except (ValueError,TypeError,KeyError,AttributeError,InvalidToken):raise EfsCryptoUnavailable('EFS secret storage is unavailable') from None
