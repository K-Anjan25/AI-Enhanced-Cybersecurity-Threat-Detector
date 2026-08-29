"""Phase 137: Universal Language service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.universal_language import UniversalLanguageModel, Translation, UniversalThreat
import hashlib

def _now():
    return datetime.now(timezone.utc)

def create_model(db: Session, org_id: int, name: str) -> UniversalLanguageModel:
    model = UniversalLanguageModel(org_id=org_id, name=name, language_type="threat", supported_formats=["stix","misp","ocsf","sigma","yara","openioc","custom_alien"], translation_accuracy=95.5, status="active")
    db.add(model)
    db.commit()
    db.refresh(model)
    return model

def list_models(db: Session, org_id: int) -> List[UniversalLanguageModel]:
    return db.query(UniversalLanguageModel).filter(UniversalLanguageModel.org_id == org_id).all()

def translate(db: Session, org_id: int, model_id: int, source_format: str, target_format: str, content: Dict[str, Any]) -> Translation:
    model = db.query(UniversalLanguageModel).filter(UniversalLanguageModel.id == model_id, UniversalLanguageModel.org_id == org_id).first()
    if not model:
        raise ValueError("Model not found")
    # Mock translation: STIX to Sigma
    translated = {"translated_from": source_format, "to": target_format, "original_hash": hashlib.sha256(str(content).encode()).hexdigest()[:8], "content": f"Translated {source_format} to {target_format}: {content}"}
    trans = Translation(model_id=model_id, org_id=org_id, source_format=source_format, target_format=target_format, source_content=content, translated_content=translated, confidence=0.92)
    db.add(trans)
    db.commit()
    db.refresh(trans)
    # Universal threat
    ut = UniversalThreat(org_id=org_id, universal_id=f"U-{hashlib.sha256(str(content).encode()).hexdigest()[:8]}", threat_name=f"Universal threat from {source_format}", representations_json={source_format: content, target_format: translated}, severity="HIGH")
    db.add(ut)
    db.commit()
    return trans

def serialize_model(m: UniversalLanguageModel) -> Dict[str, Any]:
    return {"id": m.id, "name": m.name, "language_type": m.language_type, "supported_formats": m.supported_formats, "translation_accuracy": m.translation_accuracy, "status": m.status}
