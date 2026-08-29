"""Phase 92: Quantum-Safe Crypto Agility."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class CryptoInventory(Base):
    __tablename__ = "crypto_inventory"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    # Crypto usage
    algorithm = Column(String(100), nullable=False)  # RSA-2048, ECDSA-P256, Kyber-768, Dilithium-3
    key_size = Column(Integer, nullable=True)
    usage = Column(String(50), default="tls")  # tls, signing, encryption, cert
    location = Column(String(500), nullable=True)  # where used
    # Quantum risk
    is_quantum_safe = Column(Boolean, default=False)
    quantum_risk_score = Column(Float, default=0.0)  # 0-100
    migration_status = Column(String(20), default="pending")  # pending, in_progress, migrated, not_needed
    created_at = Column(DateTime(timezone=True), default=_now)

class QuantumMigrationPlan(Base):
    __tablename__ = "quantum_migration_plans"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    # Plan: list of crypto to migrate
    inventory_ids = Column(JSON, default=list)
    target_algorithm = Column(String(100), default="Kyber-768")  # Kyber, Dilithium, Falcon
    status = Column(String(20), default="planned")  # planned, running, completed
    progress = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
