"""Phase 115: Compliance Auditor v2 service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.compliance_auditor_v2 import ComplianceAuditV2, AuditFindingV2, AuditEvidenceV2

def _now():
    return datetime.now(timezone.utc)

def create_audit(db: Session, org_id: int, name: str, framework: str = "SOC2") -> ComplianceAuditV2:
    audit = ComplianceAuditV2(org_id=org_id, name=name, framework=framework, auditor_type="llm", scope_json={"controls": ["CC6.1","CC6.2","CC7.2"]}, status="running", compliance_score=0.0)
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit

def list_audits(db: Session, org_id: int) -> List[ComplianceAuditV2]:
    return db.query(ComplianceAuditV2).filter(ComplianceAuditV2.org_id == org_id).order_by(ComplianceAuditV2.created_at.desc()).all()

def run_audit(db: Session, org_id: int, audit_id: int) -> ComplianceAuditV2:
    audit = db.query(ComplianceAuditV2).filter(ComplianceAuditV2.id == audit_id, ComplianceAuditV2.org_id == org_id).first()
    if not audit:
        raise ValueError("Audit not found")
    # Mock findings
    finding = AuditFindingV2(audit_id=audit_id, org_id=org_id, control_id="CC6.1", title="Logical access controls not enforced for production DB", severity="HIGH", status="open", llm_reasoning="Found 3 users with excessive privileges, no MFA enforced")
    db.add(finding)
    db.commit()
    db.refresh(finding)
    evidence = AuditEvidenceV2(finding_id=finding.id, audit_id=audit_id, org_id=org_id, evidence_type="config", evidence_json={"resource": "prod-db", "issue": "no MFA"}, collected_by="llm", verified=True)
    db.add(evidence)
    audit.compliance_score = 72.5
    audit.status = "completed"
    db.commit()
    db.refresh(audit)
    return audit

def list_findings(db: Session, org_id: int, audit_id: int = None) -> List[AuditFindingV2]:
    q = db.query(AuditFindingV2).filter(AuditFindingV2.org_id == org_id)
    if audit_id:
        q = q.filter(AuditFindingV2.audit_id == audit_id)
    return q.order_by(AuditFindingV2.created_at.desc()).limit(50).all()

def serialize_audit(a: ComplianceAuditV2) -> Dict[str, Any]:
    return {"id": a.id, "name": a.name, "framework": a.framework, "auditor_type": a.auditor_type, "scope": a.scope_json, "status": a.status, "compliance_score": a.compliance_score}

def serialize_finding(f: AuditFindingV2) -> Dict[str, Any]:
    return {"id": f.id, "audit_id": f.audit_id, "control_id": f.control_id, "title": f.title, "severity": f.severity, "status": f.status, "llm_reasoning": f.llm_reasoning}
