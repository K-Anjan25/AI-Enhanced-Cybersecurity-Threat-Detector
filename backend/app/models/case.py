from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class Case(Base):
    """An incident/case that groups related alerts for triage and resolution.

    Multi-tenant (org_id) and audit-friendly: state transitions are intended to
    be recorded in audit_logs by the case service.
    """

    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(String(20), default="open", nullable=False)  # open | triaging | resolved | closed
    priority = Column(String(20), default="medium", nullable=False)  # low | medium | high | critical
    source_alert_id = Column(Integer, ForeignKey("security_alerts.id", ondelete="SET NULL"), nullable=True)

    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assignee = relationship("User", foreign_keys=[assignee_id])

    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by = relationship("User", foreign_keys=[created_by_id])

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # --- Autonomous analyst (Phase 18) --------------------------------------
    # Additive, nullable columns so the existing Incidents page is unaffected.
    # A case with kind='analyst' is an AI-analyst *decision* surfaced in the Feed.
    kind = Column(String(30), default="manual", nullable=True)      # manual | analyst
    analysis = Column(JSON, nullable=True)          # LLM narrative (contract in llm_client)
    blast_radius = Column(JSON, nullable=True)      # {root_entity_id, nodes, links}
    proposed_action = Column(JSON, nullable=True)   # {action_type, target, severity, rationale, undo}
    decision = Column(String(20), default="pending", nullable=True)  # pending|approved|declined|reverted
    decided_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    soar_action_id = Column(String(64), nullable=True)  # action_id of the executed SoarAction
    report = Column(Text, nullable=True)            # generated markdown report
