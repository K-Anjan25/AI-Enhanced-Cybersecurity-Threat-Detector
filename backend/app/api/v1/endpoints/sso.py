"""SSO endpoints — OIDC + SAML 2.0 (Phase 41).

Public:
- GET /auth/sso/config — is SSO enabled? returns oidc + saml if configured
- GET /auth/sso/login — OIDC redirect to IdP
- GET /auth/sso/callback — OIDC handles code, issues JWTs as cookies
- GET /auth/sso/saml/login — SAML SP-initiated AuthnRequest redirect
- POST /auth/sso/saml/callback — SAML ACS, handles SAMLResponse, issues JWTs

Admin:
- GET/POST/PUT/DELETE /admin/sso/providers — CRUD per-org provider (oidc|saml)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query, Form
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
    # OIDC
    issuer: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scopes: Optional[str] = None
    # SAML
    saml_metadata_url: Optional[str] = None
    saml_entity_id: Optional[str] = None
    saml_acs_url: Optional[str] = None
    saml_sso_url: Optional[str] = None
    saml_certificate: Optional[str] = None
    saml_nameid_format: Optional[str] = None
    # Common
    enabled: bool = True
    jit_provisioning: bool = True


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    if not settings.COOKIE_AUTH:
        return
    samesite = settings.COOKIE_SAMESITE
    secure = settings.COOKIE_SECURE or samesite == "none"

    if settings.COOKIE_PARTITIONED and samesite == "none":
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


def _frontend_redirect_url(request: Request) -> str:
    frontend = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "/"
    return f"{frontend}/" if frontend.startswith("http") else "/"


# Public config

@router.get("/sso/config")
def get_sso_config(db: Session = Depends(get_db)):
    return sso_service.get_sso_config(db, org_id=None)


# OIDC

@router.get("/sso/login")
def sso_login(
    request: Request,
    redirect_uri: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    cfg = sso_service.get_sso_config(db, org_id=None)
    if not cfg.get("enabled") and not cfg.get("oidc"):
        raise HTTPException(status_code=404, detail="SSO not configured")

    if not redirect_uri:
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
    if error:
        raise HTTPException(status_code=400, detail=f"SSO error: {error} {error_description or ''}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/api/v1/auth/sso/callback"

    try:
        user, access_token, refresh_token = sso_service.handle_callback(
            db, code=code, state=state, redirect_uri=redirect_uri
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SSO callback failed: {exc}")

    _set_auth_cookies(response, access_token, refresh_token)

    redirect_to = _frontend_redirect_url(request)
    resp = RedirectResponse(url=redirect_to, status_code=302)
    for k, v in response.headers.items():
        if k.lower() == "set-cookie":
            resp.headers.append(k, v)
    if settings.COOKIE_AUTH and not (settings.COOKIE_PARTITIONED and settings.COOKIE_SAMESITE == "none"):
        samesite = settings.COOKIE_SAMESITE
        secure = settings.COOKIE_SECURE or samesite == "none"
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


# SAML — Phase 41

@router.get("/sso/saml/login")
def saml_login(
    request: Request,
    db: Session = Depends(get_db),
):
    cfg = sso_service.get_sso_config(db, org_id=None)
    saml_cfg = cfg.get("saml")
    if not saml_cfg or not saml_cfg.get("enabled"):
        # Also check if SAML env enabled
        if not settings.SSO_SAML_ENABLED and not saml_cfg:
            raise HTTPException(status_code=404, detail="SAML SSO not configured")

    base = str(request.base_url).rstrip("/")
    acs_url = f"{base}/api/v1/auth/sso/saml/callback"

    try:
        redirect_url, relay_state = sso_service.create_saml_authn_request(
            db, org_id=None, acs_url=acs_url
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start SAML SSO: {exc}")

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/sso/saml/callback")
def saml_callback(
    request: Request,
    response: Response,
    SAMLResponse: Optional[str] = Form(None),
    RelayState: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not SAMLResponse:
        raise HTTPException(status_code=400, detail="Missing SAMLResponse")

    if not RelayState:
        raise HTTPException(status_code=400, detail="Missing RelayState")

    try:
        user, access_token, refresh_token = sso_service.handle_saml_callback(
            db, saml_response=SAMLResponse, relay_state=RelayState
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SAML callback failed: {exc}")

    _set_auth_cookies(response, access_token, refresh_token)

    redirect_to = _frontend_redirect_url(request)
    resp = RedirectResponse(url=redirect_to, status_code=302)
    for k, v in response.headers.items():
        if k.lower() == "set-cookie":
            resp.headers.append(k, v)
    if settings.COOKIE_AUTH and not (settings.COOKIE_PARTITIONED and settings.COOKIE_SAMESITE == "none"):
        samesite = settings.COOKIE_SAMESITE
        secure = settings.COOKIE_SECURE or samesite == "none"
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
            db, org_id=current_user.org_id, payload=payload.model_dump(exclude_none=True), actor=current_user.username
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
        "saml_metadata_url": provider.saml_metadata_url,
        "saml_entity_id": provider.saml_entity_id,
        "saml_acs_url": provider.saml_acs_url,
        "saml_sso_url": provider.saml_sso_url,
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
            db, org_id=current_user.org_id, payload=payload.model_dump(exclude_none=True), actor=current_user.username
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
        "saml_metadata_url": provider.saml_metadata_url,
        "saml_entity_id": provider.saml_entity_id,
        "saml_acs_url": provider.saml_acs_url,
        "saml_sso_url": provider.saml_sso_url,
        "enabled": provider.enabled,
        "jit_provisioning": provider.jit_provisioning,
    }


@router.delete("/admin/sso/providers")
def delete_sso_provider(
    provider_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    try:
        return sso_service.delete_provider(db, org_id=current_user.org_id, provider_type=provider_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
