"""Phase 52: Sigma rules + DSL endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import sigma_service

router = APIRouter(prefix="/sigma", tags=["Sigma Rules (Phase 52)"])


class SigmaRuleCreate(BaseModel):
    title: str
    rule_yaml: str
    description: Optional[str] = None
    level: str = Field("medium")
    tags: Optional[List[str]] = None


class SigmaRuleUpdate(BaseModel):
    rule_yaml: Optional[str] = None
    title: Optional[str] = None
    level: Optional[str] = None
    is_active: Optional[bool] = None
    change_notes: Optional[str] = None


class DSLRuleCreate(BaseModel):
    name: str
    dsl_expression: str
    description: Optional[str] = None
    severity: str = "MEDIUM"


@router.get("/rules")
def list_sigma(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:read")),
):
    rows = sigma_service.list_sigma_rules(db, org_id=current_user.org_id)
    return [sigma_service.serialize_sigma_rule(r) for r in rows]


@router.post("/rules", status_code=201)
def create_sigma(
    payload: SigmaRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:write")),
):
    try:
        rule = sigma_service.create_sigma_rule(
            db,
            org_id=current_user.org_id,
            title=payload.title,
            rule_yaml=payload.rule_yaml,
            description=payload.description,
            level=payload.level,
            tags=payload.tags,
            created_by_user_id=current_user.id,
        )
        return sigma_service.serialize_sigma_rule(rule)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/rules/{rule_id}")
def get_sigma(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:read")),
):
    rule = sigma_service.get_sigma_rule(db, org_id=current_user.org_id, rule_id=rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Sigma rule not found")
    return sigma_service.serialize_sigma_rule(rule)


@router.put("/rules/{rule_id}")
def update_sigma(
    rule_id: int,
    payload: SigmaRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:write")),
):
    try:
        rule = sigma_service.update_sigma_rule(
            db,
            org_id=current_user.org_id,
            rule_id=rule_id,
            rule_yaml=payload.rule_yaml,
            title=payload.title,
            level=payload.level,
            is_active=payload.is_active,
            change_notes=payload.change_notes,
            actor_user_id=current_user.id,
        )
        return sigma_service.serialize_sigma_rule(rule)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/rules/{rule_id}")
def delete_sigma(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:delete")),
):
    ok = sigma_service.delete_sigma_rule(db, org_id=current_user.org_id, rule_id=rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Sigma rule not found")
    return {"status": "deleted"}


@router.post("/rules/{rule_id}/test")
def test_sigma(
    rule_id: int,
    alert: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:read")),
):
    rule = sigma_service.get_sigma_rule(db, org_id=current_user.org_id, rule_id=rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Sigma rule not found")
    matched = sigma_service.evaluate_sigma_rule(rule, alert)
    return {"rule_id": rule_id, "matched": matched, "alert": alert}


# DSL

@router.get("/dsl")
def list_dsl(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:read")),
):
    from app.models.sigma_rule import DetectionDSLRule

    rows = db.query(DetectionDSLRule).filter(DetectionDSLRule.org_id == current_user.org_id).all()
    return [sigma_service.serialize_dsl_rule(r) for r in rows]


@router.post("/dsl", status_code=201)
def create_dsl(
    payload: DSLRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:write")),
):
    try:
        rule = sigma_service.create_dsl_rule(
            db,
            org_id=current_user.org_id,
            name=payload.name,
            dsl_expression=payload.dsl_expression,
            severity=payload.severity,
            created_by_user_id=current_user.id,
        )
        return sigma_service.serialize_dsl_rule(rule)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/dsl/{dsl_id}/test")
def test_dsl(
    dsl_id: int,
    alert: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("rules:read")),
):
    from app.models.sigma_rule import DetectionDSLRule

    rule = db.query(DetectionDSLRule).filter(DetectionDSLRule.id == dsl_id, DetectionDSLRule.org_id == current_user.org_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="DSL rule not found")
    matched = sigma_service.evaluate_dsl_rule(rule, alert)
    return {"dsl_id": dsl_id, "matched": matched}
