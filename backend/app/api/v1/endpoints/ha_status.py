"""Phase 58: HA status + Phase 59 PWA + Phase 60 billing."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import ha_service, pwa_service, billing_service

router = APIRouter(tags=["HA / PWA / Billing (Phases 58-60)"])


# ---- Phase 58: HA ----


@router.get("/ha/status")
def get_ha_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ha_service.get_ha_status()


@router.post("/ha/lock/{name}")
def acquire_lock(
    name: str,
    ttl: int = 60,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("system:read")),
):
    ok = ha_service.acquire_distributed_lock(name, ttl_seconds=ttl)
    return {"lock": name, "acquired": ok}


# ---- Phase 59: PWA ----


@router.get("/pwa/manifest")
def get_manifest():
    return pwa_service.get_pwa_manifest()


@router.get("/pwa/status")
def get_pwa_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {
        "manifest": pwa_service.get_pwa_manifest(),
        "push_subscriptions": len(pwa_service.list_push_subscriptions(current_user.org_id)),
        "offline_queue": pwa_service.get_offline_queue_status(current_user.org_id),
    }


class PushSubscribeRequest(BaseModel):
    subscription: Dict[str, Any]


@router.post("/pwa/push/subscribe", status_code=201)
def subscribe_push(
    payload: PushSubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return pwa_service.subscribe_push(db, org_id=current_user.org_id, user_id=current_user.id, subscription=payload.subscription)


@router.post("/pwa/push/test")
def test_push(
    title: str = "NOCTRA Alert",
    body: str = "Test push notification",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    return pwa_service.send_push_notification(org_id=current_user.org_id, title=title, body=body)


# ---- Phase 60: Billing ----


@router.get("/billing/plans")
def list_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plans = billing_service.list_plans(db)
    return [{"id": p.id, "name": p.name, "description": p.description, "max_alerts": p.max_alerts, "max_cases": p.max_cases, "max_users": p.max_users, "price_per_month": p.price_per_month, "features": p.features} for p in plans]


@router.get("/billing/quota")
def get_quota(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    q = billing_service.get_org_quota(db, org_id=current_user.org_id)
    return billing_service.serialize_quota(q)


@router.get("/billing/usage")
def get_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    return billing_service.get_current_usage(db, org_id=current_user.org_id)
