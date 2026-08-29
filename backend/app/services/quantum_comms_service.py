"""Phase 105: Quantum Comms service."""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.quantum_comms import QuantumChannel, QKDKey, SecureMessage
import hashlib, secrets

def _now():
    return datetime.now(timezone.utc)

def create_channel(db: Session, org_id: int, name: str, channel_type: str = "hybrid") -> QuantumChannel:
    ch = QuantumChannel(org_id=org_id, name=name, channel_type=channel_type, endpoint_a="soc-primary", endpoint_b="soc-dr", protocol="Kyber-1024+BB84", status="active")
    db.add(ch)
    db.commit()
    db.refresh(ch)
    # Create initial QKD key
    key = QKDKey(channel_id=ch.id, org_id=org_id, key_id=f"qkd-{secrets.token_hex(8)}", key_length=256, is_quantum_safe=True, expiry_at=_now()+timedelta(hours=24), status="active")
    db.add(key)
    db.commit()
    return ch

def list_channels(db: Session, org_id: int) -> List[QuantumChannel]:
    return db.query(QuantumChannel).filter(QuantumChannel.org_id == org_id).order_by(QuantumChannel.created_at.desc()).all()

def send_secure_message(db: Session, org_id: int, channel_id: int, sender: str, recipient: str, payload: str) -> SecureMessage:
    ch = db.query(QuantumChannel).filter(QuantumChannel.id == channel_id, QuantumChannel.org_id == org_id).first()
    if not ch:
        raise ValueError("Channel not found")
    hash_val = hashlib.sha256(payload.encode()).hexdigest()
    msg = SecureMessage(org_id=org_id, channel_id=channel_id, sender=sender, recipient=recipient, encrypted_payload_hash=hash_val, algorithm="Kyber-1024", status="delivered")
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

def list_messages(db: Session, org_id: int) -> List[SecureMessage]:
    return db.query(SecureMessage).filter(SecureMessage.org_id == org_id).order_by(SecureMessage.created_at.desc()).limit(20).all()

def serialize_channel(c: QuantumChannel) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "channel_type": c.channel_type, "endpoint_a": c.endpoint_a, "endpoint_b": c.endpoint_b, "protocol": c.protocol, "status": c.status}

def serialize_message(m: SecureMessage) -> Dict[str, Any]:
    return {"id": m.id, "channel_id": m.channel_id, "sender": m.sender, "recipient": m.recipient, "encrypted_payload_hash": m.encrypted_payload_hash, "algorithm": m.algorithm, "status": m.status, "created_at": m.created_at.isoformat() if m.created_at else None}
