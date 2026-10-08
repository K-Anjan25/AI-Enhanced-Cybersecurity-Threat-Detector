"""Health and readiness endpoints.

Thin by design (rule R-13): call the service, serialise the result. No business
logic and no dependency access happens here.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.schemas.health import HealthResponse, ReadinessResponse
from app.services import health_service

router = APIRouter(tags=["health"])


@router.get("/api/v1/detection/status", summary="Rule-based detection engine status")
def detection_status(request: Request) -> dict[str, object]:
    """Return the detection engine's current stats."""
    engine = getattr(request.app.state, "detection_engine", None)
    if engine is None:
        return {"status": "not_configured"}
    return engine.stats


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
def healthz(request: Request) -> HealthResponse:
    """Report that the process is alive.

    Deliberately ignores dependency state: a database outage should not cause
    orchestrators to restart this process in a loop.
    """
    state = request.app.state
    return HealthResponse(
        **health_service.build_health(
            service=state.service_name,
            version=state.version,
            environment=state.environment,
        )
    )


@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness probe")
def readyz(request: Request, response: Response) -> ReadinessResponse:
    """Report whether the process can serve traffic.

    Returns HTTP 503 when any registered dependency probe is not ``ok``.
    """
    state = request.app.state
    payload, status_code = health_service.build_readiness(
        service=state.service_name,
        version=state.version,
        registry=state.readiness,
    )
    response.status_code = status_code
    return ReadinessResponse.model_validate(payload)
