"""Phase 101: Global SOC Federation service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.global_federation import GlobalFederation, FederatedTenant, CrossBorderCaseShare

def _now():
    return datetime.now(timezone.utc)

def create_federation(db: Session, org_id: int, name: str, regions: List[str] = None) -> GlobalFederation:
    fed = GlobalFederation(org_id=org_id, name=name, regions_json=regions or ["us-east-1","eu-west-1"], data_residency_json={"EU":"eu-only","US":"us-only"}, compliance_frameworks=["GDPR","SOC2"], status="active")
    db.add(fed)
    db.commit()
    db.refresh(fed)
    # Auto-create 2 tenants
    for i, region in enumerate(fed.regions_json[:2]):
        t = FederatedTenant(federation_id=fed.id, org_id=org_id, tenant_name=f"{name}-tenant-{i+1}", region=region, trust_score=85.0, data_sharing_level="anonymized")
        db.add(t)
    db.commit()
    return fed

def list_federations(db: Session, org_id: int) -> List[GlobalFederation]:
    return db.query(GlobalFederation).filter(GlobalFederation.org_id == org_id).order_by(GlobalFederation.created_at.desc()).all()

def list_tenants(db: Session, org_id: int, federation_id: int = None) -> List[FederatedTenant]:
    q = db.query(FederatedTenant).filter(FederatedTenant.org_id == org_id)
    if federation_id:
        q = q.filter(FederatedTenant.federation_id == federation_id)
    return q.all()

def share_case_cross_border(db: Session, org_id: int, federation_id: int, case_id: int, shared_with: List[int]) -> CrossBorderCaseShare:
    share = CrossBorderCaseShare(org_id=org_id, federation_id=federation_id, case_id=case_id, shared_with_orgs=shared_with, anonymization_level="pii_stripped", tlp="AMBER", status="shared")
    db.add(share)
    db.commit()
    db.refresh(share)
    return share

def serialize_fed(f: GlobalFederation) -> Dict[str, Any]:
    return {"id": f.id, "name": f.name, "regions": f.regions_json, "data_residency": f.data_residency_json, "compliance": f.compliance_frameworks, "status": f.status, "created_at": f.created_at.isoformat() if f.created_at else None}

def serialize_tenant(t: FederatedTenant) -> Dict[str, Any]:
    return {"id": t.id, "federation_id": t.federation_id, "tenant_name": t.tenant_name, "region": t.region, "trust_score": t.trust_score, "data_sharing_level": t.data_sharing_level, "is_active": t.is_active}
