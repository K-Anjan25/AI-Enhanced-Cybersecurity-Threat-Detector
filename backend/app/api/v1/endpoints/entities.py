from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import entity_graph

router = APIRouter(prefix="/entities", tags=["Entity Graph"])


@router.get("")
def list_entities(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    entity_type: str | None = Query(None, pattern="^(ip|domain|hash|email|file)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List extracted threat entities, highest risk first."""
    items, total = entity_graph.list_entities(
        db, page=page, limit=limit, entity_type=entity_type, org_id=current_user.org_id
    )
    return {
        "data": [entity_graph.serialize_entity(e) for e in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{entity_id}")
def get_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entity = entity_graph.get_entity(db, entity_id, org_id=current_user.org_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity_graph.serialize_entity(entity)


@router.get("/{entity_id}/graph")
def get_graph(
    entity_id: int,
    depth: int = Query(1, ge=1, le=4),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the attack-graph neighborhood around an entity (adjacency list)."""
    return entity_graph.entity_graph(db, entity_id, depth=depth, org_id=current_user.org_id)


@router.post("/{entity_id}/reputation")
def update_entity_reputation(
    entity_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reputation:write")),
):
    """Manually adjust an entity's risk score (analyst override)."""
    entity = entity_graph.get_entity(db, entity_id, org_id=current_user.org_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    if "risk_score" in payload:
        entity.risk_score = float(payload["risk_score"])
    db.commit()
    db.refresh(entity)
    return entity_graph.serialize_entity(entity)
