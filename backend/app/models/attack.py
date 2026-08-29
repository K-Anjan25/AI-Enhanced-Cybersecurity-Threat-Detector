"""Phase 56: ATT&CK Navigator + actor attribution."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, JSON, Text
from app.core.database import Base


class ThreatActor(Base):
    __tablename__ = "threat_actors"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)

    name = Column(String(255), nullable=False, unique=True)
    aliases = Column(JSON, nullable=True)  # list of alias names
    description = Column(Text, nullable=True)
    country = Column(String(100), nullable=True)
    motivation = Column(String(100), nullable=True)

    techniques = Column(JSON, nullable=True)  # list of technique IDs
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AttackHeatmap(Base):
    """Phase 56: ATT&CK heatmap per org — technique usage counts."""

    __tablename__ = "attack_heatmaps"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    technique_id = Column(String(20), nullable=False)  # e.g. T1078
    tactic = Column(String(50), nullable=True)
    count = Column(Integer, default=0, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
