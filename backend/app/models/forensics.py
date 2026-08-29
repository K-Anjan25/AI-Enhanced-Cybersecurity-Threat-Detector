"""Phase 68: Forensics + timeline reconstruction."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class ForensicCase(Base):
    __tablename__ = "forensic_cases"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)  # linked incident case
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="open")  # open, analyzing, closed
    evidence_hash = Column(String(100), nullable=True)  # root hash of evidence chain
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class ForensicArtifact(Base):
    __tablename__ = "forensic_artifacts"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    forensic_case_id = Column(Integer, ForeignKey("forensic_cases.id"), nullable=False, index=True)
    artifact_type = Column(String(50), nullable=False)  # memory_dump, disk_image, log, network_pcap, process_list
    name = Column(String(300), nullable=False)
    hash_sha256 = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)

class TimelineEvent(Base):
    __tablename__ = "forensic_timeline_events"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    forensic_case_id = Column(Integer, ForeignKey("forensic_cases.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    event_type = Column(String(50), nullable=False)  # file_created, process_started, network_connection, login, etc
    description = Column(Text, nullable=True)
    source_artifact_id = Column(Integer, ForeignKey("forensic_artifacts.id"), nullable=True)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
