"""Phase 80: Board-ready PDF export."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class PDFExport(Base):
    __tablename__ = "pdf_exports"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    report_id = Column(Integer, ForeignKey("exec_reports.id"), nullable=True)
    title = Column(String(300), nullable=False)
    export_type = Column(String(50), default="board_pack")  # board_pack, compliance, incident
    s3_bucket = Column(String(200), nullable=True)
    s3_key = Column(String(500), nullable=True)
    file_size_bytes = Column(Integer, default=0)
    status = Column(String(20), default="completed")
    # PDF metadata
    page_count = Column(Integer, default=0)
    includes_charts = Column(Boolean, default=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
