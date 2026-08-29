"""Phase 63: Vuln management + PT."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import vuln_service

router = APIRouter(prefix="/vulns", tags=["Vulns (Phase 63)"])


class VulnCreate(BaseModel):
    title: str
    severity: str = "MEDIUM"
    cve_id: Optional[str] = None
    cvss_score: Optional[float] = None
    affected_asset: Optional[str] = None
    description: Optional[str] = None
    remediation: Optional[str] = None


class ScanIngest(BaseModel):
    scanner_name: str = "trivy"
    target: str
    results: List[Dict[str, Any]]


@router.get("")
def list_vulns(severity: Optional[str] = None, status: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    rows = vuln_service.list_vulns(db, org_id=current_user.org_id, severity=severity, status=status, limit=limit)
    return [vuln_service.serialize_vuln(r) for r in rows]


@router.post("", status_code=201)
def create_vuln(payload: VulnCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:write"))):
    v = vuln_service.create_vuln(
        db,
        org_id=current_user.org_id,
        title=payload.title,
        severity=payload.severity,
        cve_id=payload.cve_id,
        cvss_score=payload.cvss_score,
        affected_asset=payload.affected_asset,
        description=payload.description,
        remediation=payload.remediation,
    )
    return vuln_service.serialize_vuln(v)


@router.get("/risk/summary")
def risk_summary(db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    return vuln_service.get_risk_summary(db, org_id=current_user.org_id)


@router.get("/scans")
def list_scans(limit: int = 20, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    rows = vuln_service.list_scans(db, org_id=current_user.org_id, limit=limit)
    return [vuln_service.serialize_scan(r) for r in rows]


@router.post("/scans/ingest", status_code=201)
def ingest_scan(payload: ScanIngest, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:write"))):
    scan = vuln_service.ingest_scan_results(db, org_id=current_user.org_id, scanner_name=payload.scanner_name, target=payload.target, results=payload.results, created_by_user_id=current_user.id)
    return vuln_service.serialize_scan(scan)
