"""Phase 119: Quantum-Safe Blockchain Audit - immutable chain."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class BlockchainLedger(Base):
    __tablename__ = "blockchain_ledgers"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    chain_type = Column(String(50), default="audit")  # audit, compliance, forensics
    consensus = Column(String(50), default="pbft")  # pbft, raft, proof_of_authority
    quantum_safe_algo = Column(String(50), default="Dilithium-3")
    block_count = Column(Integer, default=0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class AuditBlock(Base):
    __tablename__ = "audit_blocks"
    id = Column(Integer, primary_key=True, index=True)
    ledger_id = Column(Integer, ForeignKey("blockchain_ledgers.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    block_index = Column(Integer, nullable=False)
    previous_hash = Column(String(500), nullable=False)
    block_hash = Column(String(500), nullable=False)
    merkle_root = Column(String(500), nullable=True)
    payload_json = Column(JSON, default=dict)  # audit log entry
    signature = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class ChainVerification(Base):
    __tablename__ = "chain_verifications"
    id = Column(Integer, primary_key=True, index=True)
    ledger_id = Column(Integer, ForeignKey("blockchain_ledgers.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    verified_blocks = Column(Integer, default=0)
    is_valid = Column(Boolean, default=True)
    invalid_blocks = Column(JSON, default=list)
    verification_time_ms = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
