"""Phase 91: Federated Intel Sharing service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.federated_intel import IntelSharePackage, IntelShareConsent

def _now():
    return datetime.now(timezone.utc)

def create_package(db: Session, org_id: int, name: str, stix_bundle: Dict, tlp: str = "AMBER", is_anonymized: bool = True, recipient_orgs: List[int] = None) -> IntelSharePackage:
    pkg = IntelSharePackage(org_id=org_id, name=name, stix_bundle_json=stix_bundle, tlp=tlp, is_anonymized=is_anonymized, recipient_orgs=recipient_orgs or [], status="shared")
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg

def list_packages(db: Session, org_id: int) -> List[IntelSharePackage]:
    return db.query(IntelSharePackage).filter(IntelSharePackage.org_id == org_id).order_by(IntelSharePackage.created_at.desc()).all()

def serialize_pkg(p: IntelSharePackage) -> Dict[str, Any]:
    return {"id": p.id, "name": p.name, "tlp": p.tlp, "is_anonymized": p.is_anonymized, "recipient_orgs": p.recipient_orgs, "status": p.status, "created_at": p.created_at.isoformat() if p.created_at else None}
