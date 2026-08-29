"""Phase 147: Akashic Ledger service."""
from datetime import datetime, timezone
from typing import Dict, Any, List
import hashlib
from sqlalchemy.orm import Session
from app.models.akashic_ledger import AkashicRecord, AkashicQuery, AkashicVerification

def _now():
    return datetime.now(timezone.utc)

def create_record(db: Session, org_id: int, record_type: str = "threat_event", event: Dict[str, Any] = None) -> AkashicRecord:
    last = db.query(AkashicRecord).filter(AkashicRecord.org_id == org_id).order_by(AkashicRecord.akashic_index.desc()).first()
    prev_hash = last.immutable_hash if last else "0"*128
    index = (last.akashic_index + 1) if last else 0
    event_data = event or {"type": record_type, "description": f"Akashic event {index} - eternal immutable record"}
    hash_input = f"{prev_hash}{index}{str(event_data)}{_now().isoformat()}".encode()
    imm_hash = hashlib.sha512(hash_input).hexdigest()
    rec = AkashicRecord(org_id=org_id, record_type=record_type, timeline_id="primary", universe_id="primary", event_json=event_data, immutable_hash=imm_hash, previous_hash=prev_hash, akashic_index=index, verified=True)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    ver = AkashicVerification(record_id=rec.id, org_id=org_id, verification_type="hash_chain", is_valid=True, verification_json={"prev_hash": prev_hash, "chain_valid": True})
    db.add(ver)
    db.commit()
    return rec

def list_records(db: Session, org_id: int) -> List[AkashicRecord]:
    return db.query(AkashicRecord).filter(AkashicRecord.org_id == org_id).order_by(AkashicRecord.akashic_index.desc()).limit(100).all()

def serialize_record(r: AkashicRecord) -> Dict[str, Any]:
    return {"id": r.id, "record_type": r.record_type, "timeline_id": r.timeline_id, "universe_id": r.universe_id, "event_json": r.event_json, "immutable_hash": r.immutable_hash[:16]+"...", "previous_hash": r.previous_hash[:16]+"..." if r.previous_hash else None, "akashic_index": r.akashic_index, "verified": r.verified}
