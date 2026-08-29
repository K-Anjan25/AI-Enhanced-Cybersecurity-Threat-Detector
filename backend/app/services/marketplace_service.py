"""Phase 75: SOAR Marketplace."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.marketplace import MarketplacePlaybook, MarketplaceInstall
from app.models.soar import SoarPlaybook


def _now():
    return datetime.now(timezone.utc)


def list_marketplace(q: str = None, category: str = None) -> List[MarketplacePlaybook]:
    # In real would query DB, but we seed defaults
    return []


def list_marketplace_db(db: Session, category: str = None, search: str = None) -> List[MarketplacePlaybook]:
    query = db.query(MarketplacePlaybook).filter(MarketplacePlaybook.is_public == True)
    if category:
        query = query.filter(MarketplacePlaybook.category == category)
    if search:
        query = query.filter(MarketplacePlaybook.name.ilike(f"%{search}%"))
    return query.order_by(MarketplacePlaybook.downloads.desc()).limit(50).all()


def seed_marketplace(db: Session) -> List[MarketplacePlaybook]:
    """Seed default marketplace playbooks if empty."""
    existing = db.query(MarketplacePlaybook).count()
    if existing > 0:
        return db.query(MarketplacePlaybook).all()
    defaults = [
        {"name": "Auto Block Malicious IP", "description": "Block IP via firewall if threat intel high confidence", "category": "containment", "tags": ["ip", "firewall"], "playbook_json": {"steps": [{"action": "block_ip", "target": "{{source_ip}}"}]}, "is_verified": True},
        {"name": "Enrich with VirusTotal", "description": "Enrich alert with VT, AbuseIPDB", "category": "enrichment", "tags": ["enrichment", "vt"], "playbook_json": {"steps": [{"action": "enrich_ip"}, {"action": "enrich_domain"}]}, "is_verified": True},
        {"name": "Isolate Host", "description": "Isolate compromised host via EDR", "category": "containment", "tags": ["edr", "isolate"], "playbook_json": {"steps": [{"action": "isolate_host"}]}, "is_verified": True},
        {"name": "Phishing Response", "description": "Full phishing triage: extract URLs, check reputation, quarantine email", "category": "response", "tags": ["phishing"], "playbook_json": {"steps": [{"action": "extract_urls"}, {"action": "check_reputation"}, {"action": "quarantine_email"}]}, "is_verified": True},
    ]
    created = []
    for d in defaults:
        pb = MarketplacePlaybook(name=d["name"], description=d["description"], category=d["category"], tags=d["tags"], playbook_json=d["playbook_json"], is_verified=d["is_verified"], is_public=True, downloads=100, rating=4.8)
        db.add(pb)
        created.append(pb)
    db.commit()
    for c in created:
        db.refresh(c)
    return created


def install_playbook(db: Session, org_id: int, marketplace_id: int, installed_by_user_id: int = None) -> MarketplaceInstall:
    mp = db.query(MarketplacePlaybook).filter(MarketplacePlaybook.id == marketplace_id).first()
    if not mp:
        raise ValueError("Marketplace playbook not found")
    # Create local SoarPlaybook
    local = SoarPlaybook(org_id=org_id, name=mp.name, description=mp.description, playbook_json=mp.playbook_json, is_active=True, created_by_user_id=installed_by_user_id)
    db.add(local)
    db.commit()
    db.refresh(local)

    mp.downloads += 1
    db.commit()

    install = MarketplaceInstall(org_id=org_id, playbook_id=mp.id, installed_by_user_id=installed_by_user_id, local_playbook_id=local.id)
    db.add(install)
    db.commit()
    db.refresh(install)
    return install


def serialize_mp(pb: MarketplacePlaybook) -> Dict[str, Any]:
    return {"id": pb.id, "name": pb.name, "description": pb.description, "category": pb.category, "author": pb.author, "version": pb.version, "tags": pb.tags, "downloads": pb.downloads, "rating": pb.rating, "is_verified": pb.is_verified, "created_at": pb.created_at.isoformat() if pb.created_at else None}


def serialize_install(inst: MarketplaceInstall) -> Dict[str, Any]:
    return {"id": inst.id, "org_id": inst.org_id, "playbook_id": inst.playbook_id, "local_playbook_id": inst.local_playbook_id, "installed_at": inst.installed_at.isoformat() if inst.installed_at else None}
