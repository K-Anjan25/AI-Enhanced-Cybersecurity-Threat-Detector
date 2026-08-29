"""Phase 47: API keys + service accounts + org rate limiting endpoints.

- API keys: create/list/revoke, scoped to org
- Service accounts: create/list/revoke
- Rate limit status: per-org current usage (Redis if available, else in-memory)
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import apikey_service

router = APIRouter(prefix="/apikeys", tags=["API Keys (Phase 47)"])


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., description="Human readable name")
    scopes: str = Field("alerts:read", description="Comma-separated scopes")
    expires_days: Optional[int] = Field(None, description="Days until expiry, None = never")
    service_account_id: Optional[int] = None


class CreateServiceAccountRequest(BaseModel):
    name: str
    description: Optional[str] = None
    role: str = Field("service", description="Role for ABAC")


@router.get("")
def list_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    rows = apikey_service.list_api_keys(db, org_id=current_user.org_id)
    return [apikey_service.serialize_api_key(k) for k in rows]


@router.post("", status_code=201)
def create_key(
    payload: CreateApiKeyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    if payload.service_account_id:
        sa = apikey_service.get_service_account(db, org_id=current_user.org_id, sa_id=payload.service_account_id)
        if not sa:
            raise HTTPException(status_code=404, detail="Service account not found")
    rec, raw = apikey_service.create_api_key(
        db,
        org_id=current_user.org_id,
        name=payload.name,
        scopes=payload.scopes,
        created_by_user_id=current_user.id,
        service_account_id=payload.service_account_id,
        expires_days=payload.expires_days,
    )
    data = apikey_service.serialize_api_key(rec)
    data["raw_key"] = raw
    data["warning"] = "Store this key securely — it will not be shown again"
    return data


@router.delete("/{key_id}")
def revoke_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    try:
        rec = apikey_service.revoke_api_key(db, org_id=current_user.org_id, key_id=key_id)
        return {"status": "revoked", "key": apikey_service.serialize_api_key(rec)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Service accounts
# ---------------------------------------------------------------------------

@router.get("/service-accounts")
def list_service_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    rows = apikey_service.list_service_accounts(db, org_id=current_user.org_id)
    return [apikey_service.serialize_service_account(sa) for sa in rows]


@router.post("/service-accounts", status_code=201)
def create_service_account(
    payload: CreateServiceAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    sa, user = apikey_service.create_service_account(
        db,
        org_id=current_user.org_id,
        name=payload.name,
        description=payload.description,
        role=payload.role,
        created_by_user_id=current_user.id,
    )
    return apikey_service.serialize_service_account(sa)


@router.delete("/service-accounts/{sa_id}")
def revoke_service_account(
    sa_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    try:
        sa = apikey_service.revoke_service_account(db, org_id=current_user.org_id, sa_id=sa_id)
        return {"status": "revoked", "service_account": apikey_service.serialize_service_account(sa)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/rate-limit/status")
def rate_limit_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return current per-org rate limit usage (best effort)."""
    from app.core.config import settings
    import time
    from collections import deque

    org_id = current_user.org_id
    rps = getattr(settings, "ORG_RATE_LIMIT_RPS", 100)
    burst = getattr(settings, "ORG_RATE_LIMIT_BURST", 200)
    enabled = getattr(settings, "ORG_RATE_LIMIT_ENABLED", True)

    # Try Redis
    redis_client = apikey_service._get_redis()
    if redis_client:
        try:
            now = int(time.time())
            key_sec = f"org:rl:{org_id}:{now}"
            count = int(redis_client.get(key_sec) or 0)
            key_min = f"org:rl:min:{org_id}:{now // 60}"
            count_min = int(redis_client.get(key_min) or 0)
            return {
                "org_id": org_id,
                "enabled": enabled,
                "rps_limit": rps,
                "burst_limit": burst,
                "current_rps": count,
                "current_per_minute": count_min,
                "backend": "redis",
            }
        except Exception:
            pass

    # In-memory fallback
    dq = apikey_service._org_buckets.get(org_id)
    now = time.time()
    count_1s = 0
    count_60s = 0
    if dq:
        count_60s = len(dq)
        count_1s = sum(1 for t in dq if t >= now - 1)
    return {
        "org_id": org_id,
        "enabled": enabled,
        "rps_limit": rps,
        "burst_limit": burst,
        "current_rps": count_1s,
        "current_per_minute": count_60s,
        "backend": "memory",
    }
