from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.abac import require_permission, require_any_permission
from app.api.v1.endpoints.auth import get_current_user
from app.models import User
from app.services import item_service
from app.schemas.item import DetectionRuleCreate, DetectionRuleUpdate, DetectionRuleOut

router = APIRouter(prefix="/rules", tags=["Detection Rules"])


@router.get("")
def list_rules(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = item_service.list_rules(db, page, limit)
    return {
        "data": [DetectionRuleOut.model_validate(r).model_dump() for r in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("", status_code=201)
def create_rule(
    payload: DetectionRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:write")),
):
    rule = item_service.create_rule(db, payload.model_dump())
    item_service.audit(db, action="RULE_CREATED", actor=current_user.username, resource=f"rule:{rule.id}", details=rule.name)
    return DetectionRuleOut.model_validate(rule).model_dump()


@router.get("/{rule_id}")
def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = item_service.get_rule(db, rule_id)
    return DetectionRuleOut.model_validate(rule).model_dump()


@router.put("/{rule_id}")
def update_rule(
    rule_id: int,
    payload: DetectionRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:write")),
):
    rule = item_service.update_rule(db, rule_id, payload.model_dump(exclude_unset=True))
    item_service.audit(db, action="RULE_UPDATED", actor=current_user.username, resource=f"rule:{rule.id}", details=rule.name)
    return DetectionRuleOut.model_validate(rule).model_dump()


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:delete")),
):
    item_service.delete_rule(db, rule_id)
    item_service.audit(db, action="RULE_DELETED", actor=current_user.username, resource=f"rule:{rule_id}")
    return {"success": True}
