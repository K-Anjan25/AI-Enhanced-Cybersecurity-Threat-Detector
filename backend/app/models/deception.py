"""Phase 67: Deception + honeypots + canary tokens."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class Honeypot(Base):
    __tablename__ = "honeypots"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50), default="ssh")  # legacy
    honeypot_type = Column(String(50), default="ssh")  # ssh, http, ftp, database, api
    ip_address = Column(String(50), nullable=True)
    port = Column(Integer, nullable=True)
    banner = Column(String(500), nullable=True)
    status = Column(String(20), default="active")  # active, inactive
    interaction_count = Column(Integer, default=0)
    last_interaction_at = Column(DateTime(timezone=True), nullable=True)
    config_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)

class CanaryToken(Base):
    __tablename__ = "canary_tokens"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    token_type = Column(String(50), default="aws_key")  # aws_key, url, doc, dns, etc
    token_value = Column(String(500), nullable=False)  # the fake secret or url
    is_triggered = Column(Boolean, default=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    triggered_by_ip = Column(String(50), nullable=True)
    status = Column(String(20), default="active")
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class DeceptionAlert(Base):
    __tablename__ = "deception_alerts"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    honeypot_id = Column(Integer, ForeignKey("honeypots.id"), nullable=True)
    canary_id = Column(Integer, ForeignKey("canary_tokens.id"), nullable=True)
    source_type = Column(String(20), default="honeypot")
    source_id = Column(Integer, nullable=True)
    alert_type = Column(String(50), default="honeypot_interaction")
    title = Column(String(300), nullable=True)
    src_ip = Column(String(50), nullable=True)
    attacker_ip = Column(String(50), nullable=True)
    attacker_payload = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    severity = Column(String(20), default="HIGH")
    raw_data = Column(JSON, default=dict)
    evidence_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
