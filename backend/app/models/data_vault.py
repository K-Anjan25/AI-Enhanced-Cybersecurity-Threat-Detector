"""Phase 114: Zero-Trust Data Vault - confidential computing."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class DataVault(Base):
    __tablename__ = "data_vaults"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    vault_type = Column(String(50), default="confidential")  # confidential, enclave, hsm
    encryption_algo = Column(String(50), default="AES-256-GCM+Kyber")
    attestation_required = Column(Boolean, default=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class VaultSecret(Base):
    __tablename__ = "vault_secrets"
    id = Column(Integer, primary_key=True, index=True)
    vault_id = Column(Integer, ForeignKey("data_vaults.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    secret_name = Column(String(300), nullable=False)
    secret_hash = Column(String(500), nullable=False)  # hash only, never plaintext
    classification = Column(String(50), default="confidential")  # public, internal, confidential, restricted
    expiry_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class VaultAccessLog(Base):
    __tablename__ = "vault_access_logs"
    id = Column(Integer, primary_key=True, index=True)
    vault_id = Column(Integer, ForeignKey("data_vaults.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    accessor = Column(String(300), nullable=False)
    access_type = Column(String(50), default="read")  # read, write, delete
    justification = Column(Text, nullable=True)
    attestation_json = Column(JSON, default=dict)
    granted = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)
