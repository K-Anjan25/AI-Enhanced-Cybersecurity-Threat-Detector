from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.abac import require_permission
from app.api.v1.endpoints.auth import get_current_user
from app.models import User
from app.services import item_service
from app.schemas.item import IpReputationOut, IpReputationUpdate

router = APIRouter(prefix="/reputation", tags=["IP Reputation"])


@router.get("")
def list_reputation(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reputation:read")),
):
    items, total = item_service.list_ip_reputation(db, page, limit)
    return {
        "data": [IpReputationOut.model_validate(r).model_dump() for r in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("")
def upsert_reputation(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reputation:write")),
):
    row = item_service.upsert_ip_reputation(db, payload)
    item_service.audit(db, action="IP_UPSERTED", actor=current_user.username, resource=f"ip:{row.ip_address}")
    return IpReputationOut.model_validate(row).model_dump()


@router.get("/{ip_address}")
def get_reputation(
    ip_address: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = item_service.get_ip_reputation(db, ip_address)
    if not row:
        return {
            "id": None,
            "ip_address": ip_address,
            "threat_score": 0.0,
            "is_blocked": False,
            "category": None,
            "notes": "No reputation data available",
            "updated_at": None,
        }
    return IpReputationOut.model_validate(row).model_dump()


@router.post("/{ip_address}/block")
def block_ip(
    ip_address: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reputation:block")),
):
    row = item_service.upsert_ip_reputation(
        db,
        {"ip_address": ip_address, "is_blocked": True, "threat_score": 1.0, "category": "admin_blocked"},
    )
    item_service.audit(db, action="IP_BLOCKED", actor=current_user.username, resource=f"ip:{ip_address}")
    return IpReputationOut.model_validate(row).model_dump()


@router.post("/{ip_address}/unblock")
def unblock_ip(
    ip_address: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reputation:block")),
):
    row = item_service.upsert_ip_reputation(db, {"ip_address": ip_address, "is_blocked": False})
    item_service.audit(db, action="IP_UNBLOCKED", actor=current_user.username, resource=f"ip:{ip_address}")
    return IpReputationOut.model_validate(row).model_dump()
