"""Phase 69: TIP endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import tip_service

router = APIRouter(prefix="/tip", tags=["tip"])

class FeedIn(BaseModel):
    name: str
    feed_type: str
    url: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class STIXBundleIn(BaseModel):
    bundle: Dict[str, Any]
    feed_id: Optional[int] = None

class MISPEventIn(BaseModel):
    info: str
    threat_level: int = 2
    analysis: int = 0
    distribution: int = 0
    attributes: Optional[List[Dict[str, Any]]] = None

@router.get("/feeds")
def list_feeds(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        feeds = tip_service.list_feeds(db, current_user.org_id)
        return [{"id": f.id, "name": f.name, "feed_type": f.feed_type, "url": f.url, "status": f.status} for f in feeds]
    except Exception:
        return []

@router.post("/feeds")
def create_feed(payload: FeedIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        feed = tip_service.create_feed(db, current_user.org_id, payload.name, payload.feed_type, payload.url, payload.config)
        return {"id": feed.id, "name": feed.name, "feed_type": feed.feed_type}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/stix/ingest")
def ingest_stix(payload: STIXBundleIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        objs = tip_service.ingest_stix_bundle(db, current_user.org_id, payload.bundle, payload.feed_id)
        return [tip_service.serialize_stix(o) for o in objs]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/stix")
def list_stix(stix_type: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        objs = tip_service.list_stix(db, current_user.org_id, stix_type=stix_type, limit=limit)
        return [tip_service.serialize_stix(o) for o in objs]
    except Exception:
        return []

@router.get("/stix/export")
def export_stix(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        bundle = tip_service.export_stix_bundle(db, current_user.org_id)
        return bundle
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/misp")
def list_misp(limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        evs = tip_service.list_misp_events(db, current_user.org_id, limit=limit)
        return [tip_service.serialize_misp(ev) for ev in evs]
    except Exception:
        return []

@router.post("/misp")
def create_misp(payload: MISPEventIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ev = tip_service.create_misp_event(db, current_user.org_id, payload.info, payload.threat_level, payload.analysis, payload.distribution, payload.attributes)
        return tip_service.serialize_misp(ev)
    except Exception as e:
        return {"status": "error", "detail": str(e)}
