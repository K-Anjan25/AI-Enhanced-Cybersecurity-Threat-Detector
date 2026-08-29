"""Phase 53: Compliance packs — ISO27001, NIST, GDPR, SOC2 + S3 export."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import compliance_pack_service, compliance_service
from app.services.compliance_pack_service import serialize_pack, serialize_schedule

router = APIRouter(prefix="/compliance-packs", tags=["Compliance Packs (Phase 53)"])


class ScheduleCreate(BaseModel):
    pack_name: str
    frequency: str = "weekly"
    destination: str = "s3"
    s3_path: Optional[str] = None


@router.get("")
def list_packs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    rows = compliance_pack_service.list_packs(db, org_id=current_user.org_id)
    return [serialize_pack(p) for p in rows]


@router.get("/{pack_name}")
def get_pack(
    pack_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    pack = compliance_pack_service.get_pack(db, org_id=current_user.org_id, pack_name=pack_name.upper())
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    return serialize_pack(pack)


@router.get("/{pack_name}/evidence")
def get_pack_evidence(
    pack_name: str,
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    pack = compliance_pack_service.get_pack(db, org_id=current_user.org_id, pack_name=pack_name.upper())
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    # Reuse SOC2 evidence bundle logic but map to pack controls
    bundle = compliance_service.get_soc2_evidence_bundle(db, org_id=current_user.org_id, days=days)
    # Override with pack controls
    return {
        "pack": serialize_pack(pack),
        "evidence": bundle,
        "mapped_controls": pack.controls,
    }


@router.post("/schedules", status_code=201)
def create_schedule(
    payload: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    try:
        sched = compliance_pack_service.create_export_schedule(
            db,
            org_id=current_user.org_id,
            pack_name=payload.pack_name.upper(),
            frequency=payload.frequency,
            destination=payload.destination,
            s3_path=payload.s3_path,
        )
        return serialize_schedule(sched)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/schedules/list")
def list_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    rows = compliance_pack_service.list_schedules(db, org_id=current_user.org_id)
    return [serialize_schedule(s) for s in rows]


@router.post("/{pack_name}/export/s3")
def export_s3(
    pack_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    # Generate PDF for pack and export to S3
    from app.services.evidence_pdf import render_evidence_bundle_pdf
    from app.services import case_service

    pack = compliance_pack_service.get_pack(db, org_id=current_user.org_id, pack_name=pack_name.upper())
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    bundle = compliance_service.get_soc2_evidence_bundle(db, org_id=current_user.org_id, days=90)
    chain_verify = compliance_service.verify_audit_chain(db, org_id=current_user.org_id, limit=1000)

    fake_case = {
        "id": f"{pack_name.upper()}-90d",
        "title": f"{pack_name.upper()} Evidence Bundle",
        "status": "COMPLIANCE",
        "severity": "INFO",
    }
    fake_chain = {"chain": [], "last_hash": chain_verify.get("last_hash", "-"), "verified": chain_verify.get("chain_valid", False)}

    try:
        pdf_bytes = render_evidence_bundle_pdf(
            case_data=fake_case,
            chain_of_custody=fake_chain,
            audit_verification=chain_verify,
            soc2_bundle=bundle,
            generated_by=current_user.username,
            org_id=current_user.org_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF render failed: {exc}")

    result = compliance_pack_service.export_to_s3(db, org_id=current_user.org_id, pack_name=pack_name.upper(), pdf_bytes=pdf_bytes)
    return result
