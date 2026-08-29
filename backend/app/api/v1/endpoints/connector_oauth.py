"""Connector OAuth endpoints — GitHub App + Slack OAuth (Phase 41).

Flow:
- GET /connectors/{id}/oauth/status — is OAuth connected?
- GET /connectors/{id}/oauth/start — redirect to provider (GitHub/Slack)
- GET /connectors/{id}/oauth/callback — exchange code, store encrypted token, redirect to frontend
- DELETE /connectors/{id}/oauth — disconnect
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.services import connector_oauth_service

router = APIRouter(prefix="/connectors", tags=["Connector OAuth"])


@router.get("/{connector_id}/oauth/status")
def oauth_status(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return connector_oauth_service.get_connector_oauth_status(
        db, org_id=current_user.org_id, connector_id=connector_id
    )


@router.get("/{connector_id}/oauth/start")
def oauth_start(
    connector_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if connector_id not in ("github", "slack"):
        raise HTTPException(status_code=400, detail="OAuth only supported for github and slack connectors")

    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/api/v1/connectors/{connector_id}/oauth/callback"

    # Allow override via config
    if settings.CONNECTOR_OAUTH_REDIRECT_BASE:
        redirect_uri = f"{settings.CONNECTOR_OAUTH_REDIRECT_BASE.rstrip('/')}/api/v1/connectors/{connector_id}/oauth/callback"

    try:
        auth_url, state = connector_oauth_service.create_oauth_authorization_url(
            db, org_id=current_user.org_id, connector_id=connector_id, redirect_uri=redirect_uri
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/{connector_id}/oauth/callback")
def oauth_callback(
    connector_id: str,
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    try:
        row = connector_oauth_service.exchange_oauth_code(
            db, org_id=None, code=code, state=state
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {exc}")

    # Phase 42: auto-create poll config for this connector if not exists, so scheduler can pick it up
    try:
        from app.services import connector_service

        cfg = connector_service.get_config(db, org_id=row.org_id, connector_id=connector_id)
        if cfg is None:
            endpoint = (
                "https://api.github.com/orgs/{org}/code-scanning/alerts"
                if connector_id == "github"
                else "https://api.slack.com/audit/v1/logs"
            )
            connector_service.upsert_config(
                db,
                org_id=row.org_id,
                connector_id=connector_id,
                payload={
                    "mode": "poll",
                    "endpoint": endpoint,
                    "enabled": True,
                },
                actor="oauth",
            )
    except Exception:
        # Non-fatal — OAuth still connected, config can be created manually
        pass

    # Redirect to frontend — show success
    frontend = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "/"
    redirect_to = f"{frontend}/?oauth_connected={connector_id}" if frontend.startswith("http") else f"/?oauth_connected={connector_id}"

    return RedirectResponse(url=redirect_to, status_code=302)


@router.delete("/{connector_id}/oauth")
def oauth_disconnect(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return connector_oauth_service.disconnect_oauth(
            db, org_id=current_user.org_id, connector_id=connector_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
