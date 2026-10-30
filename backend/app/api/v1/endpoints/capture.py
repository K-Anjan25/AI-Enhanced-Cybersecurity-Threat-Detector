"""Capture control: read and set the desired packet-capture state (step 4).

Writes are restricted to the RESPONDER and ADMIN roles (see ``ROUTE_MATRIX``), and
every change is written to the audit trail. The check is repeated in the handler, so
the endpoint does not depend on the matrix being wired correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.v1.deps import audit_trail, client_ip
from app.auth.rbac import Capability, authenticate_request
from app.services.audit_log import AuditAction, record_action
from app.services.capture_control import (
    DEFAULT_ENGINES,
    CaptureControl,
    CaptureState,
    InvalidCaptureRequest,
)
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["capture"])


def no_store(response: Response) -> None:
    """Keep control state out of shared caches."""
    response.headers["Cache-Control"] = "no-store"


class CaptureStateIn(BaseModel):
    """A request to start or stop capture, and which engines to use."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    running: bool
    engines: list[str] = Field(default_factory=lambda: list(DEFAULT_ENGINES), max_length=3)


class CaptureStateOut(BaseModel):
    """The desired capture state and when it was last changed."""

    running: bool
    engines: list[str]
    version: int
    changed_by: str | None
    changed_at: datetime | None

    @classmethod
    def of(cls, state: CaptureState) -> CaptureStateOut:
        """Project the service's state into the response shape."""
        return cls(
            running=state.running,
            engines=list(state.engines),
            version=state.version,
            changed_by=state.changed_by,
            changed_at=state.changed_at,
        )


def _control(request: Request) -> CaptureControl:
    return request.app.state.capture_control  # type: ignore[no-any-return]


@router.get(
    "/api/v1/capture/state",
    response_model=CaptureStateOut,
    summary="Desired packet-capture state",
)
def get_capture_state(request: Request, response: Response) -> CaptureStateOut:
    """Return what capture should be doing. Operators only."""
    no_store(response)
    authenticate_request(request, Capability.CAPTURE)
    return CaptureStateOut.of(_control(request).get())


@router.put(
    "/api/v1/capture/state",
    response_model=CaptureStateOut,
    summary="Start or stop capture, and choose its engines",
)
def set_capture_state(
    body: CaptureStateIn,
    request: Request,
    response: Response,
) -> CaptureStateOut:
    """Change the desired state. Each change is audited with the actor and the engines."""
    no_store(response)
    principal = authenticate_request(request, Capability.CAPTURE)
    now = datetime.now(UTC)
    try:
        state = _control(request).set(
            running=body.running,
            engines=body.engines,
            actor=principal.subject,
            at=now,
        )
    except InvalidCaptureRequest as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    record_action(
        audit_trail(request),
        action=AuditAction.capture_state,
        actor=principal.subject,
        target_type="capture",
        target_id="sensor",
        at=now,
        detail={"running": state.running, "engines": list(state.engines), "version": state.version},
        ip=client_ip(request),
    )
    return CaptureStateOut.of(state)
