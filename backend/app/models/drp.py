"""Phase 97: Digital Risk Protection (DRP) - dark web monitoring."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class DRP_Monitor(Base):
    __tablename__ = "drp_monitors"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    monitor_type = Column(String(50), default="domain")  # domain, email, brand, credential, dark_web
    keyword = Column(String(500), nullable=False)  # domain to monitor, brand name, email
    is_active = Column(Boolean, default=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class DRP_Finding(Base):
    __tablename__ = "drp_findings"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    monitor_id = Column(Integer, ForeignKey("drp_monitors.id"), nullable=False)
    finding_type = Column(String(100), default="leaked_credential")  # leaked_credential, brand_impersonation, data_leak, dark_web_mention
    severity = Column(String(20), default="HIGH")
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    # Evidence
    evidence_json = Column(JSON, default=dict)  # {url, screenshot, leak_source}
    source = Column(String(100), default="dark_web")  # dark_web, paste_site, social, etc
    status = Column(String(20), default="open")  # open, investigating, resolved, false_positive
    created_at = Column(DateTime(timezone=True), default=_now)

class DRP_Takedown(Base):
    __tablename__ = "drp_takedowns"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    finding_id = Column(Integer, ForeignKey("drp_findings.id"), nullable=False)
    takedown_type = Column(String(50), default="domain")  # domain, content, social
    status = Column(String(20), default="requested")  # requested, in_progress, completed, failed
    provider = Column(String(100), nullable=True)  # registrar, hosting provider
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
