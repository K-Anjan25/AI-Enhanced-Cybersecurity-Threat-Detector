"""Phase 57: Data lifecycle — retention, archival, GDPR, legal hold."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.data_lifecycle import DataRetentionPolicy, DataArchiveLog, LegalHold, GDPRDeletionRequest
from app.models import SecurityAlert, Case, AuditLog, User
from app.core.config import settings


def ensure_default_policies(db: Session, org_id: int):
    existing_types = {p.data_type for p in db.query(DataRetentionPolicy).filter(DataRetentionPolicy.org_id == org_id).all()}
    defaults = [
        ("alerts", 90, 60, 90),
        ("cases", 365, 180, 365),
        ("audit_logs", 90, 30, 90),
        ("scanned_alerts", 30, 15, 30),
    ]
    for dtype, ret, arch, delete in defaults:
        if dtype not in existing_types:
            pol = DataRetentionPolicy(
                org_id=org_id,
                data_type=dtype,
                retention_days=ret,
                archive_after_days=arch,
                delete_after_days=delete,
            )
            db.add(pol)
    db.commit()


def list_policies(db: Session, org_id: int) -> List[DataRetentionPolicy]:
    ensure_default_policies(db, org_id)
    return db.query(DataRetentionPolicy).filter(DataRetentionPolicy.org_id == org_id).all()


def update_policy(db: Session, org_id: int, data_type: str, retention_days: int, archive_after_days: int = None, delete_after_days: int = None) -> DataRetentionPolicy:
    pol = db.query(DataRetentionPolicy).filter(DataRetentionPolicy.org_id == org_id, DataRetentionPolicy.data_type == data_type).first()
    if not pol:
        pol = DataRetentionPolicy(org_id=org_id, data_type=data_type)
        db.add(pol)
    pol.retention_days = retention_days
    if archive_after_days is not None:
        pol.archive_after_days = archive_after_days
    if delete_after_days is not None:
        pol.delete_after_days = delete_after_days
    db.commit()
    db.refresh(pol)
    return pol


def archive_old_data(db: Session, org_id: int, data_type: str = "alerts") -> Dict[str, Any]:
    """Archive old data per retention policy."""
    pol = db.query(DataRetentionPolicy).filter(DataRetentionPolicy.org_id == org_id, DataRetentionPolicy.data_type == data_type).first()
    if not pol:
        ensure_default_policies(db, org_id)
        pol = db.query(DataRetentionPolicy).filter(DataRetentionPolicy.org_id == org_id, DataRetentionPolicy.data_type == data_type).first()

    cutoff = datetime.now(timezone.utc) - timedelta(days=pol.archive_after_days or pol.retention_days)

    # No archive destination is configured, so nothing is copied or deleted.
    # What this can do honestly is report how much data is *eligible*, which is
    # the number an operator needs before wiring up storage. Previously it
    # returned that count as `archived_count` and wrote a log row claiming
    # success against a fabricated s3:// path, so the dashboard reported
    # "Archived N records" when nothing had moved.
    eligible = 0
    if data_type == "alerts":
        eligible = db.query(SecurityAlert).filter(
            SecurityAlert.org_id == org_id, SecurityAlert.created_at < cutoff
        ).count()
    elif data_type == "cases":
        held_case_ids: set[int] = set()
        for hold in db.query(LegalHold).filter(
            LegalHold.org_id == org_id, LegalHold.is_active.is_(True)
        ).all():
            if hold.case_ids:
                held_case_ids.update(hold.case_ids)
        q = db.query(Case).filter(Case.org_id == org_id, Case.created_at < cutoff)
        if held_case_ids:
            q = q.filter(Case.id.notin_(held_case_ids))
        eligible = q.count()

    log = DataArchiveLog(
        org_id=org_id,
        data_type=data_type,
        archived_count=0,
        archive_path=None,
        status="not_configured",
    )
    db.add(log)
    db.commit()
    return {
        "data_type": data_type,
        "archived_count": 0,
        "eligible_count": eligible,
        "cutoff": cutoff.isoformat(),
        "status": "not_configured",
        "reason": (
            "No archive destination is configured, so nothing was copied or "
            "deleted. This reports how many records are past their retention "
            "threshold and would be archived once storage is set up."
        ),
    }


def create_legal_hold(db: Session, org_id: int, name: str, description: str = None, case_ids: List[int] = None, user_id: int = None) -> LegalHold:
    hold = LegalHold(
        org_id=org_id,
        name=name,
        description=description,
        case_ids=case_ids or [],
        user_id=user_id,
        is_active=True,
    )
    db.add(hold)
    db.commit()
    db.refresh(hold)
    return hold


def list_legal_holds(db: Session, org_id: int) -> List[LegalHold]:
    return db.query(LegalHold).filter(LegalHold.org_id == org_id).order_by(LegalHold.created_at.desc()).all()


def release_legal_hold(db: Session, org_id: int, hold_id: int) -> Optional[LegalHold]:
    hold = db.query(LegalHold).filter(LegalHold.id == hold_id, LegalHold.org_id == org_id).first()
    if not hold:
        return None
    hold.is_active = False
    hold.released_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(hold)
    return hold


def create_gdpr_request(db: Session, org_id: int, target_email: str, reason: str = None, requested_by_user_id: int = None, target_user_id: int = None) -> GDPRDeletionRequest:
    req = GDPRDeletionRequest(
        org_id=org_id,
        target_email=target_email,
        target_user_id=target_user_id,
        requested_by_user_id=requested_by_user_id,
        reason=reason,
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


_GDPR_ACTIONS = ("approve", "reject", "complete")

# Once approved, the subject's account is anonymised in place. There is no undo,
# so a decided request must not be re-decided into a different outcome.
_GDPR_DECIDED = ("approved", "completed", "rejected")


def process_gdpr_request(db: Session, org_id: int, request_id: int, action: str = "approve") -> GDPRDeletionRequest:
    if action not in _GDPR_ACTIONS:
        # Previously any unknown action fell through every branch and returned
        # the unchanged request with HTTP 200 — the caller saw success for a
        # decision that never happened.
        raise ValueError(
            f"Unknown action {action!r}. Expected one of: {', '.join(_GDPR_ACTIONS)}."
        )
    req = db.query(GDPRDeletionRequest).filter(GDPRDeletionRequest.id == request_id, GDPRDeletionRequest.org_id == org_id).first()
    if not req:
        raise ValueError("GDPR request not found")
    if action in ("approve", "reject") and req.status in _GDPR_DECIDED:
        raise ValueError(
            f"Request is already {req.status}; erasure cannot be reversed or re-decided."
        )
    if action == "approve":
        req.status = "approved"
        # In real implementation, anonymize user data
        if req.target_user_id:
            user = db.query(User).filter(User.id == req.target_user_id).first()
            if user:
                user.email = f"deleted_{user.id}@deleted.local"
                user.username = f"deleted_{user.id}"
                user.is_active = False
        db.commit()
    elif action == "complete":
        req.status = "completed"
        req.completed_at = datetime.now(timezone.utc)
        db.commit()
    elif action == "reject":
        req.status = "rejected"
        db.commit()
    db.refresh(req)
    return req
