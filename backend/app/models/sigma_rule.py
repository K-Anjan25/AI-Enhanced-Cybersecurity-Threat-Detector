"""Phase 52: Sigma rules + custom DSL + versioning."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, JSON
from app.core.database import Base


class SigmaRule(Base):
    __tablename__ = "sigma_rules"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    rule_yaml = Column(Text, nullable=False)  # raw Sigma YAML
    rule_json = Column(JSON, nullable=True)  # parsed
    level = Column(String(20), default="medium")  # informational, low, medium, high, critical
    status = Column(String(20), default="experimental")  # experimental, test, stable

    tags = Column(JSON, nullable=True)  # list of tags
    references = Column(JSON, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)

    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class SigmaRuleVersion(Base):
    __tablename__ = "sigma_rule_versions"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("sigma_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    version = Column(Integer, nullable=False)
    rule_yaml = Column(Text, nullable=False)
    rule_json = Column(JSON, nullable=True)
    change_notes = Column(Text, nullable=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DetectionDSLRule(Base):
    """Phase 52: custom DSL for detection."""

    __tablename__ = "detection_dsl_rules"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    dsl_expression = Column(Text, nullable=False)  # e.g. 'severity >= HIGH AND source_ip IN reputation_blocked'
    severity = Column(String(20), default="MEDIUM")

    is_active = Column(Boolean, default=True, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
