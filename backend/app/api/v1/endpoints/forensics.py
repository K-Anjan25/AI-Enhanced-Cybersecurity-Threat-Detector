"""Phase 68: Forensics endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import forensics_service

router = APIRouter(prefix="/forensics", tags=["forensics"])

class ForensicCaseIn(BaseModel):
    case_id: int
    title: str
    description: Optional[str] = None

class ArtifactIn(BaseModel):
    forensic_case_id: int
    name: str
    artifact_type: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None

class TimelineIn(BaseModel):
    forensic_case_id: int
    timestamp: datetime
    event_type: str
    description: str
    artifact_id: Optional[int] = None
    source: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

@router.get("/cases")
def list_cases(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        cases = forensics_service.list_forensic_cases(db, current_user.org_id)
        return [forensics_service.serialize_case(c) for c in cases]
    except Exception:
        return []

@router.post("/cases")
def create_case(payload: ForensicCaseIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        fc = forensics_service.create_forensic_case(db, current_user.org_id, payload.case_id, payload.title, payload.description, created_by_user_id=current_user.id)
        return forensics_service.serialize_case(fc)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/artifacts")
def list_artifacts(forensic_case_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        arts = forensics_service.list_artifacts(db, current_user.org_id, forensic_case_id=forensic_case_id)
        return [forensics_service.serialize_artifact(a) for a in arts]
    except Exception:
        return []

@router.post("/artifacts")
def add_artifact(payload: ArtifactIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        art = forensics_service.add_artifact(db, current_user.org_id, payload.forensic_case_id, payload.name, payload.artifact_type, payload.file_path, payload.file_size, collected_by_user_id=current_user.id)
        return forensics_service.serialize_artifact(art)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/timeline/{forensic_case_id}")
def get_timeline(forensic_case_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        evs = forensics_service.get_timeline(db, current_user.org_id, forensic_case_id)
        return [forensics_service.serialize_event(ev) for ev in evs]
    except Exception:
        return []

@router.post("/timeline")
def add_timeline(payload: TimelineIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ev = forensics_service.add_timeline_event(db, current_user.org_id, payload.forensic_case_id, payload.timestamp, payload.event_type, payload.description, payload.artifact_id, payload.source, payload.details)
        return forensics_service.serialize_event(ev)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
