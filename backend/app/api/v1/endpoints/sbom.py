"""Phase 66: SBOM endpoints."""

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import sbom_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sbom", tags=["sbom"])

class SBOMIn(BaseModel):
    name: str
    sbom_json: Dict[str, Any]
    source: Optional[str] = None

@router.get("/")
def list_sboms(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        sboms = sbom_service.list_sboms(db, current_user.org_id)
        return [sbom_service.serialize_sbom(s) for s in sboms]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/")
def create_sbom(payload: SBOMIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        sbom = sbom_service.parse_cyclonedx(db, current_user.org_id, payload.sbom_json, payload.name, payload.source, created_by_user_id=current_user.id)
        return sbom_service.serialize_sbom(sbom)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/dependencies")
def list_deps(sbom_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        deps = sbom_service.list_dependencies(db, current_user.org_id, sbom_id=sbom_id)
        return [sbom_service.serialize_dep(d) for d in deps]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/risks")
def list_risks(severity: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        risks = sbom_service.list_risks(db, current_user.org_id, severity=severity)
        return [{"id": r.id, "dependency_id": r.dependency_id, "risk_type": r.risk_type, "severity": r.severity, "description": r.description, "status": r.status} for r in risks]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in %s", __name__)
        raise HTTPException(status_code=500, detail=str(e)) from e