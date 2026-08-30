"""Phase 84: SOC TV Wall endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import soc_tv_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/soc-tv", tags=["SOC TV Wall (Phase 84)"])

class WallConfigIn(BaseModel):
    name: str
    widgets: List[Dict[str, Any]]
    is_default: bool = False

@router.get("/configs")
def list_configs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        soc_tv_service.seed_default_wall(db, current_user.org_id)
        configs = soc_tv_service.list_wall_configs(db, current_user.org_id)
        return [soc_tv_service.serialize_config(c) for c in configs]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/configs")
def create_config(payload: WallConfigIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cfg = soc_tv_service.create_wall_config(db, current_user.org_id, payload.name, payload.widgets, payload.is_default, created_by_user_id=current_user.id)
        return soc_tv_service.serialize_config(cfg)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/live")
def get_live_metrics(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        return soc_tv_service.get_live_metrics(db, current_user.org_id)
    except Exception as e:
        return {"status": "error", "detail": str(e), "total_alerts": 0, "open_cases": 0, "recent_alerts": []}

@router.get("/stream")
def stream_metrics(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    """For TV wall, returns live metrics - frontend polls every 5s or uses SSE."""
    try:
        return soc_tv_service.get_live_metrics(db, current_user.org_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e