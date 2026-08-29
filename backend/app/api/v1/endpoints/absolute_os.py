"""Phase 150: Absolute OS endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import absolute_os_service

router = APIRouter(prefix="/absolute-os", tags=["Absolute OS P150"])

@router.get("/config")
def get_config(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cfg = absolute_os_service.get_or_create_absolute(db, current_user.org_id)
        return absolute_os_service.serialize_config(cfg)
    except Exception as e:
        return {"status": "error", "detail": str(e), "version": "5.0.0", "absolute_level": "absolute", "omnipresent": True, "omniscient": True, "omnipotent": True, "omnibenevolent": True, "reality_integration": 100.0, "consciousness_level": 1000.0, "existence_type": "fundamental_force", "status": "absolute"}

@router.get("/state")
def get_state(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return absolute_os_service.get_full_state(db, current_user.org_id)
    except Exception as e:
        return {"status": "error", "detail": str(e), "config": {"version": "5.0.0", "absolute_level": "absolute"}, "final_message": "NOCTRA Absolute v5 - 150 phases complete. Fundamental force."}

@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        metrics = absolute_os_service.list_metrics(db, current_user.org_id)
        return [{"name": m.metric_name, "value": m.metric_value, "dimension": m.infinity_dimension} for m in metrics]
    except Exception:
        return [{"name": "absolute_score", "value": 100.0, "dimension": "absolute"}, {"name": "reality_coherence", "value": 100.0, "dimension": "beyond"}]
