"""Phase 92: Quantum-Safe service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.quantum_safe import CryptoInventory, QuantumMigrationPlan

def _now():
    return datetime.now(timezone.utc)

def scan_crypto(db: Session, org_id: int) -> List[CryptoInventory]:
    """Mock scan for crypto usage."""
    existing = db.query(CryptoInventory).filter(CryptoInventory.org_id == org_id).count()
    if existing > 0:
        return db.query(CryptoInventory).filter(CryptoInventory.org_id == org_id).all()
    defaults = [
        {"algorithm": "RSA-2048", "key_size": 2048, "usage": "tls", "location": "web01:443", "is_quantum_safe": False, "quantum_risk_score": 85, "migration_status": "pending"},
        {"algorithm": "ECDSA-P256", "key_size": 256, "usage": "signing", "location": "api gateway", "is_quantum_safe": False, "quantum_risk_score": 80, "migration_status": "pending"},
        {"algorithm": "Kyber-768", "key_size": 768, "usage": "encryption", "location": "new service", "is_quantum_safe": True, "quantum_risk_score": 5, "migration_status": "migrated"},
    ]
    created = []
    for d in defaults:
        inv = CryptoInventory(org_id=org_id, **d)
        db.add(inv)
        created.append(inv)
    db.commit()
    for c in created:
        db.refresh(c)
    return created

def list_inventory(db: Session, org_id: int) -> List[CryptoInventory]:
    return db.query(CryptoInventory).filter(CryptoInventory.org_id == org_id).all()

def create_migration_plan(db: Session, org_id: int, name: str, inventory_ids: List[int], target_algorithm: str = "Kyber-768") -> QuantumMigrationPlan:
    plan = QuantumMigrationPlan(org_id=org_id, name=name, inventory_ids=inventory_ids, target_algorithm=target_algorithm, status="planned", progress=0)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

def serialize_inv(i: CryptoInventory) -> Dict[str, Any]:
    return {"id": i.id, "algorithm": i.algorithm, "key_size": i.key_size, "usage": i.usage, "location": i.location, "is_quantum_safe": i.is_quantum_safe, "quantum_risk_score": i.quantum_risk_score, "migration_status": i.migration_status}

def serialize_plan(p: QuantumMigrationPlan) -> Dict[str, Any]:
    return {"id": p.id, "name": p.name, "inventory_ids": p.inventory_ids, "target_algorithm": p.target_algorithm, "status": p.status, "progress": p.progress}
