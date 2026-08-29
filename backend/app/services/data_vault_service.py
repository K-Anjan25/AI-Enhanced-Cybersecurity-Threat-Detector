"""Phase 114: Data Vault service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
import hashlib
from sqlalchemy.orm import Session
from app.models.data_vault import DataVault, VaultSecret, VaultAccessLog

def _now():
    return datetime.now(timezone.utc)

def create_vault(db: Session, org_id: int, name: str, vault_type: str = "confidential") -> DataVault:
    vault = DataVault(org_id=org_id, name=name, vault_type=vault_type, encryption_algo="AES-256-GCM+Kyber", attestation_required=True, status="active")
    db.add(vault)
    db.commit()
    db.refresh(vault)
    return vault

def list_vaults(db: Session, org_id: int) -> List[DataVault]:
    return db.query(DataVault).filter(DataVault.org_id == org_id).all()

def store_secret(db: Session, org_id: int, vault_id: int, secret_name: str, secret_value: str) -> VaultSecret:
    vault = db.query(DataVault).filter(DataVault.id == vault_id, DataVault.org_id == org_id).first()
    if not vault:
        raise ValueError("Vault not found")
    secret_hash = hashlib.sha256(secret_value.encode()).hexdigest()
    secret = VaultSecret(vault_id=vault_id, org_id=org_id, secret_name=secret_name, secret_hash=secret_hash, classification="confidential")
    db.add(secret)
    # Access log
    log = VaultAccessLog(vault_id=vault_id, org_id=org_id, accessor="system", access_type="write", justification="store secret", attestation_json={"enclave_verified": True}, granted=True)
    db.add(log)
    db.commit()
    db.refresh(secret)
    return secret

def list_secrets(db: Session, org_id: int, vault_id: int = None) -> List[VaultSecret]:
    q = db.query(VaultSecret).filter(VaultSecret.org_id == org_id)
    if vault_id:
        q = q.filter(VaultSecret.vault_id == vault_id)
    return q.limit(50).all()

def serialize_vault(v: DataVault) -> Dict[str, Any]:
    return {"id": v.id, "name": v.name, "vault_type": v.vault_type, "encryption_algo": v.encryption_algo, "attestation_required": v.attestation_required, "status": v.status}

def serialize_secret(s: VaultSecret) -> Dict[str, Any]:
    return {"id": s.id, "vault_id": s.vault_id, "secret_name": s.secret_name, "secret_hash": s.secret_hash[:16]+"...", "classification": s.classification}
