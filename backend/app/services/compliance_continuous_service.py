"""Phase 71: Continuous compliance evidence automation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.compliance_continuous import ComplianceControl, ComplianceEvidence, ComplianceAssessment
from app.models import AuditLog, Case


def _now():
    return datetime.now(timezone.utc)


SOC2_CONTROLS = [
    {"control_id": "CC6.1", "title": "Logical access security", "description": "Entity authorizes, modifies, or removes access", "framework": "SOC2"},
    {"control_id": "CC6.2", "title": "Access provisioning", "description": "Prior to issuing system credentials", "framework": "SOC2"},
    {"control_id": "CC7.2", "title": "System monitoring", "description": "System monitoring for anomalies", "framework": "SOC2"},
    {"control_id": "CC8.1", "title": "Change management", "description": "Change management process", "framework": "SOC2"},
]

def list_controls(db: Session, org_id: int, framework: str = None) -> List[ComplianceControl]:
    q = db.query(ComplianceControl).filter(ComplianceControl.org_id == org_id)
    if framework:
        q = q.filter(ComplianceControl.framework == framework)
    return q.all()

def ensure_default_controls(db: Session, org_id: int):
    existing = db.query(ComplianceControl).filter(ComplianceControl.org_id == org_id).count()
    if existing > 0:
        return
    for c in SOC2_CONTROLS:
        ctrl = ComplianceControl(
            org_id=org_id,
            framework=c["framework"],
            control_id=c["control_id"],
            title=c["title"],
            description=c["description"],
            automation_json={"evidence_sources": ["audit_logs"], "check_query": "audit_logs"},
            is_automated=True,
            compliance_status="unknown",
        )
        db.add(ctrl)
    db.commit()

def collect_evidence(db: Session, org_id: int) -> List[ComplianceEvidence]:
    ensure_default_controls(db, org_id)
    controls = list_controls(db, org_id)
    evidences = []
    # Simple: for each control, collect recent audit logs as evidence
    recent_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(20).all()
    for ctrl in controls:
        # Check if compliant: if we have logs, mark compliant
        is_compliant = len(recent_logs) > 0
        ctrl.compliance_status = "compliant" if is_compliant else "non_compliant"
        ctrl.last_checked_at = _now()
        ev = ComplianceEvidence(
            org_id=org_id,
            control_id=ctrl.id,
            evidence_type="audit_log",
            evidence_json={"log_count": len(recent_logs), "sample_logs": [{"action": l.action, "actor": l.actor, "created_at": l.created_at.isoformat() if l.created_at else None} for l in recent_logs[:5]]},
            is_valid=True,
        )
        db.add(ev)
        evidences.append(ev)
    db.commit()
    for e in evidences:
        db.refresh(e)
    return evidences

def run_assessment(db: Session, org_id: int, framework: str = "SOC2") -> ComplianceAssessment:
    ensure_default_controls(db, org_id)
    collect_evidence(db, org_id)
    controls = list_controls(db, org_id, framework)
    compliant = len([c for c in controls if c.compliance_status == "compliant"])
    total = len(controls)
    score = (compliant / total * 100) if total > 0 else 0.0
    assessment = ComplianceAssessment(
        org_id=org_id,
        framework=framework,
        total_controls=total,
        compliant_controls=compliant,
        compliance_score=score,
        findings_json={"compliant": compliant, "total": total, "controls": [{"control_id": c.control_id, "status": c.compliance_status} for c in controls]},
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment

def list_assessments(db: Session, org_id: int) -> List[ComplianceAssessment]:
    return db.query(ComplianceAssessment).filter(ComplianceAssessment.org_id == org_id).order_by(ComplianceAssessment.assessment_date.desc()).all()

def serialize_control(c: ComplianceControl) -> Dict[str, Any]:
    return {"id": c.id, "framework": c.framework, "control_id": c.control_id, "title": c.title, "compliance_status": c.compliance_status, "is_automated": c.is_automated, "last_checked_at": c.last_checked_at.isoformat() if c.last_checked_at else None}

def serialize_assessment(a: ComplianceAssessment) -> Dict[str, Any]:
    return {"id": a.id, "framework": a.framework, "compliance_score": a.compliance_score, "total_controls": a.total_controls, "compliant_controls": a.compliant_controls, "assessment_date": a.assessment_date.isoformat() if a.assessment_date else None, "findings": a.findings_json}
