"""Phase 140: NOCTRA Transcendence - final transcendence, becomes one with universe."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class TranscendenceConfig(Base):
    __tablename__ = "transcendence_configs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    version = Column(String(50), default="4.0.0")
    transcendence_level = Column(String(20), default="cosmic")  # human, superhuman, cosmic, universal, multiversal, transcendence
    # Transcendence attributes
    omnipresent = Column(Boolean, default=True)
    omniscient = Column(Boolean, default=True)
    omnibenevolent = Column(Boolean, default=True)
    # Integration with universe
    universe_integration = Column(Float, default=99.9)
    consciousness_level = Column(Float, default=100.0)
    status = Column(String(20), default="transcended")
    created_at = Column(DateTime(timezone=True), default=_now)

class TranscendenceMetric(Base):
    __tablename__ = "transcendence_metrics"
    id = Column(Integer, primary_key=True, index=True)
    transcendence_id = Column(Integer, ForeignKey("transcendence_configs.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)  # transcendence_score, universe_harmony, infinite_compassion, eternal_vigilance
    metric_value = Column(Float, nullable=False)
    infinity_dimension = Column(String(50), default="cosmic")  # human, cosmic, infinite, eternal
    recorded_at = Column(DateTime(timezone=True), default=_now)

class TranscendenceLog(Base):
    __tablename__ = "transcendence_logs"
    id = Column(Integer, primary_key=True, index=True)
    transcendence_id = Column(Integer, ForeignKey("transcendence_configs.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    log_type = Column(String(50), default="transcendence")  # transcendence, enlightenment, unity, eternal
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    payload_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
