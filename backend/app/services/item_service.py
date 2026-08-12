from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import EngineSetting, DetectionRule, IpReputation
from app.schemas.item import EngineSettings
from app.utils.helpers import paginate, create_audit_log

# ---------------------------------------------------------------------------
# Engine Settings
# ---------------------------------------------------------------------------

DEFAULT_ENGINE_SETTINGS = {
    "detectionSensitivity": settings.ENGINE_SENSITIVITY,
    "maxConcurrentScans": str(settings.MAX_CONCURRENT_SCANS),
    "autoQuarantine": "false" if not settings.AUTO_QUARANTINE else "true",
    "kafkaEnabled": "true" if settings.ENABLE_KAFKA else "false",
    "logRetentionDays": str(settings.LOG_RETENTION_DAYS),
}


def _bool_to_str(value) -> str:
    return "true" if value else "false"


def _str_to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_engine_settings(db: Session) -> EngineSettings:
    stored = {row.key: row.value for row in db.query(EngineSetting).all()}
    merged = {**DEFAULT_ENGINE_SETTINGS, **stored}

    return EngineSettings(
        detectionSensitivity=str(merged["detectionSensitivity"]).upper(),
        maxConcurrentScans=int(merged["maxConcurrentScans"] or 0),
        autoQuarantine=_str_to_bool(merged["autoQuarantine"]),
        kafkaEnabled=_str_to_bool(merged["kafkaEnabled"]),
        logRetentionDays=int(merged["logRetentionDays"] or 30),
    )


def update_engine_settings(db: Session, payload: dict) -> EngineSettings:
    allowed_keys = set(DEFAULT_ENGINE_SETTINGS.keys())

    def _normalize(key: str, value):
        if key == "detectionSensitivity":
            val = str(value).upper()
            if val not in {"LOW", "MEDIUM", "HIGH"}:
                raise HTTPException(status_code=400, detail="detectionSensitivity must be LOW, MEDIUM or HIGH")
            return val
        if key in {"maxConcurrentScans", "logRetentionDays"}:
            return str(int(value))
        return _bool_to_str(value)

    for key, value in payload.items():
        if key not in allowed_keys:
            continue
        row = db.query(EngineSetting).filter(EngineSetting.key == key).first()
        normalized = _normalize(key, value)
        if row:
            row.value = normalized
        else:
            db.add(EngineSetting(key=key, value=normalized))
    db.commit()

    return get_engine_settings(db)


# ---------------------------------------------------------------------------
# Detection Rules
# ---------------------------------------------------------------------------

def list_rules(db: Session, page: int = 1, limit: int = 20) -> tuple[list, int]:
    query = db.query(DetectionRule).order_by(DetectionRule.created_at.desc())
    return paginate(db, query, page, limit)


def get_rule(db: Session, rule_id: int) -> DetectionRule:
    rule = db.query(DetectionRule).filter(DetectionRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


def create_rule(db: Session, data: dict) -> DetectionRule:
    existing = db.query(DetectionRule).filter(DetectionRule.name == data.get("name")).first()
    if existing:
        raise HTTPException(status_code=400, detail="A rule with that name already exists")

    rule = DetectionRule(
        name=data["name"],
        description=data.get("description"),
        severity=(data.get("severity") or "MEDIUM").upper(),
        pattern=data.get("pattern"),
        is_active=bool(data.get("is_active", True)),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(db: Session, rule_id: int, data: dict) -> DetectionRule:
    rule = get_rule(db, rule_id)
    for field in ("name", "description", "pattern", "is_active"):
        if field in data:
            setattr(rule, field, data[field])
    if "severity" in data:
        rule.severity = str(data["severity"]).upper()
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int) -> None:
    rule = get_rule(db, rule_id)
    db.delete(rule)
    db.commit()


# ---------------------------------------------------------------------------
# IP Reputation
# ---------------------------------------------------------------------------

def get_ip_reputation(db: Session, ip_address: str) -> Optional[IpReputation]:
    return db.query(IpReputation).filter(IpReputation.ip_address == ip_address).first()


def upsert_ip_reputation(db: Session, data: dict) -> IpReputation:
    ip = data.get("ip_address")
    if not ip:
        raise HTTPException(status_code=400, detail="ip_address is required")

    row = get_ip_reputation(db, ip)
    if not row:
        row = IpReputation(ip_address=ip, threat_score=0.0)
        db.add(row)

    if "threat_score" in data:
        row.threat_score = float(data["threat_score"])
    if "is_blocked" in data:
        row.is_blocked = bool(data["is_blocked"])
    if "category" in data:
        row.category = data["category"]
    if "notes" in data:
        row.notes = data["notes"]

    db.commit()
    db.refresh(row)
    return row


def list_ip_reputation(db: Session, page: int = 1, limit: int = 20) -> tuple[list, int]:
    query = db.query(IpReputation).order_by(IpReputation.threat_score.desc())
    return paginate(db, query, page, limit)


def audit(db: Session, action: str, actor: Optional[str] = None, resource: Optional[str] = None, details: Optional[str] = None, ip_address: Optional[str] = None):
    """Thin wrapper so admin endpoints can record audit events without importing utils directly."""
    return create_audit_log(db, action, actor, resource, details, ip_address)
