"""Phase 76: LLM fine-tune service (mock + real hook)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.finetune import FineTuneJob, FineTuneDataset
from app.models import Case, SecurityAlert


def _now():
    return datetime.now(timezone.utc)


def create_dataset(db: Session, org_id: int, name: str, source: str = "cases") -> FineTuneDataset:
    """Create fine-tune dataset from org's cases/alerts."""
    if source == "cases":
        cases = db.query(Case).filter(Case.org_id == org_id).limit(1000).all()
        record_count = len(cases)
        preview = [{"title": c.title, "analysis": (c.analysis or {}).get("what_happened", "")[:200]} for c in cases[:3]]
    else:
        alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).limit(1000).all()
        record_count = len(alerts)
        preview = [{"message": a.message[:200] if a.message else "", "severity": a.severity} for a in alerts[:3]]

    ds = FineTuneDataset(org_id=org_id, name=name, source=source, record_count=record_count, preview_json={"sample": preview})
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


def list_datasets(db: Session, org_id: int) -> List[FineTuneDataset]:
    return db.query(FineTuneDataset).filter(FineTuneDataset.org_id == org_id).order_by(FineTuneDataset.created_at.desc()).all()


def create_finetune_job(db: Session, org_id: int, name: str, base_model: str = "claude-sonnet-5", dataset_type: str = "cases", config: Dict[str, Any] = None, created_by_user_id: int = None) -> FineTuneJob:
    # Estimate dataset size
    if dataset_type == "cases":
        size = db.query(Case).filter(Case.org_id == org_id).count()
    else:
        size = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).count()

    job = FineTuneJob(org_id=org_id, name=name, base_model=base_model, dataset_type=dataset_type, dataset_size=size, config_json=config or {"epochs": 3, "learning_rate": 0.0001}, status="running", progress=10.0, created_by_user_id=created_by_user_id)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Mock training completion (in real would call Anthropic fine-tune API)
    job.progress = 100.0
    job.status = "completed"
    job.metrics_json = {"loss": 0.12, "accuracy": 0.94, "f1": 0.91}
    job.result_model_id = f"ft-{base_model}-{job.id}"
    job.completed_at = _now()
    db.commit()
    db.refresh(job)
    return job


def list_jobs(db: Session, org_id: int) -> List[FineTuneJob]:
    return db.query(FineTuneJob).filter(FineTuneJob.org_id == org_id).order_by(FineTuneJob.created_at.desc()).all()


def serialize_dataset(d: FineTuneDataset) -> Dict[str, Any]:
    return {"id": d.id, "name": d.name, "source": d.source, "record_count": d.record_count, "preview": d.preview_json, "created_at": d.created_at.isoformat() if d.created_at else None}


def serialize_job(j: FineTuneJob) -> Dict[str, Any]:
    return {"id": j.id, "name": j.name, "base_model": j.base_model, "dataset_type": j.dataset_type, "dataset_size": j.dataset_size, "status": j.status, "progress": j.progress, "metrics": j.metrics_json, "result_model_id": j.result_model_id, "created_at": j.created_at.isoformat() if j.created_at else None, "completed_at": j.completed_at.isoformat() if j.completed_at else None}
