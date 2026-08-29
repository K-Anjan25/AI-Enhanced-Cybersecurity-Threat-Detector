"""Phase 89: Federated Learning service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.federated import FederatedJob, FederatedRound, OrgModelUpdate, FederatedModel
from app.models.org import Org


def _now():
    return datetime.now(timezone.utc)


def create_job(db: Session, name: str, description: str = None, model_type: str = "threat_detection", base_model: str = "noctra-ml-v1", config: Dict = None, total_rounds: int = 5, created_by_user_id: int = None) -> FederatedJob:
    job = FederatedJob(name=name, description=description, model_type=model_type, base_model=base_model, config_json=config or {"rounds": total_rounds, "min_orgs": 2, "aggregation": "fedavg", "dp_noise": 0.1}, total_rounds=total_rounds, status="pending", current_round=0)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_jobs(db: Session) -> List[FederatedJob]:
    return db.query(FederatedJob).order_by(FederatedJob.created_at.desc()).all()


def start_round(db: Session, job_id: int) -> FederatedRound:
    job = db.query(FederatedJob).filter(FederatedJob.id == job_id).first()
    if not job:
        raise ValueError("Job not found")
    if job.status == "completed":
        raise ValueError("Job already completed")

    job.status = "running"
    job.current_round += 1
    db.commit()

    rnd = FederatedRound(job_id=job_id, round_number=job.current_round, status="training", participating_orgs=job.participating_orgs or [])
    db.add(rnd)
    db.commit()
    db.refresh(rnd)

    # Simulate orgs participating: get all orgs
    orgs = db.query(Org).limit(5).all()
    participating = [o.id for o in orgs]
    job.participating_orgs = participating
    rnd.participating_orgs = participating
    db.commit()

    # Create pending updates for each org
    for org_id in participating:
        upd = OrgModelUpdate(job_id=job_id, round_id=rnd.id, org_id=org_id, status="pending", is_private=True)
        db.add(upd)
    db.commit()

    return rnd


def submit_update(db: Session, job_id: int, round_id: int, org_id: int, update: Dict[str, Any], metrics: Dict[str, Any]) -> OrgModelUpdate:
    upd = db.query(OrgModelUpdate).filter(OrgModelUpdate.job_id == job_id, OrgModelUpdate.round_id == round_id, OrgModelUpdate.org_id == org_id).first()
    if not upd:
        # Create if not exists
        upd = OrgModelUpdate(job_id=job_id, round_id=round_id, org_id=org_id, status="pending")
        db.add(upd)
    upd.update_json = update
    upd.metrics_json = metrics
    upd.status = "submitted"
    upd.submitted_at = _now()
    db.commit()
    db.refresh(upd)
    return upd


def aggregate_round(db: Session, round_id: int) -> FederatedRound:
    rnd = db.query(FederatedRound).filter(FederatedRound.id == round_id).first()
    if not rnd:
        raise ValueError("Round not found")

    updates = db.query(OrgModelUpdate).filter(OrgModelUpdate.round_id == round_id, OrgModelUpdate.status == "submitted").all()
    if not updates:
        # Mock updates if none submitted
        job = db.query(FederatedJob).filter(FederatedJob.id == rnd.job_id).first()
        for org_id in (job.participating_orgs or [1, 2, 3]):
            mock_upd = OrgModelUpdate(job_id=rnd.job_id, round_id=round_id, org_id=org_id, update_json={"weights_hash": f"hash_{org_id}_{round_id}", "sample_count": 100}, metrics_json={"accuracy": 0.85 + org_id*0.02, "f1": 0.8}, status="submitted", submitted_at=_now())
            db.add(mock_upd)
        db.commit()
        updates = db.query(OrgModelUpdate).filter(OrgModelUpdate.round_id == round_id, OrgModelUpdate.status == "submitted").all()

    # FedAvg aggregation mock
    avg_accuracy = sum(u.metrics_json.get("accuracy", 0.8) for u in updates) / max(1, len(updates))
    avg_f1 = sum(u.metrics_json.get("f1", 0.75) for u in updates) / max(1, len(updates))

    rnd.status = "completed"
    rnd.metrics_json = {"avg_accuracy": avg_accuracy, "avg_f1": avg_f1, "participating_orgs": len(updates), "aggregation": "fedavg"}
    rnd.completed_at = _now()
    db.commit()

    # Mark updates aggregated
    for u in updates:
        u.status = "aggregated"
    db.commit()

    # Create federated model for this round
    job = db.query(FederatedJob).filter(FederatedJob.id == rnd.job_id).first()
    model = FederatedModel(job_id=rnd.job_id, round_id=round_id, version=f"v{rnd.round_number}", model_id=f"fed-{job.id}-round-{rnd.round_number}", metrics_json=rnd.metrics_json, is_global=False)
    db.add(model)
    db.commit()

    # If last round, create global model and complete job
    if rnd.round_number >= job.total_rounds:
        global_model = FederatedModel(job_id=job.id, round_id=round_id, version=f"global-v{rnd.round_number}", model_id=f"fed-global-{job.id}", metrics_json={"accuracy": avg_accuracy, "f1": avg_f1, "rounds": job.total_rounds}, is_global=True)
        db.add(global_model)
        job.status = "completed"
        job.global_model_id = global_model.model_id
        job.global_metrics_json = {"accuracy": avg_accuracy, "f1": avg_f1}
        job.completed_at = _now()
        db.commit()
    else:
        job.status = "aggregating"
        db.commit()

    db.refresh(rnd)
    return rnd


def get_job_status(db: Session, job_id: int) -> Dict[str, Any]:
    job = db.query(FederatedJob).filter(FederatedJob.id == job_id).first()
    if not job:
        raise ValueError("Job not found")
    rounds = db.query(FederatedRound).filter(FederatedRound.job_id == job_id).order_by(FederatedRound.round_number.asc()).all()
    return {
        "job": {"id": job.id, "name": job.name, "status": job.status, "current_round": job.current_round, "total_rounds": job.total_rounds, "global_model_id": job.global_model_id, "global_metrics": job.global_metrics_json},
        "rounds": [{"round_number": r.round_number, "status": r.status, "metrics": r.metrics_json, "participating_orgs": r.participating_orgs} for r in rounds],
    }


def serialize_job(j: FederatedJob) -> Dict[str, Any]:
    return {"id": j.id, "name": j.name, "description": j.description, "model_type": j.model_type, "base_model": j.base_model, "config": j.config_json, "status": j.status, "current_round": j.current_round, "total_rounds": j.total_rounds, "global_model_id": j.global_model_id, "global_metrics": j.global_metrics_json, "participating_orgs": j.participating_orgs, "created_at": j.created_at.isoformat() if j.created_at else None, "completed_at": j.completed_at.isoformat() if j.completed_at else None}


def serialize_round(r: FederatedRound) -> Dict[str, Any]:
    return {"id": r.id, "job_id": r.job_id, "round_number": r.round_number, "status": r.status, "metrics": r.metrics_json, "participating_orgs": r.participating_orgs, "started_at": r.started_at.isoformat() if r.started_at else None, "completed_at": r.completed_at.isoformat() if r.completed_at else None}
