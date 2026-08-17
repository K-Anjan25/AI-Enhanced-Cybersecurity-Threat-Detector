import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.utils.helpers import create_audit_log

router = APIRouter(tags=["Telemetry"])


class ClientErrorIn(BaseModel):
    message: str
    component_stack: str | None = None
    url: str | None = None
    user_agent: str | None = None


@router.post("/telemetry/client-error")
def report_client_error(
    payload: ClientErrorIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a dashboard client error into the append-only audit trail.

    Any authenticated subject may report errors (no permission gate); the
    entry is immutable by design (audit_logs rejects UPDATE/DELETE).
    """
    details = json.dumps(
        {
            "message": payload.message,
            "component_stack": payload.component_stack,
            "url": payload.url,
            "ip_address": request.client.host if request.client else None,
        },
        default=str,
    )
    create_audit_log(
        db,
        action="CLIENT_ERROR",
        actor=current_user.username,
        resource="dashboard",
        details=details[:4000],
        ip_address=request.client.host if request.client else None,
    )
    return {"recorded": True}