"""Entity extraction and attack-graph building.

Extracts normalized threat entities (IPs, domains, hashes, emails, files) from
alerts and links them into a directed graph. The graph lets analysts pivot from
an indicator (e.g. a C2 IP) to every other indicator and alert it touched.
"""

from __future__ import annotations

import ipaddress
import re
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Entity, EntityLink, SecurityAlert
from app.utils.helpers import paginate

# Deterministic fingerprints (SHA-256-ish MD5/SHA1/SHA256/short hex blobs).
_HASH_RE = re.compile(r"\b(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64})\b")
_DOMAIN_RE = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Common malware file-name markers (case-insensitive).
_FILE_MARKERS = ("\.exe", "\.dll", "\.vbs", "\.js", "\.ps1", "\.scr", "\.bat")


def _is_ip(candidate: str) -> bool:
    try:
        ipaddress.ip_address(candidate)
        return True
    except ValueError:
        return False


def extract_entities(message: str, source_ip: Optional[str], dst_port: Optional[str] = None) -> list[dict]:
    """Extract candidate entities from an alert message + source IP.

    Returns a list of ``{entity_type, value, meta}`` dicts, deduplicated by
    (type, value). Malicious-looking domains / hashes / files get a ``meta``
    hint (e.g. ``{"kind": "suspicious_extension"}``) used to seed risk.
    """
    text = message or ""
    found: dict[tuple[str, str], dict] = {}

    for match in _EMAIL_RE.findall(text):
        key = ("email", match.lower())
        found.setdefault(key, {"entity_type": "email", "value": match.lower()})

    for match in _HASH_RE.findall(text):
        key = ("hash", match.lower())
        found.setdefault(key, {"entity_type": "hash", "value": match.lower(), "meta": {"algorithm": _hash_algo(match)}})

    for match in _DOMAIN_RE.findall(text):
        # Skip values that are actually email-local parts / IP-like.
        if _is_ip(match):
            continue
        key = ("domain", match.lower())
        found.setdefault(key, {"entity_type": "domain", "value": match.lower(), "meta": {"kind": "domain"}})

    # File names with suspicious extensions.
    for marker in _FILE_MARKERS:
        for match in re.findall(rf"\b\S+{marker}", text, flags=re.IGNORECASE):
            key = ("file", match.lower())
            found.setdefault(key, {"entity_type": "file", "value": match.lower(), "meta": {"kind": "suspicious_file"}})

    if source_ip:
        found.setdefault(("ip", source_ip), {"entity_type": "ip", "value": source_ip})
    if dst_port:
        found.setdefault(("ip", dst_port), {"entity_type": "ip", "value": dst_port})

    return list(found.values())


def _hash_algo(value: str) -> str:
    if len(value) == 32:
        return "md5"
    if len(value) == 40:
        return "sha1"
    return "sha256"


def upsert_entity(db: Session, entity_type: str, value: str, org_id: Optional[int], meta: Optional[dict] = None) -> Entity:
    """Create-or-update an entity, incrementing its occurrence + risk and
    bumping ``last_seen``. Returns the entity row."""
    entity = (
        db.query(Entity)
        .filter(Entity.org_id == org_id, Entity.entity_type == entity_type, Entity.value == value)
        .first()
    )
    if entity is None:
        entity = Entity(
            org_id=org_id,
            entity_type=entity_type,
            value=value,
            risk_score=0.0,
            occurrences=1,
            meta=meta or {},
        )
        db.add(entity)
        db.flush()
        return entity

    entity.occurrences += 1
    if meta:
        merged = dict(entity.meta or {})
        merged.update(meta)
        entity.meta = merged
    return entity


def _relation_for(alert_type: str) -> str:
    if alert_type == "network":
        return "communicates"
    if alert_type == "email":
        return "delivers"
    return "derives_from"


def link_entities(db: Session, source: Entity, target: Entity, alert: SecurityAlert, relation: str) -> None:
    """Create a directed link source -> target for a shared alert, if the pair
    is not already linked in this direction."""
    if source.id == target.id:
        return
    exists = (
        db.query(EntityLink)
        .filter(EntityLink.org_id == alert.org_id, EntityLink.source_entity_id == source.id, EntityLink.target_entity_id == target.id)
        .first()
    )
    if exists:
        return
    db.add(EntityLink(
        org_id=alert.org_id,
        source_entity_id=source.id,
        target_entity_id=target.id,
        relation=relation,
        source_alert_id=alert.id,
    ))


def index_alert(db: Session, alert: SecurityAlert) -> None:
    """Extract entities + links for a persisted alert (best-effort).

    Creates a primary entity for the alert's own identity, then links every
    extracted indicator to it. Non-fatal: failures are swallowed so alert
    ingestion never breaks because of graph bookkeeping.
    """
    try:
        source_ip = alert.source_ip
        indicators = extract_entities(alert.message or "", source_ip, None)

        primary = upsert_entity(db, "ip", source_ip, alert.org_id) if source_ip else None
        if primary is not None and alert.score is not None:
            primary.risk_score = max(primary.risk_score, float(alert.score))
        if primary is not None:
            db.flush()

        relation = _relation_for(alert.alert_type or "system_log")
        for indicator in indicators:
            entity = upsert_entity(db, indicator["entity_type"], indicator["value"], alert.org_id, indicator.get("meta"))
            if alert.score is not None:
                entity.risk_score = max(entity.risk_score, float(alert.score))
            db.flush()
            if primary is not None:
                link_entities(db, primary, entity, alert, relation)
        db.flush()
    except Exception:
        db.rollback()


def list_entities(db: Session, page: int = 1, limit: int = 20, entity_type: str | None = None, org_id: int | None = None) -> tuple[list, int]:
    query = db.query(Entity)
    if org_id is not None:
        query = query.filter(Entity.org_id == org_id)
    if entity_type:
        query = query.filter(Entity.entity_type == entity_type)
    query = query.order_by(Entity.risk_score.desc(), Entity.last_seen.desc())
    return paginate(db, query, page, limit)


def get_entity(db: Session, entity_id: int, org_id: int | None = None) -> Entity | None:
    query = db.query(Entity).filter(Entity.id == entity_id)
    if org_id is not None:
        query = query.filter(Entity.org_id == org_id)
    return query.first()


def entity_graph(db: Session, entity_id: int, depth: int = 1, org_id: int | None = None) -> dict:
    """Return an adjacency payload for the attack-graph visualization.

    ``nodes`` lists entities; ``links`` lists directed edge pairs
    ``{source, target, relation}`` up to ``depth`` hops from the root.
    """
    root = get_entity(db, entity_id, org_id=org_id)
    if root is None:
        return {"root": None, "nodes": [], "links": []}

    seen: set[int] = set()
    nodes: dict[int, dict] = {}
    links: list[dict] = []

    frontier = [root]
    seen.add(root.id)
    for _ in range(max(1, depth)):
        nxt: list[Entity] = []
        for entity in frontier:
            edges = (
                db.query(EntityLink)
                .filter(EntityLink.source_entity_id == entity.id)
                .all()
            )
            for edge in edges:
                target = (
                    db.query(Entity)
                    .filter(Entity.id == edge.target_entity_id, Entity.org_id == org_id)
                    .first()
                )
                if target is None or target.id in seen:
                    continue
                seen.add(target.id)
                nodes[target.id] = serialize_entity(target)
                links.append({"source": entity.id, "target": target.id, "relation": edge.relation})
                nxt.append(target)
        frontier = nxt

    nodes[root.id] = serialize_entity(root)
    return {"root": root.id, "nodes": list(nodes.values()), "links": links}


def serialize_entity(entity: Entity) -> dict:
    return {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "value": entity.value,
        "risk_score": entity.risk_score,
        "occurrences": entity.occurrences,
        "meta": entity.meta,
        "first_seen": entity.first_seen.isoformat() if entity.first_seen else None,
        "last_seen": entity.last_seen.isoformat() if entity.last_seen else None,
    }
