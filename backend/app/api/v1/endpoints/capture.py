"""Authenticated capture-sensor heartbeat and status routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status

from app.api.v1.deps import audit_trail, client_ip
from app.auth.rbac import Capability, Principal, require
from app.schemas.capture import CaptureHealthOut, CaptureHeartbeatIn, CaptureSensorHealth
from app.services.audit_log import AuditAction, record_action
from app.services.capture_health import CaptureHealthCapacityError, CaptureHealthRegistry

router = APIRouter(tags=["capture"])


@router.post(
    "/api/v1/capture/heartbeat",
    response_model=CaptureSensorHealth,
    status_code=status.HTTP_200_OK,
    summary="Report a live capture sensor heartbeat",
    responses={429: {"description": "The bounded registry is full of live sensors."}},
)
def report_capture_heartbeat(
    request: Request,
    body: CaptureHeartbeatIn,
    caller: Annotated[Principal, require(Capability.INGEST)],
) -> CaptureSensorHealth:
    """Record that a supervised Docker capture sensor is still running."""
    registry: CaptureHealthRegistry = request.app.state.capture_health
    try:
        heartbeat = registry.record(body.sensor_id, body.engines)
    except CaptureHealthCapacityError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="capture health registry is full of live sensors",
        ) from exc
    record_action(
        audit_trail(request),
        action=AuditAction.capture_heartbeat,
        actor=caller.subject,
        target_type="capture_sensor",
        target_id=body.sensor_id,
        at=datetime.now(UTC),
        detail={"engines": list(body.engines)},
        ip=client_ip(request),
    )
    return CaptureSensorHealth.model_validate(heartbeat)


@router.get(
    "/api/v1/capture/status",
    response_model=CaptureHealthOut,
    summary="Read capture sensor health",
    dependencies=[require(Capability.READ)],
)
def capture_status(request: Request) -> CaptureHealthOut:
    """Return only real sensor heartbeats; an empty fleet is explicitly unknown."""
    registry: CaptureHealthRegistry = request.app.state.capture_health
    return CaptureHealthOut.model_validate(registry.snapshot())
