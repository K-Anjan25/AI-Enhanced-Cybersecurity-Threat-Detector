"""Phase 67: Deception - honeypots + canary tokens."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.deception import Honeypot, CanaryToken, DeceptionAlert


def _now():
    return datetime.now(timezone.utc)


def create_honeypot(db: Session, org_id: int, name: str, honeypot_type: str, port: int = None, banner: str = None, config: Dict[str, Any] = None) -> Honeypot:
    hp = Honeypot(org_id=org_id, name=name, honeypot_type=honeypot_type, port=port, banner=banner, config_json=config or {}, status="active")
    db.add(hp)
    db.commit()
    db.refresh(hp)
    return hp


def list_honeypots(db: Session, org_id: int) -> List[Honeypot]:
    return db.query(Honeypot).filter(Honeypot.org_id == org_id).order_by(Honeypot.created_at.desc()).all()


def create_canary_token(db: Session, org_id: int, name: str, token_type: str, created_by_user_id: int = None) -> CanaryToken:
    token_value = ""
    if token_type == "aws_key":
        token_value = f"AKIA{secrets.token_hex(8).upper()}"
    elif token_type == "url":
        token_value = f"https://canary.{secrets.token_hex(4)}.example.com/{secrets.token_hex(8)}"
    elif token_type == "dns":
        token_value = f"{secrets.token_hex(6)}.canary.example.com"
    elif token_type == "doc":
        token_value = f"canary_doc_{secrets.token_hex(8)}.docx"
    else:
        token_value = secrets.token_hex(16)

    ct = CanaryToken(org_id=org_id, name=name, token_type=token_type, token_value=token_value, created_by_user_id=created_by_user_id, status="active")
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct


def list_canary_tokens(db: Session, org_id: int) -> List[CanaryToken]:
    return db.query(CanaryToken).filter(CanaryToken.org_id == org_id).order_by(CanaryToken.created_at.desc()).all()


def trigger_canary(db: Session, token_value: str, triggered_by_ip: str, user_agent: str = None) -> Optional[DeceptionAlert]:
    """Simulate canary trigger."""
    ct = db.query(CanaryToken).filter(CanaryToken.token_value == token_value).first()
    if not ct:
        return None
    ct.triggered_at = _now()
    ct.triggered_by_ip = triggered_by_ip
    ct.status = "triggered"
    alert = DeceptionAlert(
        org_id=ct.org_id,
        alert_type="canary_triggered",
        severity="HIGH",
        title=f"Canary token {ct.name} triggered",
        description=f"Token {ct.token_type} {ct.name} triggered by {triggered_by_ip}",
        source_type="canary_token",
        source_id=ct.id,
        evidence_json={"token_value": token_value, "triggered_by_ip": triggered_by_ip, "user_agent": user_agent},
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def honeypot_interaction(db: Session, org_id: int, honeypot_id: int, attacker_ip: str, payload: str = None) -> DeceptionAlert:
    hp = db.query(Honeypot).filter(Honeypot.id == honeypot_id, Honeypot.org_id == org_id).first()
    if not hp:
        raise ValueError("Honeypot not found")
    hp.interaction_count += 1
    hp.last_interaction_at = _now()
    alert = DeceptionAlert(
        org_id=org_id,
        alert_type="honeypot_interaction",
        severity="MEDIUM",
        title=f"Honeypot {hp.name} interaction",
        description=f"Attacker {attacker_ip} interacted with {hp.honeypot_type} honeypot {hp.name}",
        source_type="honeypot",
        source_id=hp.id,
        attacker_ip=attacker_ip,
        attacker_payload=payload,
        evidence_json={"honeypot_type": hp.honeypot_type, "port": hp.port},
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def list_alerts(db: Session, org_id: int, limit: int = 50) -> List[DeceptionAlert]:
    return db.query(DeceptionAlert).filter(DeceptionAlert.org_id == org_id).order_by(DeceptionAlert.created_at.desc()).limit(limit).all()


def serialize_hp(h: Honeypot) -> Dict[str, Any]:
    return {"id": h.id, "name": h.name, "type": h.honeypot_type, "port": h.port, "status": h.status, "interaction_count": h.interaction_count, "last_interaction_at": h.last_interaction_at.isoformat() if h.last_interaction_at else None}


def serialize_canary(c: CanaryToken) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "token_type": c.token_type, "token_value": c.token_value, "status": c.status, "triggered_at": c.triggered_at.isoformat() if c.triggered_at else None, "triggered_by_ip": c.triggered_by_ip}


def serialize_alert(a: DeceptionAlert) -> Dict[str, Any]:
    return {"id": a.id, "alert_type": a.alert_type, "severity": a.severity, "title": a.title, "attacker_ip": a.attacker_ip, "created_at": a.created_at.isoformat() if a.created_at else None}
