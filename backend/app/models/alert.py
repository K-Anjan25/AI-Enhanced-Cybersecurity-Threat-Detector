from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base

class SecurityAlert(Base):
    __tablename__ = "security_alerts"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)
    alert_type = Column(String(50))  # "network" or "log"
    source_ip = Column(String(50), nullable=True)
    source = Column(String(255), nullable=True)

    severity = Column(String(20))
    score = Column(Float)
    message = Column(Text)

    # MITRE ATT&CK mapping (v3): tactic + technique identifiers.
    mitre_tactic = Column(String(100), nullable=True)
    mitre_technique_id = Column(String(20), nullable=True)
    mitre_technique = Column(String(150), nullable=True)

    # Threat-intel enrichment context (v3): reputation of the source IP.
    threat_intel = Column(JSON, nullable=True)

    # When the event actually happened at the source, as reported by the
    # originating system. Distinct from created_at, which is only when we
    # inserted the row. Nullable on purpose: many sources send nothing usable,
    # and guessing would silently corrupt the detection-latency figures that
    # depend on this. A NULL here means "not supplied", never "instant".
    event_time = Column(DateTime, nullable=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    user = relationship("User", back_populates="alerts")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ScannedAlert(Base):
    __tablename__ = "scanned_alerts"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    threat_type = Column(String(100), nullable=False)
    raw_log = Column(Text, nullable=False)
    risk = Column(String(50), nullable=False)
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    user = relationship("User", back_populates="scanned_alerts")
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ScanBatch(Base):
    """One uploaded-log scan session. Persists upload history so it survives
    process restarts (previously an in-memory python list)."""

    __tablename__ = "scan_batches"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    total_logs = Column(Integer, default=0)
    threats_detected = Column(Integer, default=0)
    status = Column(String(20), default="pending")  # pending | processing | completed | failed
    message = Column(Text, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    user = relationship("User", back_populates="scan_batches")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))