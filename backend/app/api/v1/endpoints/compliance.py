"""Compliance evidence endpoints — tamper-evident audit, SOC2 bundle, chain-of-custody (Phase 45/48)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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


@router.get("/cases/{case_id}/evidence-bundle/pdf")
def get_case_evidence_bundle_pdf(
    case_id: int,
    include_soc2: bool = Query(False, description="Include SOC2 controls evidence in PDF"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase 48: Download evidence bundle as PDF with chain-of-custody + hash verification.

    Renders server-side PDF via reportlab, uncompressed for test greppability.
    Includes honest limitations footer.
    """
    case = case_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    chain = compliance_service.get_case_chain_of_custody(db, case)
    audit_verify = compliance_service.verify_audit_chain(db, org_id=current_user.org_id, limit=1000)

    soc2_bundle = None
    if include_soc2:
        try:
            soc2_bundle = compliance_service.get_soc2_evidence_bundle(
                db, org_id=current_user.org_id, days=90
            )
        except Exception:
            soc2_bundle = None

    try:
        from app.services.evidence_pdf import render_evidence_bundle_pdf

        pdf_bytes = render_evidence_bundle_pdf(
            case_data=case_service.serialize_case(case),
            chain_of_custody=chain,
            audit_verification=audit_verify,
            soc2_bundle=soc2_bundle,
            generated_by=getattr(current_user, "username", "unknown"),
            org_id=getattr(current_user, "org_id", None),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF rendering failed: {exc}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename=\"evidence-bundle-case-{case_id}.pdf\"',
            "X-Chain-Last-Hash": chain.get("last_hash", "")[:64],
            "X-Audit-Chain-Valid": str(audit_verify.get("chain_valid", False)),
        },
    )


@router.get("/audit/evidence/pdf")
def get_soc2_evidence_pdf(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """Phase 48: SOC2 evidence bundle as PDF (admin only)."""
    bundle = compliance_service.get_soc2_evidence_bundle(db, org_id=current_user.org_id, days=days)
    chain_verify = compliance_service.verify_audit_chain(db, org_id=current_user.org_id, limit=1000)

    # Create a synthetic case-like dict for PDF header reuse? Instead render custom PDF
    try:
        from app.services.evidence_pdf import render_evidence_bundle_pdf

        # Use empty chain but include soc2
        fake_case = {
            "id": f"SOC2-{days}d",
            "title": f"SOC2 Evidence Bundle — last {days} days",
            "status": "COMPLIANCE",
            "severity": "INFO",
        }
        fake_chain = {"chain": [], "last_hash": chain_verify.get("last_hash", "-"), "verified": chain_verify.get("chain_valid", False)}

        pdf_bytes = render_evidence_bundle_pdf(
            case_data=fake_case,
            chain_of_custody=fake_chain,
            audit_verification=chain_verify,
            soc2_bundle=bundle,
            generated_by=getattr(current_user, "username", "unknown"),
            org_id=getattr(current_user, "org_id", None),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF rendering failed: {exc}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename=\"soc2-evidence-{days}d.pdf\"',
            "X-Audit-Chain-Valid": str(chain_verify.get("chain_valid", False)),
        },
    )
