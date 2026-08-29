"""SSO OIDC endpoints — login + callback + admin config.

Public:
- GET /auth/sso/config — is SSO enabled?
- GET /auth/sso/login — redirect to IdP (starts Authorization Code flow)
- GET /auth/sso/callback — handles code, issues our JWTs as cookies

Admin:
- GET/POST/PUT /admin/sso/providers — CRUD per-org provider
- DELETE /admin/sso/providers
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models import User
from app.services import sso_service

router = APIRouter()


class SsoProviderRequest(BaseModel):
    provider_type: str = "oidc"
    display_name: Optional[str] = None
    issuer: str
    client_id: str
    client_secret: Optional[str] = None
    scopes: Optional[str] = None
    enabled: bool = True
    jit_provisioning: bool = True


# Public config — used by login page to show SSO button

@router.get("/sso/config")
def get_sso_config(db: Session = Depends(get_db)):
    return sso_service.get_sso_config(db, org_id=None)


@router.get("/sso/login")
def sso_login(
    request: Request,
    redirect_uri: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Start OIDC flow — redirects to IdP authorization endpoint."""
    cfg = sso_service.get_sso_config(db, org_id=None)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=404, detail="SSO not configured")

    # Where IdP should redirect back to
    # If redirect_uri not provided, use request base + callback path
    if not redirect_uri:
        # Build from request
        base = str(request.base_url).rstrip("/")
        redirect_uri = f"{base}/api/v1/auth/sso/callback"

    try:
        auth_url, state = sso_service.create_authorization_url(
            db, redirect_uri=redirect_uri, org_id=None
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start SSO: {exc}")

    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/sso/callback")
def sso_callback(
    request: Request,
    response: Response,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """OIDC callback — exchanges code, JIT provisions user, sets auth cookies, redirects to frontend."""
    if error:
        raise HTTPException(status_code=400, detail=f"SSO error: {error} {error_description or ''}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    # Reconstruct redirect_uri — must match what was sent to IdP
    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/api/v1/auth/sso/callback"

    # Allow override via query param from login step? We stored it in state store
    # The stored redirect_uri is authoritative, but we also need to pass it to exchange

    try:
        user, access_token, refresh_token = sso_service.handle_callback(
            db, code=code, state=state, redirect_uri=redirect_uri
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SSO callback failed: {exc}")

    # Set cookies like normal login
    if settings.COOKIE_AUTH:
        samesite = settings.COOKIE_SAMESITE
        secure = settings.COOKIE_SECURE or samesite == "none"

        if settings.COOKIE_PARTITIONED and samesite == "none":
            # Manual header for partitioned
            response.headers.append(
                "Set-Cookie",
                f"access_token={access_token}; Max-Age={settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}; Path=/; HttpOnly; Secure; SameSite=None; Partitioned",
            )
            response.headers.append(
                "Set-Cookie",
                f"refresh_token={refresh_token}; Max-Age={settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60}; Path=/; HttpOnly; Secure; SameSite=None; Partitioned",
            )
        else:
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=secure,
                samesite=samesite,
                max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                path="/",
            )
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=secure,
                samesite=samesite,
                max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
                path="/",
            )

    # Redirect to frontend — dashboard will pick up cookies
    # Use CORS_ORIGINS[0] as frontend origin if available
    frontend = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "/"
    # If frontend is localhost:3000, redirect there
    # In compose, frontend is served from same origin via nginx, so "/" works
    redirect_to = f"{frontend}/" if frontend.startswith("http") else "/"

    resp = RedirectResponse(url=redirect_to, status_code=302)
    # Copy cookies to redirect response
    for k, v in response.headers.items():
        if k.lower() == "set-cookie":
            resp.headers.append(k, v)
    # Also set via set_cookie on redirect response for non-partitioned case
    if settings.COOKIE_AUTH and not (settings.COOKIE_PARTITIONED and settings.COOKIE_SAMESITE == "none"):
        resp.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=secure,
            samesite=samesite,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
        resp.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=secure,
            samesite=samesite,
            max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )

    return resp


# Admin CRUD

@router.get("/admin/sso/providers")
def list_sso_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    cfg = sso_service.get_sso_config(db, org_id=current_user.org_id)
    # Also check global
    global_cfg = sso_service.get_sso_config(db, org_id=None)
    return {"org": cfg, "global": global_cfg}


@router.post("/admin/sso/providers")
def create_sso_provider(
    payload: SsoProviderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    try:
        provider = sso_service.upsert_provider(
            db, org_id=current_user.org_id, payload=payload.model_dump(), actor=current_user.username
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "id": provider.id,
        "provider_type": provider.provider_type,
        "display_name": provider.display_name,
        "issuer": provider.issuer,
        "client_id": provider.client_id,
        "scopes": provider.scopes,
        "enabled": provider.enabled,
        "jit_provisioning": provider.jit_provisioning,
    }


@router.put("/admin/sso/providers")
def update_sso_provider(
    payload: SsoProviderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    try:
        provider = sso_service.upsert_provider(
            db, org_id=current_user.org_id, payload=payload.model_dump(), actor=current_user.username
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "id": provider.id,
        "provider_type": provider.provider_type,
        "display_name": provider.display_name,
        "issuer": provider.issuer,
        "client_id": provider.client_id,
        "scopes": provider.scopes,
        "enabled": provider.enabled,
        "jit_provisioning": provider.jit_provisioning,
    }


@router.delete("/admin/sso/providers")
def delete_sso_provider(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    try:
        return sso_service.delete_provider(db, org_id=current_user.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
