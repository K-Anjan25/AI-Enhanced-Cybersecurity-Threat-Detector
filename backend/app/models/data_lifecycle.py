"""Phase 57: Data retention + archival + GDPR deletion + legal hold."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, JSON, Text
from app.core.database import Base


class DataRetentionPolicy(Base):
    __tablename__ = "data_retention_policies"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    data_type = Column(String(50), nullable=False)  # alerts, cases, audit_logs, etc
    retention_days = Column(Integer, default=90, nullable=False)
    archive_after_days = Column(Integer, nullable=True)
    delete_after_days = Column(Integer, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DataArchiveLog(Base):
    __tablename__ = "data_archive_logs"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    data_type = Column(String(50), nullable=False)
    archived_count = Column(Integer, default=0, nullable=False)
    archive_path = Column(String(500), nullable=True)
    s3_url = Column(String(500), nullable=True)

    status = Column(String(20), default="success")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class LegalHold(Base):
    __tablename__ = "legal_holds"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    case_ids = Column(JSON, nullable=True)  # list of case IDs under hold
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    released_at = Column(DateTime, nullable=True)


class GDPRDeletionRequest(Base):
    __tablename__ = "gdpr_deletion_requests"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    requested_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_email = Column(String(255), nullable=True)

    reason = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, approved, completed, rejected

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
