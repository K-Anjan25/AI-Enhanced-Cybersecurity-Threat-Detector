from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
from uuid import uuid4

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a bcrypt password hash."""
    return pwd_context.hash(password)


def _build_token_payload(subject: str, token_type: str, expires_delta: Optional[timedelta]) -> dict:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        minutes = (
            settings.ACCESS_TOKEN_EXPIRE_MINUTES
            if token_type == "access"
            else settings.REFRESH_TOKEN_EXPIRE_MINUTES
        )
        expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    return {
        "exp": expire,
        "sub": str(subject),
        "type": token_type,
        "jti": uuid4().hex,
    }


def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JSON Web Token (JWT) access token."""
    to_encode = _build_token_payload(str(subject), "access", expires_delta)
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JSON Web Token (JWT) refresh token with a longer lifespan."""
    to_encode = _build_token_payload(str(subject), "refresh", expires_delta)
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)
