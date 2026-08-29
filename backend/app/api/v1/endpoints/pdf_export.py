"""Phase 80: PDF export endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services import pdf_export_service

router = APIRouter(prefix="/pdf-export", tags=["PDF Export (Phase 80)"])

class PDFIn(BaseModel):
    report_id: Optional[int] = None
    title: Optional[str] = None
    export_type: str = "board_pack"

@router.post("/")
def generate_pdf(payload: PDFIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        pdf = pdf_export_service.generate_pdf(db, current_user.org_id, report_id=payload.report_id, title=payload.title, export_type=payload.export_type, created_by_user_id=current_user.id)
        return pdf_export_service.serialize_pdf(pdf)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/")
def list_pdfs(limit: int = 20, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        pdfs = pdf_export_service.list_exports(db, current_user.org_id, limit=limit)
        return [pdf_export_service.serialize_pdf(p) for p in pdfs]
    except Exception:
        return []
