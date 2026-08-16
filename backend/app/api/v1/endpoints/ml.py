"""Proxy endpoints to the ml-service: benchmark + explainability."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.abac import require_permission
from app.core.config import settings
from app.models import User
from app.services import ml_client

router = APIRouter(prefix="/ml", tags=["Machine Learning"])


def _post(path: str, payload: dict) -> dict:
    try:
        return ml_client._post_with_retry(f"{settings.ML_SERVICE_URL}{path}", payload)
    except Exception:
        raise HTTPException(status_code=503, detail="ML service unreachable")


@router.get("/benchmark")
def ml_benchmark(current_user: User = Depends(require_permission("analytics:read"))):
    """Evaluate deployed ML artifacts against holdout sets (ml-service)."""
    try:
        return ml_client._get_with_retry(f"{settings.ML_SERVICE_URL}/benchmark")
    except Exception:
        raise HTTPException(status_code=503, detail="ML service unreachable")


@router.post("/explain/log")
def explain_log(payload: dict, current_user: User = Depends(require_permission("analytics:read"))):
    return _post("/explain/log", payload)


@router.post("/explain/email")
def explain_email(payload: dict, current_user: User = Depends(require_permission("analytics:read"))):
    return _post("/explain/email", payload)


@router.post("/explain/network")
def explain_network(payload: dict, current_user: User = Depends(require_permission("analytics:read"))):
    return _post("/explain/network", payload)


@router.post("/explain/dns")
def explain_dns(payload: dict, current_user: User = Depends(require_permission("analytics:read"))):
    return _post("/explain/dns", payload)