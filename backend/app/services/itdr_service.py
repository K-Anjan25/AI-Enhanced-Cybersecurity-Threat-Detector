"""Phase 64: ITDR/UEBA service."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import math

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.itdr import UserBehaviorProfile, IdentityThreat, RiskySignIn
from app.models import AuditLog, User, SecurityAlert
from app.core.config import settings


def _now():
    return datetime.now(timezone.utc)


def build_baseline(db: Session, org_id: int, user_id: int) -> UserBehaviorProfile:
    """Build baseline from last 30 days of audit logs + alerts for user."""
    days = getattr(settings, "UEBA_BASELINE_DAYS", 30)
    since = _now() - timedelta(days=days)

    logs = db.query(AuditLog).filter(AuditLog.created_at >= since).all()
    # Filter by actor if possible (actor is username)
    user = db.query(User).filter(User.id == user_id, User.org_id == org_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    user_logs = [l for l in logs if user.username in (l.actor or "")]
    login_count = len([l for l in user_logs if "LOGIN" in (l.action or "").upper()])

    # Usual hours
    hours = []
    for l in user_logs:
        if l.created_at:
            hours.append(l.created_at.hour)
    usual_hours = sorted(set(hours))[:5] if hours else [9, 10, 11, 14, 15]

    # Usual IPs from SecurityAlert
    ips = db.query(SecurityAlert.source_ip).filter(SecurityAlert.org_id == org_id, SecurityAlert.source_ip.isnot(None)).limit(20).all()
    usual_ips = list({ip[0] for ip in ips if ip[0]})[:5]

    baseline = {
        "avg_logins_per_day": round(login_count / max(1, days), 2),
        "usual_hours": usual_hours,
        "usual_ips": usual_ips,
        "usual_locations": ["US"],  # would need GeoIP
        "devices": ["chrome", "firefox"],
    }

    profile = db.query(UserBehaviorProfile).filter(UserBehaviorProfile.org_id == org_id, UserBehaviorProfile.user_id == user_id).first()
    if not profile:
        profile = UserBehaviorProfile(org_id=org_id, user_id=user_id, baseline_json=baseline, login_count=login_count, last_login_at=_now())
        db.add(profile)
    else:
        profile.baseline_json = baseline
        profile.login_count = login_count
        profile.updated_at = _now()
    db.commit()
    db.refresh(profile)
    return profile


def detect_impossible_travel(db: Session, org_id: int, user_id: int, new_ip: str, new_location: str, previous_location: str, time_delta_seconds: int) -> Optional[IdentityThreat]:
    """Detect impossible travel: same user in distant locations within short time."""
    if not new_location or not previous_location:
        return None
    if new_location == previous_location:
        return None
    # If time delta < 1 hour and locations different continents, flag
    if time_delta_seconds < 3600 and new_location != previous_location:
        threat = IdentityThreat(
            org_id=org_id,
            user_id=user_id,
            threat_type="impossible_travel",
            severity="HIGH",
            description=f"User {user_id} logged in from {previous_location} then {new_location} within {time_delta_seconds}s (IP {new_ip})",
            evidence_json={"new_ip": new_ip, "new_location": new_location, "previous_location": previous_location, "time_delta_seconds": time_delta_seconds},
        )
        db.add(threat)
        db.commit()
        db.refresh(threat)
        return threat
    return None


def detect_brute_force(db: Session, org_id: int, src_ip: str, threshold: int = 5) -> Optional[IdentityThreat]:
    """Detect brute force: many failed logins from same IP in last hour."""
    since = _now() - timedelta(hours=1)
    failed = db.query(AuditLog).filter(AuditLog.action.ilike("%LOGIN_FAILED%"), AuditLog.created_at >= since).all()
    # Filter by IP in details if present
    ip_failed = [l for l in failed if src_ip in (l.details or "")]
    if len(ip_failed) >= threshold:
        threat = IdentityThreat(
            org_id=org_id,
            threat_type="brute_force",
            severity="HIGH",
            description=f"Brute force detected from {src_ip}: {len(ip_failed)} failed logins in last hour",
            evidence_json={"src_ip": src_ip, "failed_count": len(ip_failed)},
        )
        db.add(threat)
        db.commit()
        db.refresh(threat)
        return threat
    return None


def list_threats(db: Session, org_id: int, status: str = None, limit: int = 50) -> List[IdentityThreat]:
    q = db.query(IdentityThreat).filter(IdentityThreat.org_id == org_id)
    if status:
        q = q.filter(IdentityThreat.status == status)
    return q.order_by(IdentityThreat.created_at.desc()).limit(limit).all()


def list_risky_signins(db: Session, org_id: int, limit: int = 50) -> List[RiskySignIn]:
    return db.query(RiskySignIn).filter(RiskySignIn.org_id == org_id).order_by(RiskySignIn.created_at.desc()).limit(limit).all()


def serialize_profile(p: UserBehaviorProfile) -> Dict[str, Any]:
    return {"id": p.id, "user_id": p.user_id, "baseline": p.baseline_json, "login_count": p.login_count, "risk_score": p.risk_score, "last_login_at": p.last_login_at.isoformat() if p.last_login_at else None, "updated_at": p.updated_at.isoformat() if p.updated_at else None}


def serialize_threat(t: IdentityThreat) -> Dict[str, Any]:
    return {"id": t.id, "user_id": t.user_id, "threat_type": t.threat_type, "severity": t.severity, "description": t.description, "evidence": t.evidence_json, "status": t.status, "created_at": t.created_at.isoformat() if t.created_at else None}
