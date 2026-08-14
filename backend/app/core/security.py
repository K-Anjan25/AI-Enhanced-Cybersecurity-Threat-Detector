from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
from uuid import uuid4

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import User, TokenBlocklist

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

security = HTTPBearer(auto_error=False)


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


def _decode_access_token(token: str, db: Session, credentials_exception: HTTPException) -> User:
    """Shared token -> user resolution for Bearer headers and httpOnly cookies."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception

        # Optional: Check if token JTI is blocklisted
        jti = payload.get("jti")
        if jti and db.query(TokenBlocklist).filter_by(jti=jti).first():
            raise HTTPException(status_code=401, detail="Token has been revoked")

    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Account is blocked")

    return user


def get_current_user(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """
    Resolves the current authenticated user from either an Authorization
    Bearer header or the httpOnly access_token cookie (when COOKIE_AUTH is
    enabled). This keeps JWTs out of localStorage while remaining backward
    compatible with Bearer-token clients.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials if credentials else None
    if token is None and settings.COOKIE_AUTH and request is not None:
        token = request.cookies.get("access_token")

    if not token:
        raise credentials_exception

    return _decode_access_token(token, db, credentials_exception)


def require_role(role: str):
    def _dependency(user: User = Depends(get_current_user)):
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        user_role = getattr(user, "role", "user") or "user"
        if user_role.lower() != role.lower() and role.lower() != "any":
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return _dependency
