"""Phase 69: TIP - STIX 2.1, TAXII, MISP."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.tip import IntelFeed, STIXObject, MISPEvent


def _now():
    return datetime.now(timezone.utc)


def list_feeds(db: Session, org_id: int) -> List[IntelFeed]:
    return db.query(IntelFeed).filter(IntelFeed.org_id == org_id).all()


def create_feed(db: Session, org_id: int, name: str, feed_type: str, url: str = None, config: Dict[str, Any] = None) -> IntelFeed:
    feed = IntelFeed(org_id=org_id, name=name, feed_type=feed_type, url=url, config_json=config or {})
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return feed


def ingest_stix_bundle(db: Session, org_id: int, bundle: Dict[str, Any], feed_id: int = None) -> List[STIXObject]:
    """Ingest STIX 2.1 bundle (objects list)."""
    objects = bundle.get("objects", []) if isinstance(bundle, dict) else []
    created = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        stix_id = obj.get("id") or f"{obj.get('type', 'indicator')}--{uuid.uuid4()}"
        stix_type = obj.get("type", "indicator")
        pattern = obj.get("pattern")
        created_at = obj.get("created")
        try:
            valid_from = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else _now()
        except Exception:
            valid_from = _now()

        stix_obj = STIXObject(
            org_id=org_id,
            feed_id=feed_id,
            stix_id=stix_id,
            stix_type=stix_type,
            spec_version="2.1",
            pattern=pattern,
            valid_from=valid_from,
            stix_json=obj,
        )
        db.add(stix_obj)
        created.append(stix_obj)
    if created:
        db.commit()
        for o in created:
            db.refresh(o)
    return created


def list_stix(db: Session, org_id: int, stix_type: str = None, limit: int = 100) -> List[STIXObject]:
    q = db.query(STIXObject).filter(STIXObject.org_id == org_id)
    if stix_type:
        q = q.filter(STIXObject.stix_type == stix_type)
    return q.order_by(STIXObject.created_at.desc()).limit(limit).all()


def export_stix_bundle(db: Session, org_id: int, stix_ids: List[str] = None) -> Dict[str, Any]:
    """Export STIX bundle."""
    q = db.query(STIXObject).filter(STIXObject.org_id == org_id)
    if stix_ids:
        q = q.filter(STIXObject.stix_id.in_(stix_ids))
    objs = q.limit(200).all()
    bundle = {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid4()}",
        "objects": [o.stix_json for o in objs if o.stix_json],
    }
    return bundle


def create_misp_event(db: Session, org_id: int, info: str, threat_level: int = 2, analysis: int = 0, distribution: int = 0, attributes: List[Dict[str, Any]] = None) -> MISPEvent:
    ev = MISPEvent(
        org_id=org_id,
        misp_id=str(uuid.uuid4()),
        info=info,
        threat_level=threat_level,
        analysis=analysis,
        distribution=distribution,
        attributes_json=attributes or [],
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def list_misp_events(db: Session, org_id: int, limit: int = 50) -> List[MISPEvent]:
    return db.query(MISPEvent).filter(MISPEvent.org_id == org_id).order_by(MISPEvent.created_at.desc()).limit(limit).all()


def serialize_stix(s: STIXObject) -> Dict[str, Any]:
    return {"id": s.id, "stix_id": s.stix_id, "stix_type": s.stix_type, "pattern": s.pattern, "valid_from": s.valid_from.isoformat() if s.valid_from else None, "created_at": s.created_at.isoformat() if s.created_at else None}


def serialize_misp(e: MISPEvent) -> Dict[str, Any]:
    return {"id": e.id, "misp_id": e.misp_id, "info": e.info, "threat_level": e.threat_level, "analysis": e.analysis, "attribute_count": len(e.attributes_json or []), "created_at": e.created_at.isoformat() if e.created_at else None}
