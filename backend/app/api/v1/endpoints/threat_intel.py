"""Phase 49: Threat intel enrichment endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import threat_intel_enrichment

router = APIRouter(prefix="/threat-intel", tags=["Threat Intel (Phase 49)"])


@router.get("/status")
def get_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return threat_intel_enrichment.get_enrichment_status()


@router.get("/enrich/ip/{ip}")
def enrich_ip(
    ip: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    return threat_intel_enrichment.enrich_ip(ip)


@router.get("/enrich/domain/{domain}")
def enrich_domain(
    domain: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    return threat_intel_enrichment.enrich_domain(domain)


@router.get("/enrich/hash/{file_hash}")
def enrich_hash(
    file_hash: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:read")),
):
    return threat_intel_enrichment.enrich_hash(file_hash)


@router.post("/enrich/alert/{alert_id}")
def enrich_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    from app.models import SecurityAlert

    alert = db.query(SecurityAlert).filter(SecurityAlert.id == alert_id, SecurityAlert.org_id == current_user.org_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    result = threat_intel_enrichment.enrich_alert_threat_intel(db, alert)
    return result
