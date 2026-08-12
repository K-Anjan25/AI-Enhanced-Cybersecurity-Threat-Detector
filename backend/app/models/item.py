from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, event
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class DetectionRule(Base):
    """A tunable signature / heuristic rule used by the detection engine."""

    __tablename__ = "detection_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(20), default="MEDIUM", nullable=False)
    pattern = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class IpReputation(Base):
    """Reputation scoring + blacklist status for observed source IPs."""

    __tablename__ = "ip_reputation"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(50), unique=True, nullable=False, index=True)
    threat_score = Column(Float, default=0.0, nullable=False)
    is_blocked = Column(Boolean, default=False, nullable=False)
    category = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class EngineSetting(Base):
    """Singleton-style key/value store for threat detection engine settings."""

    __tablename__ = "engine_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    """Immutable trail of administrative and triage actions.

    Append-only by design: UPDATE and DELETE are rejected at the ORM layer so
    the audit trail cannot be silently rewritten or purged through the API.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False)
    actor = Column(String(100), nullable=True)
    resource = Column(String(150), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)


@event.listens_for(AuditLog, "before_update")
def _reject_audit_update(mapper, connection, target):
    raise AssertionError("AuditLog is append-only; updates are not allowed.")


@event.listens_for(AuditLog, "before_delete")
def _reject_audit_delete(mapper, connection, target):
    raise AssertionError("AuditLog is append-only; deletes are not allowed.")
