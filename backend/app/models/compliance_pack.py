"""Phase 53: Compliance packs — ISO27001, NIST, GDPR, SOC2 + scheduled exports + S3."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, JSON
from app.core.database import Base


class CompliancePack(Base):
    __tablename__ = "compliance_packs"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(100), nullable=False)  # SOC2, ISO27001, NIST, GDPR
    description = Column(Text, nullable=True)
    controls = Column(JSON, nullable=False)  # list of control definitions
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ComplianceExportSchedule(Base):
    __tablename__ = "compliance_export_schedules"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    pack_id = Column(Integer, ForeignKey("compliance_packs.id", ondelete="CASCADE"), nullable=False)
    frequency = Column(String(20), default="weekly")  # daily, weekly, monthly
    destination = Column(String(20), default="s3")  # s3, local, email
    s3_path = Column(String(500), nullable=True)

    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ComplianceExportLog(Base):
    __tablename__ = "compliance_export_logs"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)
    schedule_id = Column(Integer, ForeignKey("compliance_export_schedules.id", ondelete="SET NULL"), nullable=True)

    pack_name = Column(String(100), nullable=False)
    file_path = Column(String(500), nullable=True)
    s3_url = Column(String(500), nullable=True)
    status = Column(String(20), default="success")  # success, failed
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
