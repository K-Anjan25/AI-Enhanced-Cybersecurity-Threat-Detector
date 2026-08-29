"""Phase 61: ZTNA + microsegmentation endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import ztna_service

router = APIRouter(prefix="/ztna", tags=["ZTNA (Phase 61)"])


class SegmentCreate(BaseModel):
    name: str
    cidr: str
    zone: str = "internal"
    description: Optional[str] = None


class PolicyCreate(BaseModel):
    name: str
    policy_json: Dict[str, Any] = {}
    src_segment_id: Optional[int] = None
    dst_segment_id: Optional[int] = None
    action: str = "deny"
    priority: int = 100


class EvaluateRequest(BaseModel):
    src_ip: str
    dst_ip: str


@router.get("/segments")
def list_segments(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    rows = ztna_service.list_segments(db, org_id=current_user.org_id)
    return [ztna_service.serialize_segment(r) for r in rows]


@router.post("/segments", status_code=201)
def create_segment(payload: SegmentCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        seg = ztna_service.create_segment(db, org_id=current_user.org_id, name=payload.name, cidr=payload.cidr, zone=payload.zone, description=payload.description)
        return ztna_service.serialize_segment(seg)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/policies")
def list_policies(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    rows = ztna_service.list_policies(db, org_id=current_user.org_id)
    return [ztna_service.serialize_policy(r) for r in rows]


@router.post("/policies", status_code=201)
def create_policy(payload: PolicyCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        p = ztna_service.create_policy(
            db,
            org_id=current_user.org_id,
            name=payload.name,
            policy_json=payload.policy_json,
            src_segment_id=payload.src_segment_id,
            dst_segment_id=payload.dst_segment_id,
            action=payload.action,
            priority=payload.priority,
            created_by_user_id=current_user.id,
        )
        return ztna_service.serialize_policy(p)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/evaluate")
def evaluate(payload: EvaluateRequest, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    return ztna_service.evaluate_access(db, org_id=current_user.org_id, src_ip=payload.src_ip, dst_ip=payload.dst_ip, user_id=current_user.id, user_role=current_user.role)


@router.get("/graph")
def get_graph(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    return ztna_service.get_microseg_graph(db, org_id=current_user.org_id)
