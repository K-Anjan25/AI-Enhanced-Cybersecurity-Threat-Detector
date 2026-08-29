"""Phase 147: Akashic Ledger - immutable record of all events across all timelines, beyond blockchain."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AkashicRecord(Base):
    __tablename__ = "akashic_records"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    record_type = Column(String(100), default="threat_event")  # threat_event, creation, destruction, transcendence, all
    timeline_id = Column(String(100), default="primary")  # which timeline
    universe_id = Column(String(100), default="primary")  # which universe
    event_json = Column(JSON, default=dict)  # the event itself
    immutable_hash = Column(String(128), nullable=False)  # SHA512 hash chained
    previous_hash = Column(String(128), nullable=True)  # blockchain chain
    akashic_index = Column(Integer, default=0)  # position in akashic
    verified = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class AkashicQuery(Base):
    __tablename__ = "akashic_queries"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    query_type = Column(String(100), default="temporal_range")
    query_json = Column(JSON, default=dict)
    result_count = Column(Integer, default=0)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime(timezone=True), default=_now)

class AkashicVerification(Base):
    __tablename__ = "akashic_verifications"
    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("akashic_records.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    verification_type = Column(String(100), default="hash_chain")
    is_valid = Column(Boolean, default=True)
    verification_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
