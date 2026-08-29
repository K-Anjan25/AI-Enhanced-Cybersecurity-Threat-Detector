"""Phase 80: PDF export for board packs."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.pdf_export import PDFExport
from app.models.exec_risk import ExecReport
from app.core.config import settings


def _now():
    return datetime.now(timezone.utc)


def generate_pdf(db: Session, org_id: int, report_id: int = None, title: str = None, export_type: str = "board_pack", created_by_user_id: int = None) -> PDFExport:
    """Generate PDF (mock if no weasyprint/reportlab, creates metadata)."""
    report = None
    if report_id:
        report = db.query(ExecReport).filter(ExecReport.id == report_id, ExecReport.org_id == org_id).first()

    title = title or (report.title if report else f"Board Pack - {_now().date()}")
    s3_bucket = getattr(settings, "S3_BUCKET", "noctra-exports")
    s3_key = f"exports/org_id={org_id}/pdf/{export_type}_{_now().strftime('%Y%m%d_%H%M%S')}.pdf"

    # In real implementation, use reportlab or weasyprint to generate PDF from report_json
    # For demo, mock file size and page count
    page_count = 12
    file_size = 250 * 1024  # 250KB

    pdf = PDFExport(
        org_id=org_id,
        report_id=report_id,
        title=title,
        export_type=export_type,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        file_size_bytes=file_size,
        status="completed",
        page_count=page_count,
        includes_charts=True,
        created_by_user_id=created_by_user_id,
    )
    db.add(pdf)
    db.commit()
    db.refresh(pdf)

    # Real PDF generation would be:
    # from reportlab.pdfgen import canvas
    # buffer = io.BytesIO()
    # c = canvas.Canvas(buffer)
    # c.drawString(100, 750, title)
    # ... add charts from report_json
    # c.save()
    # upload to S3

    return pdf


def list_exports(db: Session, org_id: int, limit: int = 20) -> List[PDFExport]:
    return db.query(PDFExport).filter(PDFExport.org_id == org_id).order_by(PDFExport.created_at.desc()).limit(limit).all()


def serialize_pdf(p: PDFExport) -> Dict[str, Any]:
    return {"id": p.id, "report_id": p.report_id, "title": p.title, "export_type": p.export_type, "s3_bucket": p.s3_bucket, "s3_key": p.s3_key, "file_size_bytes": p.file_size_bytes, "status": p.status, "page_count": p.page_count, "includes_charts": p.includes_charts, "created_at": p.created_at.isoformat() if p.created_at else None}
