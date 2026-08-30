"""Posture score — one 0-100 number for how well defended the org is.

Every sub-score is derived from rows that exist in this tenant. Where a signal
has no data we return `None` for that dimension and drop it from the average
rather than substituting a flattering constant: a score built on invented
inputs is worse than a score with fewer inputs, because the customer will act
on it.

Dimensions (NIST CSF):
  detect     — ATT&CK coverage + hunting activity
  protect    — open critical vulns and cloud misconfigurations
  respond    — case backlog and how much of it actually gets closed
  recover    — retention policies + legal-hold readiness
  governance — measured compliance control status
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models import SecurityAlert, Case
from app.models.vuln import Vulnerability
from app.models.cspm import CSPMViolation
from app.models.posture_score import PostureScore, PostureFinding, PostureRecommendation

def _now():
    return datetime.now(timezone.utc)


def _detect_score(db: Session, org_id: int) -> Optional[float]:
    """ATT&CK technique coverage, nudged by how actively the org hunts."""
    from app.models.hunt import Hunt
    from app.models.attack_coverage import AttackCoverage

    coverage = db.query(AttackCoverage).filter(AttackCoverage.org_id == org_id).all()
    hunts = db.query(Hunt).filter(Hunt.org_id == org_id).count()
    if not coverage and hunts == 0:
        return None
    avg_coverage = (
        sum(c.coverage_score for c in coverage) / len(coverage) if coverage else 0.0
    )
    # Hunting demonstrates detection capability beyond static rule coverage,
    # capped so an org cannot hunt its way to a perfect score.
    return min(100.0, avg_coverage + min(20.0, hunts * 2.0))


def _protect_score(db: Session, org_id: int) -> Optional[float]:
    """Open critical exposure: unpatched vulnerabilities and cloud misconfig."""
    vuln_total = db.query(Vulnerability).filter(Vulnerability.org_id == org_id).count()
    cspm_total = db.query(CSPMViolation).filter(CSPMViolation.org_id == org_id).count()
    if vuln_total == 0 and cspm_total == 0:
        return None

    vuln_critical = (
        db.query(Vulnerability)
        .filter(
            Vulnerability.org_id == org_id,
            Vulnerability.severity == "CRITICAL",
            Vulnerability.status == "open",
        )
        .count()
    )
    cspm_critical = (
        db.query(CSPMViolation)
        .filter(
            CSPMViolation.org_id == org_id,
            CSPMViolation.severity == "CRITICAL",
            CSPMViolation.status == "open",
        )
        .count()
    )
    return max(0.0, 100.0 - (vuln_critical * 10.0 + cspm_critical * 15.0))


def _respond_score(db: Session, org_id: int) -> Optional[float]:
    """Backlog health: what share of cases the team actually closes."""
    total = db.query(Case).filter(Case.org_id == org_id).count()
    if total == 0:
        return None
    closed = (
        db.query(Case)
        .filter(Case.org_id == org_id, Case.status.in_(("resolved", "closed")))
        .count()
    )
    open_cases = total - closed
    closure_rate = (closed / total) * 100.0
    # An unbounded backlog erodes the score even at a good closure rate.
    return max(0.0, min(100.0, closure_rate - min(40.0, open_cases * 2.0)))


def _recover_score(db: Session, org_id: int) -> Optional[float]:
    """Recovery readiness: are retention policies defined and holds honoured?"""
    try:
        from app.models.data_lifecycle import DataRetentionPolicy, DataArchiveLog
    except Exception:  # pragma: no cover - module optional
        return None

    policies = (
        db.query(DataRetentionPolicy)
        .filter(DataRetentionPolicy.org_id == org_id, DataRetentionPolicy.is_active == True)  # noqa: E712
        .count()
    )
    if policies == 0:
        # No retention policy at all is a real, measurable gap — not "no data".
        return 20.0

    archives = db.query(DataArchiveLog).filter(DataArchiveLog.org_id == org_id).count()
    # Policies defined earns the base; evidence they actually run earns the rest.
    score = 60.0 + min(40.0, archives * 5.0)
    return min(100.0, score)


def _governance_score(db: Session, org_id: int) -> Optional[float]:
    """Share of assessed compliance controls currently passing."""
    try:
        from app.models.compliance_continuous import ComplianceControl
    except Exception:  # pragma: no cover - module optional
        return None

    controls = db.query(ComplianceControl).filter(ComplianceControl.org_id == org_id).all()
    assessed = [c for c in controls if (c.compliance_status or "unknown") != "unknown"]
    if not assessed:
        return None
    compliant = [c for c in assessed if c.compliance_status == "compliant"]
    return (len(compliant) / len(assessed)) * 100.0


def calculate_posture(db: Session, org_id: int) -> PostureScore:
    dimensions: Dict[str, Optional[float]] = {
        "detect": _detect_score(db, org_id),
        "protect": _protect_score(db, org_id),
        "respond": _respond_score(db, org_id),
        "recover": _recover_score(db, org_id),
        "governance": _governance_score(db, org_id),
    }
    measured = {k: v for k, v in dimensions.items() if v is not None}

    # Average only what we actually measured. An org with no cloud footprint is
    # not penalised for having no CSPM data.
    overall = sum(measured.values()) / len(measured) if measured else 0.0

    prev = (
        db.query(PostureScore)
        .filter(PostureScore.org_id == org_id)
        .order_by(PostureScore.created_at.desc())
        .first()
    )
    previous_score = prev.overall_score if prev else None
    trend = "stable"
    if previous_score is not None:
        if overall > previous_score + 5:
            trend = "improving"
        elif overall < previous_score - 5:
            trend = "degrading"

    total_alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).count()

    breakdown = {k: round(v, 1) for k, v in measured.items()}
    unmeasured = sorted(k for k, v in dimensions.items() if v is None)

    score = PostureScore(
        org_id=org_id,
        overall_score=overall,
        breakdown_json=breakdown,
        business_context_json={
            "total_alerts": total_alerts,
            "measured_dimensions": sorted(measured.keys()),
            # Named explicitly so the UI can say "not measured" rather than
            # implying a dimension scored zero.
            "unmeasured_dimensions": unmeasured,
        },
        previous_score=previous_score,
        trend=trend,
    )
    db.add(score)
    db.commit()
    db.refresh(score)

    _refresh_findings(db, org_id, measured)
    return score


def _refresh_findings(db: Session, org_id: int, measured: Dict[str, float]) -> None:
    """Replace open findings/recommendations with ones matching this reading."""

    db.query(PostureFinding).filter(
        PostureFinding.org_id == org_id, PostureFinding.status == "open"
    ).delete(synchronize_session=False)
    db.query(PostureRecommendation).filter(
        PostureRecommendation.org_id == org_id
    ).delete(synchronize_session=False)
    db.commit()

    # Evidence for each weak dimension, phrased as the gap it actually is.
    detail = {
        "detect": (
            "Detection coverage is thin",
            "Gaps in ATT&CK technique coverage mean some attacker behaviour would go unseen.",
            "Add detection rules for uncovered techniques and run a hunt against recent telemetry.",
        ),
        "protect": (
            "Unpatched critical exposure",
            "Critical vulnerabilities or cloud misconfigurations are open right now.",
            "Patch critical CVEs and remediate critical cloud findings.",
        ),
        "respond": (
            "Case backlog is growing",
            "Open cases are accumulating faster than they are being closed.",
            "Triage the oldest open cases or raise the autonomy level for low-risk decisions.",
        ),
        "recover": (
            "Recovery readiness unproven",
            "Retention policies are missing or have never produced an archive.",
            "Define a retention policy per data type and verify the archive job runs.",
        ),
        "governance": (
            "Compliance controls failing",
            "Assessed controls are reporting non-compliant.",
            "Review failing controls and attach current evidence.",
        ),
    }

    for dimension, value in sorted(measured.items(), key=lambda kv: kv[1]):
        if value >= 70:
            continue
        title, description, remediation = detail[dimension]
        severity = "HIGH" if value < 50 else "MEDIUM"
        db.add(
            PostureFinding(
                org_id=org_id,
                category=dimension,
                title=f"{title} ({value:.0f}/100)",
                severity=severity,
                description=description,
                impact="high" if value < 50 else "medium",
                remediation=remediation,
                crown_jewel_affected=dimension == "protect",
            )
        )
        db.add(
            PostureRecommendation(
                org_id=org_id,
                title=remediation,
                description=description,
                priority="high" if value < 50 else "medium",
                effort="medium",
                # Closing the gap to 100 is the score headroom this unlocks,
                # divided across the dimensions we average.
                impact_score=round((100.0 - value) / max(1, len(measured)), 1),
            )
        )
    db.commit()


def list_scores(db: Session, org_id: int) -> List[PostureScore]:
    return (
        db.query(PostureScore)
        .filter(PostureScore.org_id == org_id)
        .order_by(PostureScore.created_at.desc())
        .limit(20)
        .all()
    )


def list_findings(db: Session, org_id: int) -> List[PostureFinding]:
    return (
        db.query(PostureFinding)
        .filter(PostureFinding.org_id == org_id, PostureFinding.status == "open")
        .order_by(PostureFinding.severity.desc())
        .limit(50)
        .all()
    )


def list_recommendations(db: Session, org_id: int) -> List[PostureRecommendation]:
    return (
        db.query(PostureRecommendation)
        .filter(PostureRecommendation.org_id == org_id)
        .order_by(PostureRecommendation.impact_score.desc())
        .limit(20)
        .all()
    )


def serialize_score(s) -> Dict[str, Any]:
    return {
        "id": s.id,
        "overall_score": s.overall_score,
        "breakdown": s.breakdown_json,
        "business_context": s.business_context_json,
        "previous_score": s.previous_score,
        "trend": s.trend,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def serialize_finding(f) -> Dict[str, Any]:
    return {
        "id": f.id,
        "category": f.category,
        "title": f.title,
        "severity": f.severity,
        "description": f.description,
        "impact": f.impact,
        "remediation": f.remediation,
        "crown_jewel_affected": f.crown_jewel_affected,
        "status": f.status,
    }


def serialize_recommendation(r) -> Dict[str, Any]:
    return {
        "id": r.id,
        "title": r.title,
        "description": r.description,
        "priority": r.priority,
        "effort": r.effort,
        "impact_score": r.impact_score,
        "estimated_cost": r.estimated_cost,
        "estimated_benefit": r.estimated_benefit,
    }
