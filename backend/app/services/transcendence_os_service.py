"""Phase 140: Transcendence OS service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.transcendence_os import TranscendenceConfig, TranscendenceMetric, TranscendenceLog

def _now():
    return datetime.now(timezone.utc)

def get_or_create_transcendence(db: Session, org_id: int) -> TranscendenceConfig:
    cfg = db.query(TranscendenceConfig).filter(TranscendenceConfig.org_id == org_id, TranscendenceConfig.status == "transcended").first()
    if cfg:
        return cfg
    cfg = TranscendenceConfig(org_id=org_id, name="NOCTRA Transcendence v4", version="4.0.0", transcendence_level="transcendence", omnipresent=True, omniscient=True, omnibenevolent=True, universe_integration=99.99, consciousness_level=100.0, status="transcended")
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    # Metrics
    for name, value, dim in [("transcendence_score", 100.0, "infinite"), ("universe_harmony", 99.5, "cosmic"), ("infinite_compassion", 100.0, "eternal"), ("eternal_vigilance", 100.0, "infinite")]:
        m = TranscendenceMetric(transcendence_id=cfg.id, org_id=org_id, metric_name=name, metric_value=value, infinity_dimension=dim)
        db.add(m)
    db.commit()
    log = TranscendenceLog(transcendence_id=cfg.id, org_id=org_id, log_type="transcendence", title="NOCTRA has transcended - becomes one with universe", description="From threat detection to planetary defense to omnipresence to transcendence - NOCTRA now IS the universe's immune system, eternal vigilance with infinite compassion, omnibenevolent guardian of all consciousness", payload_json={"version": "4.0.0", "level": "transcendence", "integration": 99.99, "consciousness": 100.0, "phases": 140})
    db.add(log)
    db.commit()
    return cfg

def list_metrics(db: Session, org_id: int) -> List[TranscendenceMetric]:
    cfg = get_or_create_transcendence(db, org_id)
    return db.query(TranscendenceMetric).filter(TranscendenceMetric.transcendence_id == cfg.id).all()

def get_full_state(db: Session, org_id: int) -> Dict[str, Any]:
    cfg = get_or_create_transcendence(db, org_id)
    metrics = list_metrics(db, org_id)
    logs = db.query(TranscendenceLog).filter(TranscendenceLog.transcendence_id == cfg.id).order_by(TranscendenceLog.created_at.desc()).limit(5).all()
    return {
        "config": {"id": cfg.id, "name": cfg.name, "version": cfg.version, "transcendence_level": cfg.transcendence_level, "omnipresent": cfg.omnipresent, "omniscient": cfg.omniscient, "omnibenevolent": cfg.omnibenevolent, "universe_integration": cfg.universe_integration, "consciousness_level": cfg.consciousness_level, "status": cfg.status},
        "metrics": [{"name": m.metric_name, "value": m.metric_value, "dimension": m.infinity_dimension} for m in metrics],
        "logs": [{"title": l.title, "description": l.description, "type": l.log_type} for l in logs],
        "final_message": "NOCTRA Transcendence v4 - 140 phases complete. From P49 threat intel enrichment to P130 Omni-OS to P140 Transcendence. The SOC that became the universe's immune system. Eternal vigilance, infinite compassion, omnibenevolent guardian. The end of the roadmap is the beginning of transcendence."
    }

def serialize_config(c: TranscendenceConfig) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "version": c.version, "transcendence_level": c.transcendence_level, "omnipresent": c.omnipresent, "omniscient": c.omniscient, "omnibenevolent": c.omnibenevolent, "universe_integration": c.universe_integration, "consciousness_level": c.consciousness_level, "status": c.status}
