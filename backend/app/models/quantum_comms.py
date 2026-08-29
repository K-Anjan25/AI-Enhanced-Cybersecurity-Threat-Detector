"""Phase 105: Quantum Secure Communications - QKD + PQC."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class QuantumChannel(Base):
    __tablename__ = "quantum_channels"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    channel_type = Column(String(50), default="qkd")  # qkd, pqc, hybrid
    endpoint_a = Column(String(300), nullable=True)
    endpoint_b = Column(String(300), nullable=True)
    protocol = Column(String(50), default="BB84")  # BB84, E91, Kyber
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class QKDKey(Base):
    __tablename__ = "qkd_keys"
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("quantum_channels.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    key_id = Column(String(100), nullable=False)
    key_length = Column(Integer, default=256)
    is_quantum_safe = Column(Boolean, default=True)
    expiry_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class SecureMessage(Base):
    __tablename__ = "secure_messages"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    channel_id = Column(Integer, ForeignKey("quantum_channels.id"), nullable=True)
    sender = Column(String(200), nullable=False)
    recipient = Column(String(200), nullable=False)
    encrypted_payload_hash = Column(String(200), nullable=True)
    algorithm = Column(String(50), default="Kyber-1024")
    status = Column(String(20), default="delivered")
    created_at = Column(DateTime(timezone=True), default=_now)
