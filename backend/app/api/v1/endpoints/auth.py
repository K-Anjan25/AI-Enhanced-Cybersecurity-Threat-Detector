from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, OAuth2PasswordRequestForm, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app.core.database import get_db
from app.core.config import settings
from jose import jwt, JWTError
from app.utils.email_utils import send_email
from app.models import User, TokenBlocklist, Org
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.utils.rate_limit import RateLimiter

router = APIRouter()
security = HTTPBearer(auto_error=False)

login_limiter = RateLimiter(limit=settings.LOGIN_RATE_LIMIT_PER_MINUTE, window_seconds=60)


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


@router.get("/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    """Returns basic info about the currently authenticated user (root path)."""
    return {
        "status": "success",
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role,
            "profileImageURL": current_user.profile_image or "",
        },
        "roles": [current_user.role] if current_user.role else [],
    }


@router.post("/refresh")
def refresh_token(
    request: Request = None,
    response: Response = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Issue a new access token from a valid refresh token."""
    token = credentials.credentials if credentials else None
    if token is None and settings.COOKIE_AUTH and request is not None:
        token = request.cookies.get("refresh_token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    jti = payload.get("jti")
    if jti and db.query(TokenBlocklist).filter_by(jti=jti).first():
        raise HTTPException(status_code=401, detail="Token has been revoked")

    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first() if username else None
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Account is blocked")

    access_token = create_access_token(subject=user.username)
    if settings.COOKIE_AUTH and response is not None:
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite="strict",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
    }

@router.post("/register", status_code=201)
def register(data: dict, db: Session = Depends(get_db)):
    existing = db.query(User).filter(
        (User.username == data.get("username")) | (User.email == data.get("email"))
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    # Assign the default org so every user has a tenant (multi-tenancy v3).
    default_org = db.query(Org).filter(Org.slug == "default").first()
    if default_org is None:
        default_org = Org(name="Default Organization", slug="default")
        db.add(default_org)
        db.flush()

    hashed_password = get_password_hash(data["password"])
    user = User(
        username=data["username"],
        password=hashed_password,
        email=data.get("email"),
        role=data.get("role", "user"),
        org_id=default_org.id,
    )
    db.add(user)
    db.commit()
    return {"message": "User registered successfully"}

@router.post("/login")
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # Brute-force protection: per-client-IP sliding-window rate limit.
    client_ip = request.client.host if request.client else "unknown"
    limiter_key = f"login:{client_ip}"
    if not login_limiter.check(limiter_key):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
        )

    # Support logging in with either username or email field
    user = db.query(User).filter(
        (User.username == form_data.username) | (User.email == form_data.username)
    ).first()

    if not user or not verify_password(form_data.password, user.password):
        # Failed-attempt counter flips is_blocked after N consecutive failures.
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.LOGIN_MAX_ATTEMPTS:
                user.is_blocked = True
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Account is blocked")

    access_token = create_access_token(subject=user.username)
    refresh_token = create_refresh_token(subject=user.username)

    # Reset the failed-attempt counter on a successful login.
    if user.failed_login_attempts:
        user.failed_login_attempts = 0
        db.commit()

    if settings.COOKIE_AUTH:
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite="strict",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite="strict",
            max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "email": user.email,
        "profileImageURL": user.profile_image or "",
    }

@router.post("/logout")
def logout(
    response: Response,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials if credentials else None
    if token:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
            jti = payload.get("jti")

            if jti:
                # Check if already blocklisted
                exists = db.query(TokenBlocklist).filter_by(jti=jti).first()
                if not exists:
                    block_token = TokenBlocklist(jti=jti)
                    db.add(block_token)
                    db.commit()
        except JWTError:
            raise HTTPException(status_code=400, detail="Invalid token or already expired")

    if settings.COOKIE_AUTH:
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")

    return {"message": "Successfully logged out"}


@router.post("/forgot-password")
def forgot_password(data: dict, db: Session = Depends(get_db)):
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    user = db.query(User).filter(User.email == email).first()
    # Do not reveal whether user exists in production; here return token for dev/testing
    if not user:
        return {"message": "If an account exists, a reset link was sent."}

    from datetime import datetime, timedelta

    to_encode = {
        "sub": user.username,
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "purpose": "reset",
    }
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)
    # If SMTP is configured, send an email with the token; otherwise return token for dev/testing.
    email_sent = False
    if settings.SMTP_HOST and settings.EMAIL_FROM:
        reset_link = f"{settings.PROJECT_NAME} - Use token: {token}"
        try:
            email_sent = send_email(
                subject="Password reset for " + settings.PROJECT_NAME,
                recipient=user.email,
                body=f"Use the following token to reset your password: {token}\n\nThis token expires in 30 minutes."
            )
        except Exception:
            email_sent = False

    response = {"message": "Password reset token generated"}
    if email_sent:
        response["email_sent"] = True
    elif settings.ENVIRONMENT == "development":
        # Provide token in response for development convenience only.
        response["reset_link"] = token

    return response


@router.post("/reset-password")
def reset_password(payload: dict, db: Session = Depends(get_db)):
    token = payload.get("token")
    new_password = payload.get("new_password")

    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and new_password are required")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose") != "reset":
            raise HTTPException(status_code=400, detail="Invalid token purpose")

        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=400, detail="Invalid token payload")

        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.password = get_password_hash(new_password)
        db.commit()
        return {"message": "Password reset successfully"}
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")