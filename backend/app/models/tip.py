"""Phase 69: TIP STIX/TAXII/MISP."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class IntelFeed(Base):
    __tablename__ = "intel_feeds"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    feed_type = Column(String(50), default="stix")  # stix, taxii, misp, opencti
    url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    indicator_count = Column(Integer, default=0)
    config_json = Column(JSON, default=dict)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class STIXObject(Base):
    __tablename__ = "stix_objects"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    feed_id = Column(Integer, ForeignKey("intel_feeds.id"), nullable=True)
    stix_id = Column(String(100), nullable=False, index=True)  # e.g. indicator--uuid
    stix_type = Column(String(50), nullable=False)  # indicator, malware, attack-pattern, etc
    spec_version = Column(String(20), default="2.1")
    stix_json = Column(JSON, nullable=False)
    pattern = Column(Text, nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class MISPEvent(Base):
    __tablename__ = "misp_events"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    misp_id = Column(String(100), nullable=True)
    misp_event_id = Column(String(50), nullable=True)
    info = Column(String(500), nullable=True)
    threat_level = Column(Integer, default=2)
    analysis = Column(Integer, default=0)
    distribution = Column(Integer, default=0)
    event_json = Column(JSON, default=dict)
    attributes_json = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=_now)
