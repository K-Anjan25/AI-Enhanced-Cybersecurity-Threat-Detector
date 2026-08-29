"""Phase 61: ZTNA + microsegmentation."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey, JSON
from sqlalchemy.sql import func
from datetime import datetime, timezone

from app.core.database import Base


def _now():
    return datetime.now(timezone.utc)


class NetworkSegment(Base):
    __tablename__ = "network_segments"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    cidr = Column(String(50), nullable=False)  # e.g. 10.0.0.0/24
    zone = Column(String(50), default="internal")  # internal, dmz, external, sensitive
    description = Column(Text, nullable=True)
    risk_level = Column(String(20), default="MEDIUM")
    created_at = Column(DateTime(timezone=True), default=_now)


class ZTNAPolicy(Base):
    __tablename__ = "ztna_policies"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    # Policy DSL: {"src_segment": 1, "dst_segment": 2, "action": "allow", "conditions": {"user_role": "ADMIN", "mfa_required": true}}
    policy_json = Column(JSON, nullable=False, default=dict)
    src_segment_id = Column(Integer, ForeignKey("network_segments.id"), nullable=True)
    dst_segment_id = Column(Integer, ForeignKey("network_segments.id"), nullable=True)
    action = Column(String(20), default="deny")  # allow, deny, isolate, require_mfa
    priority = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class ZTNADecisionLog(Base):
    __tablename__ = "ztna_decision_logs"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    policy_id = Column(Integer, ForeignKey("ztna_policies.id"), nullable=True)
    src_ip = Column(String(50), nullable=False)
    dst_ip = Column(String(50), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(20), nullable=False)  # allow, deny
    reason = Column(Text, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), default=_now)
