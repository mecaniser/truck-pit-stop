from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
from jose import JWTError, jwt
import bcrypt
from app.core.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt(rounds=12)  # Explicit rounds for security
    ).decode('utf-8')


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    token_version: int = 0,
    tenant_id: Optional[str] = None,
) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "jti": str(uuid.uuid4()),  # Unique token ID for blacklisting
        "ver": token_version,      # Token version for mass invalidation
    })
    if tenant_id:
        to_encode["tid"] = tenant_id  # Active tenant scope for customers
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    data: dict,
    token_version: int = 0,
    remember_me: bool = False,
    tenant_id: Optional[str] = None,
) -> str:
    to_encode = data.copy()
    days = settings.REFRESH_TOKEN_EXPIRE_DAYS_REMEMBER if remember_me else settings.REFRESH_TOKEN_EXPIRE_DAYS
    expire = datetime.now(timezone.utc) + timedelta(days=days)
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "ver": token_version,
        "rem": remember_me,  # Preserve remember_me preference for token refresh
    })
    if tenant_id:
        to_encode["tid"] = tenant_id  # Active tenant scope for customers
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_shop_select_token(data: dict, token_version: int = 0) -> str:
    """Short-lived token issued when a customer has multiple shops and must pick one."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    to_encode.update({
        "exp": expire,
        "type": "shop_select",
        "jti": str(uuid.uuid4()),
        "ver": token_version,
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def get_token_expiry_seconds(token: str) -> int:
    """Get remaining seconds until token expires."""
    payload = decode_token(token)
    if not payload or "exp" not in payload:
        return 0
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    remaining = (exp - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(remaining))
