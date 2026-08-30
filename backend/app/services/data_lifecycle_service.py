"""Phase 57: Data lifecycle — retention, archival, GDPR, legal hold."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.data_lifecycle import DataRetentionPolicy, DataArchiveLog, LegalHold, GDPRDeletionRequest
from app.models import SecurityAlert, Case, AuditLog, User
from app.core.config import settings
from app.services import archive_store


# One run copies at most this many rows, so a first archive on a large
# tenant cannot build a multi-gigabyte payload in memory.
_ARCHIVE_BATCH = 5000


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

    # Rows past their threshold are written to the configured destination
    # (object storage, or local disk when none is set). Nothing is deleted:
    # copying data out and removing it are separate decisions, and deletion
    # without a verified copy is how retention policies lose evidence.
    eligible = 0
    rows_to_archive = []
    if data_type == "alerts":
        rows_to_archive = db.query(SecurityAlert).filter(
            SecurityAlert.org_id == org_id, SecurityAlert.created_at < cutoff
        ).limit(_ARCHIVE_BATCH).all()
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
        rows_to_archive = q.limit(_ARCHIVE_BATCH).all()

    if not rows_to_archive:
        log = DataArchiveLog(
            org_id=org_id, data_type=data_type, archived_count=0,
            archive_path=None, status="nothing_eligible",
        )
        db.add(log)
        db.commit()
        return {
            "data_type": data_type,
            "archived_count": 0,
            "eligible_count": 0,
            "cutoff": cutoff.isoformat(),
            "status": "nothing_eligible",
            "destination": archive_store.describe_destination()["kind"],
            "reason": "No records are past their retention threshold.",
        }

    payload = json.dumps(
        [_serialize_for_archive(r) for r in rows_to_archive], default=str
    ).encode("utf-8")
    result = archive_store.store(
        org_id=org_id,
        category=f"retention/{data_type}",
        name=f"{cutoff.date()}.json",
        payload=payload,
        content_type="application/json",
    )

    written = len(rows_to_archive) if result["stored"] else 0
    log = DataArchiveLog(
        org_id=org_id,
        data_type=data_type,
        archived_count=written,
        archive_path=result["path"],
        status="success" if result["stored"] else "failed",
    )
    db.add(log)
    db.commit()

    return {
        "data_type": data_type,
        "archived_count": written,
        "eligible_count": eligible,
        "cutoff": cutoff.isoformat(),
        "status": "archived" if result["stored"] else "failed",
        "destination": result["destination"],
        "path": result["path"],
        "error": result["error"],
        "truncated": eligible > written and result["stored"],
        "reason": (
            None if result["stored"]
            else f"Nothing was archived: {result['error']}"
        ),
    }


def _serialize_for_archive(row) -> Dict[str, Any]:
    """Column values only — enough to reconstitute the record later."""
    return {
        c.name: getattr(row, c.name) for c in row.__table__.columns
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
    # with_for_update takes a row lock so two callers cannot both read
    # "pending" and both decide. Postgres blocks the second reader until the
    # first commits; SQLite ignores the hint, which is why the guarded UPDATE
    # below is kept as well.
    req = (
        db.query(GDPRDeletionRequest)
        .filter(GDPRDeletionRequest.id == request_id, GDPRDeletionRequest.org_id == org_id)
        .with_for_update()
        .first()
    )
    if not req:
        raise ValueError("GDPR request not found")
    if action in ("approve", "reject"):
        # The conditional UPDATE below is the real guard; this early check only
        # gives a clearer message in the common, uncontended case.
        if req.status in _GDPR_DECIDED:
            raise ValueError(
                f"Request is already {req.status}; erasure cannot be reversed or re-decided."
            )

        # Settle the request with a conditional UPDATE so two simultaneous
        # decisions cannot both pass the status check above. Approving
        # anonymises an account, so it has to happen at most once.
        settled = (
            db.query(GDPRDeletionRequest)
            .filter(
                GDPRDeletionRequest.id == request_id,
                GDPRDeletionRequest.org_id == org_id,
                GDPRDeletionRequest.status.notin_(_GDPR_DECIDED),
            )
            .update(
                {GDPRDeletionRequest.status: "approved" if action == "approve" else "rejected"},
                synchronize_session="fetch",
            )
        )
        # Commit immediately so the claim is visible to other transactions.
        # Without this the guard is evaluated against a snapshot and several
        # callers each believe they won.
        db.commit()
        if not settled:
            # Someone else settled it between our read and the UPDATE.
            db.expire(req)
            current = db.query(GDPRDeletionRequest.status).filter(
                GDPRDeletionRequest.id == request_id
            ).scalar()
            raise ValueError(
                f"Request is already {current}; erasure cannot be reversed or re-decided."
            )
        # We won the claim, so the row now carries our decision. Set it on the
        # in-session object directly rather than refreshing: a refresh re-reads
        # through a connection another thread may be mid-commit on, which made
        # the winner intermittently observe someone else's status and refuse
        # its own successful decision.
        req.status = "approved" if action == "approve" else "rejected"
    if action == "approve":
        # Status was set by the claiming UPDATE above.
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
