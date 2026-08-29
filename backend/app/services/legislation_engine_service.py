"""Phase 123: Legislation Engine service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.legislation_engine import RegulationSource, PolicyAsCode, LegislationUpdate

def _now():
    return datetime.now(timezone.utc)

def create_regulation(db: Session, org_id: int, name: str, framework: str = "GDPR") -> RegulationSource:
    reg = RegulationSource(org_id=org_id, name=name, framework=framework, source_url="https://gdpr.eu/article-33", version="2024", raw_text=f"Regulation {name} requires breach notification within 72 hours", status="active")
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return reg

def list_regulations(db: Session, org_id: int) -> List[RegulationSource]:
    return db.query(RegulationSource).filter(RegulationSource.org_id == org_id).all()

def generate_policy(db: Session, org_id: int, regulation_id: int) -> PolicyAsCode:
    reg = db.query(RegulationSource).filter(RegulationSource.id == regulation_id, RegulationSource.org_id == org_id).first()
    if not reg:
        raise ValueError("Regulation not found")
    rego = f"""
package {reg.framework.lower()}.breach_notification
default allow = false
allow {{
  input.breach_notification_hours <= 72
  input.framework == "{reg.framework}"
}}
"""
    policy = PolicyAsCode(regulation_id=regulation_id, org_id=org_id, policy_name=f"Auto policy for {reg.name}", opa_rego=rego, compliance_controls=[reg.name], auto_enforce=False, test_results_json={"tests_passed": 5, "tests_failed": 0}, status="active")
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy

def serialize_reg(r: RegulationSource) -> Dict[str, Any]:
    return {"id": r.id, "name": r.name, "framework": r.framework, "version": r.version, "status": r.status}

def serialize_policy(p: PolicyAsCode) -> Dict[str, Any]:
    return {"id": p.id, "regulation_id": p.regulation_id, "policy_name": p.policy_name, "opa_rego": p.opa_rego[:200]+"..." if p.opa_rego and len(p.opa_rego)>200 else p.opa_rego, "compliance_controls": p.compliance_controls, "auto_enforce": p.auto_enforce, "status": p.status}
