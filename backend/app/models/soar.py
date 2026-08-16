from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class SoarAction(Base):
    """Audit record of an automated response executed by the SOAR engine."""

    __tablename__ = "soar_actions"
    __table_args__ = (Index("ix_soar_actions_org_created", "org_id", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)
    action_id = Column(String(36), unique=True, nullable=False)  # UUID for cross-system traceability
    action_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    rule_name = Column(String(150), nullable=True)
    alert_id = Column(Integer, ForeignKey("security_alerts.id", ondelete="SET NULL"), nullable=True, index=True)
    payload = Column(JSON, nullable=True)
    status = Column(String(20), default="executed", nullable=False)  # executed | failed | review
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    alert = relationship("SecurityAlert")


class SoarPlaybook(Base):
    """An explicit rule -> action override for the SOAR engine.

    Detection rules auto-map to actions by name/severity heuristics; a playbook
    lets an admin pin a rule to a specific action, which takes precedence over
    the heuristic when both apply. Playbooks are tenant-scoped and one per rule.
    """

    __tablename__ = "soar_playbooks"
    __table_args__ = (
        UniqueConstraint("org_id", "rule_id", name="uq_soar_playbook_rule"),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("detection_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    action_type = Column(String(50), nullable=False)  # one of SUPPORTED_ACTIONS
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    rule = relationship("DetectionRule")