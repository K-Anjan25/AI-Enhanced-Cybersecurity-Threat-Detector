"""Phase 78-79: Purple team endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import purple_team_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/purple-team", tags=["PurpleTeam (Phase 78-79)"])

class ExerciseIn(BaseModel):
    name: str
    description: Optional[str] = None
    mitre_tactic: Optional[str] = None
    mitre_technique_id: Optional[str] = None
    exercise_type: str = "atomic"
    steps: Optional[List[Dict[str, Any]]] = None

@router.get("/exercises")
def list_exercises(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        purple_team_service.seed_exercises(db, current_user.org_id)
        exs = purple_team_service.list_exercises(db, current_user.org_id)
        return [purple_team_service.serialize_exercise(e) for e in exs]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/exercises")
def create_exercise(payload: ExerciseIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ex = purple_team_service.create_exercise(db, current_user.org_id, payload.name, payload.description, payload.mitre_tactic, payload.mitre_technique_id, payload.exercise_type, payload.steps, created_by_user_id=current_user.id)
        return purple_team_service.serialize_exercise(ex)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/exercises/{exercise_id}/run")
def run_exercise(exercise_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ex = purple_team_service.run_exercise(db, current_user.org_id, exercise_id)
        return purple_team_service.serialize_exercise(ex)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/findings")
def list_findings(exercise_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        findings = purple_team_service.list_findings(db, current_user.org_id, exercise_id=exercise_id)
        return [purple_team_service.serialize_finding(f) for f in findings]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e