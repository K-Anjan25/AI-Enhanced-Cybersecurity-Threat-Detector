"""Compliance evidence endpoints — tamper-evident audit, SOC2 bundle, chain-of-custody (Phase 45)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_role, get_current_user
from app.models import User, Case
from app.services import compliance_service, case_service

router = APIRouter(prefix="/compliance", tags=["Compliance"])


@router.get("/audit/verify")
def verify_audit_chain(
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """Verify tamper-evident audit log chain integrity."""
    return compliance_service.verify_audit_chain(db, org_id=current_user.org_id, limit=limit)


@router.get("/audit/evidence")
def get_soc2_evidence(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """Generate SOC2 evidence bundle mapping audit logs to controls."""
    return compliance_service.get_soc2_evidence_bundle(db, org_id=current_user.org_id, days=days)


@router.post("/audit/retention/enforce")
def enforce_retention(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """Enforce retention policy — delete old audit logs with checkpoint."""
    return compliance_service.enforce_retention_policy(db)


@router.get("/cases/{case_id}/chain-of-custody")
def get_case_chain_of_custody(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return compliance_service.get_case_chain_of_custody(db, case)


@router.get("/cases/{case_id}/evidence-bundle")
def get_case_evidence_bundle(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full evidence bundle for a case: timeline + hash chain + audit logs."""
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    chain = compliance_service.get_case_chain_of_custody(db, case)
    audit_verify = compliance_service.verify_audit_chain(db, org_id=current_user.org_id, limit=100)

    return {
        "case": case_service.serialize_case(case),
        "chain_of_custody": chain,
        "audit_chain_integrity": audit_verify,
        "generated_at": chain.get("chain", [{}])[-1].get("hash") if chain.get("chain") else None,
    }
