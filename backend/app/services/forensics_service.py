"""Phase 68: Forensics - cases, artifacts, timeline."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.forensics import ForensicCase, ForensicArtifact, TimelineEvent


def _now():
    return datetime.now(timezone.utc)


def create_forensic_case(db: Session, org_id: int, case_id: int, title: str, description: str = None, created_by_user_id: int = None) -> ForensicCase:
    fc = ForensicCase(org_id=org_id, case_id=case_id, title=title, description=description, created_by_user_id=created_by_user_id)
    db.add(fc)
    db.commit()
    db.refresh(fc)
    return fc


def list_forensic_cases(db: Session, org_id: int) -> List[ForensicCase]:
    return db.query(ForensicCase).filter(ForensicCase.org_id == org_id).order_by(ForensicCase.created_at.desc()).all()


def add_artifact(db: Session, org_id: int, forensic_case_id: int, name: str, artifact_type: str, file_path: str = None, file_size: int = None, content: bytes = None, collected_by_user_id: int = None) -> ForensicArtifact:
    sha256 = None
    if content:
        sha256 = hashlib.sha256(content).hexdigest()
    # map to existing model fields
    artifact = ForensicArtifact(
        org_id=org_id,
        forensic_case_id=forensic_case_id,
        name=name,
        artifact_type=artifact_type,
        hash_sha256=sha256,
        size_bytes=file_size,
        metadata_json={"file_path": file_path, "collected_by_user_id": collected_by_user_id, "chain_of_custody": [{"action": "collected", "by_user_id": collected_by_user_id, "at": _now().isoformat()}]},
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def list_artifacts(db: Session, org_id: int, forensic_case_id: int = None) -> List[ForensicArtifact]:
    q = db.query(ForensicArtifact).filter(ForensicArtifact.org_id == org_id)
    if forensic_case_id:
        q = q.filter(ForensicArtifact.forensic_case_id == forensic_case_id)
    return q.order_by(ForensicArtifact.created_at.desc()).all()


def add_timeline_event(db: Session, org_id: int, forensic_case_id: int, timestamp: datetime, event_type: str, description: str, artifact_id: int = None, source: str = None, details: Dict[str, Any] = None) -> TimelineEvent:
    ev = TimelineEvent(
        org_id=org_id,
        forensic_case_id=forensic_case_id,
        source_artifact_id=artifact_id,
        timestamp=timestamp,
        event_type=event_type,
        description=description,
        extra={"source": source, "details": details or {}},
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def get_timeline(db: Session, org_id: int, forensic_case_id: int) -> List[TimelineEvent]:
    return db.query(TimelineEvent).filter(TimelineEvent.org_id == org_id, TimelineEvent.forensic_case_id == forensic_case_id).order_by(TimelineEvent.timestamp.asc()).all()


def serialize_case(fc: ForensicCase) -> Dict[str, Any]:
    return {"id": fc.id, "case_id": fc.case_id, "title": fc.title, "description": fc.description, "status": fc.status, "evidence_hash": fc.evidence_hash, "created_at": fc.created_at.isoformat() if fc.created_at else None}


def serialize_artifact(a: ForensicArtifact) -> Dict[str, Any]:
    return {"id": a.id, "forensic_case_id": a.forensic_case_id, "name": a.name, "artifact_type": a.artifact_type, "hash_sha256": a.hash_sha256, "file_size": a.size_bytes, "collected_at": a.created_at.isoformat() if a.created_at else None, "metadata": a.metadata_json}


def serialize_event(e: TimelineEvent) -> Dict[str, Any]:
    return {"id": e.id, "timestamp": e.timestamp.isoformat() if e.timestamp else None, "event_type": e.event_type, "description": e.description, "extra": e.extra}
