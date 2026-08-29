"""Connector configuration + push-ingest endpoints.

Companion to the analyst surface: `/analyst/connectors` reports state, these
endpoints let an operator make that state real, and
`/api/v1/connectors/ingest/{id}` is the webhook a source posts events to.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.abac import require_permission
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import ConnectorSource, User
from app.services import connector_service

router = APIRouter(prefix="/connectors", tags=["Connectors"])


class ConnectorConfigRequest(BaseModel):
    mode: str = Field("push", description="poll | push")
    endpoint: Optional[str] = None
    auth_header: Optional[str] = None
    auth_token: Optional[str] = None
    ingest_token: Optional[str] = None
    enabled: Optional[bool] = None


class IngestRequest(BaseModel):
    events: list = Field(default_factory=list)


@router.get("")
def list_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every configured source for this tenant (secrets omitted)."""
    rows = (
        db.query(ConnectorSource)
        .filter(ConnectorSource.org_id == current_user.org_id)
        .order_by(ConnectorSource.connector_id)
        .all()
    )
    return [connector_service.serialize_config(cfg) for cfg in rows]


@router.get("/{connector_id}/config")
def read_config(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    cfg = connector_service.get_config(db, current_user.org_id, connector_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No configuration for this connector")
    return connector_service.serialize_config(cfg)


@router.put("/{connector_id}/config")
def write_config(
    connector_id: str,
    payload: ConnectorConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Create or update a connector source.

    Adding a source is an operational change with real side effects (it can
    write alerts), so it requires `alerts:write` and lands in the audit trail.
    """
    try:
        return connector_service.upsert_config(
            db,
            current_user.org_id,
            connector_id,
            payload.model_dump(exclude_none=True),
            actor=current_user.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/{connector_id}/config")
def remove_config(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    try:
        return connector_service.delete_config(
            db, current_user.org_id, connector_id, actor=current_user.username
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/ingest/{connector_id}", status_code=201)
def ingest_events(
    connector_id: str,
    payload: IngestRequest,
    x_connector_token: Optional[str] = Header(None, alias="X-Connector-Token"),
    db: Session = Depends(get_db),
):
    """Push ingest webhook — no session required, authenticated by shared secret.

    The honest counterpart to polling: a provider (or a cron job, or a curl in
    a demo) posts events here and they become real alerts attributed to the
    connector.
    """
    try:
        return connector_service.ingest_push(
            db, connector_id, x_connector_token or "", payload.events
        )
    except connector_service.RateLimited as exc:
        # 429 with Retry-After, so a well-behaved sender backs off instead of
        # hammering a limit it cannot see.
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
