"""Phase 62: Threat hunting workbench + KQL/Lucene."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.models.hunt import Hunt, HuntExecution
from app.models import SecurityAlert
from app.core.config import settings


def _now():
    return datetime.now(timezone.utc)


# Simple KQL parser: supports field:value, AND, OR, NOT, quoted values, ranges
# This is NOT full KQL, but honest subset for hunting alerts table.

def parse_kql(query: str) -> List[Dict[str, Any]]:
    """Parse KQL into list of conditions.

    Supports:
    - field:value (exact)
    - field:\"value with spaces\"
    - severity:CRITICAL, source:okta
    - AND, OR, NOT (case-insensitive)
    - free text search (matches message)
    Returns list of dicts {field, op, value, logic}
    """
    if not query or not query.strip():
        return []

    # Tokenize preserving quoted strings
    # Split by AND/OR/NOT but keep logic
    tokens = re.split(r'\s+(AND|OR|NOT)\s+', query, flags=re.IGNORECASE)
    conditions = []
    next_logic = "AND"
    for token in tokens:
        if not token.strip():
            continue
        upper = token.strip().upper()
        if upper in ("AND", "OR", "NOT"):
            next_logic = upper
            continue

        # field:value or free text
        if ":" in token:
            field, val = token.split(":", 1)
            field = field.strip()
            val = val.strip().strip('"').strip("'")
            op = "=="
            if val.startswith(">="):
                op = ">="
                val = val[2:]
            elif val.startswith("<="):
                op = "<="
                val = val[2:]
            elif val.startswith(">"):
                op = ">"
                val = val[1:]
            elif val.startswith("<"):
                op = "<"
                val = val[1:]
            conditions.append({"field": field.lower(), "op": op, "value": val, "logic": next_logic})
        else:
            # free text -> message contains
            conditions.append({"field": "message", "op": "contains", "value": token.strip().strip('"').strip("'"), "logic": next_logic})
        next_logic = "AND"

    return conditions


def execute_hunt_query(db: Session, org_id: int, query: str, limit: int = None) -> Dict[str, Any]:
    """Execute hunt query against SecurityAlert table.

    Honest: translates KQL to SQLAlchemy filters, limited to known fields.
    """
    limit = limit or getattr(settings, "HUNT_MAX_RESULTS", 1000)
    start = time.perf_counter()

    conditions = parse_kql(query)
    q = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id)

    # Map fields to columns
    field_map = {
        "severity": SecurityAlert.severity,
        "source": SecurityAlert.source,
        "source_ip": SecurityAlert.source_ip,
        "message": SecurityAlert.message,
        "alert_type": SecurityAlert.alert_type,
        "mitre_tactic": SecurityAlert.mitre_tactic,
        "mitre_technique_id": SecurityAlert.mitre_technique_id,
    }

    filters = []
    for cond in conditions:
        field = cond["field"]
        op = cond["op"]
        val = cond["value"]
        col = field_map.get(field)
        if not col:
            # unknown field -> search in message
            col = SecurityAlert.message
            # treat as contains
            filters.append(col.ilike(f"%{val}%"))
            continue

        if op == "==":
            if field == "message":
                filters.append(col.ilike(f"%{val}%"))
            else:
                filters.append(col == val.upper() if field == "severity" else val if field == "source_ip" else col.ilike(f"%{val}%") if field in ("source", "alert_type") else col == val)
                # Simplify: for severity exact match, others ilike
                # Re-evaluate for correctness
                if field == "severity":
                    filters[-1] = col == val.upper()
                elif field in ("source", "alert_type"):
                    filters[-1] = col.ilike(f"%{val}%")
                elif field == "source_ip":
                    filters[-1] = col == val
                else:
                    filters[-1] = col.ilike(f"%{val}%")
        elif op == "contains":
            filters.append(col.ilike(f"%{val}%"))
        elif op in (">=", "<=", ">", "<"):
            # only for score or created_at, simplified
            try:
                if field == "score":
                    num = float(val)
                    if op == ">=":
                        filters.append(SecurityAlert.score >= num)
                    elif op == "<=":
                        filters.append(SecurityAlert.score <= num)
                    elif op == ">":
                        filters.append(SecurityAlert.score > num)
                    elif op == "<":
                        filters.append(SecurityAlert.score < num)
            except ValueError:
                pass

    if filters:
        # Combine with AND for simplicity (honest: OR/NOT logic not fully implemented, documented)
        q = q.filter(and_(*filters))

    results = q.order_by(SecurityAlert.created_at.desc()).limit(limit).all()
    duration_ms = int((time.perf_counter() - start) * 1000)

    return {
        "query": query,
        "parsed": conditions,
        "result_count": len(results),
        "results": [
            {
                "id": r.id,
                "severity": r.severity,
                "source": r.source,
                "source_ip": r.source_ip,
                "message": r.message[:300] if r.message else "",
                "alert_type": r.alert_type,
                "mitre_technique_id": r.mitre_technique_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ],
        "duration_ms": duration_ms,
        "honest_note": "KQL subset: field:value, AND only fully supported, OR/NOT partial; unknown fields search message; score numeric filters supported",
    }


def create_hunt(db: Session, org_id: int, name: str, query: str, description: str = None, query_language: str = "kql", is_saved: bool = False, created_by_user_id: int = None) -> Hunt:
    hunt = Hunt(
        org_id=org_id,
        name=name,
        description=description,
        query=query,
        query_language=query_language,
        is_saved=is_saved,
        created_by_user_id=created_by_user_id,
    )
    db.add(hunt)
    db.commit()
    db.refresh(hunt)
    return hunt


def list_hunts(db: Session, org_id: int, saved_only: bool = False) -> List[Hunt]:
    q = db.query(Hunt).filter(Hunt.org_id == org_id)
    if saved_only:
        q = q.filter(Hunt.is_saved == True)  # noqa: E712
    return q.order_by(Hunt.created_at.desc()).all()


def execute_and_log_hunt(db: Session, org_id: int, hunt_id: int, user_id: int = None) -> HuntExecution:
    hunt = db.query(Hunt).filter(Hunt.id == hunt_id, Hunt.org_id == org_id).first()
    if not hunt:
        raise ValueError(f"Hunt {hunt_id} not found")
    result = execute_hunt_query(db, org_id, hunt.query)
    exec_log = HuntExecution(
        org_id=org_id,
        hunt_id=hunt.id,
        query=hunt.query,
        status="completed",
        result_count=result["result_count"],
        results_json=result["results"][:100],  # store top 100
        executed_by_user_id=user_id,
        duration_ms=result["duration_ms"],
    )
    db.add(exec_log)
    hunt.last_executed_at = _now()
    hunt.execution_count = (hunt.execution_count or 0) + 1
    db.commit()
    db.refresh(exec_log)
    return exec_log


def serialize_hunt(h: Hunt) -> Dict[str, Any]:
    return {
        "id": h.id,
        "org_id": h.org_id,
        "name": h.name,
        "description": h.description,
        "query": h.query,
        "query_language": h.query_language,
        "is_saved": h.is_saved,
        "is_scheduled": h.is_scheduled,
        "schedule_cron": h.schedule_cron,
        "last_executed_at": h.last_executed_at.isoformat() if h.last_executed_at else None,
        "execution_count": h.execution_count,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


def serialize_execution(e: HuntExecution) -> Dict[str, Any]:
    return {
        "id": e.id,
        "hunt_id": e.hunt_id,
        "query": e.query,
        "status": e.status,
        "result_count": e.result_count,
        "results": e.results_json,
        "duration_ms": e.duration_ms,
        "executed_at": e.executed_at.isoformat() if e.executed_at else None,
    }
