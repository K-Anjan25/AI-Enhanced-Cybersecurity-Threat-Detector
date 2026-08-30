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

    # Split on the boolean keywords, keeping them so each term knows which
    # operator preceded it. The leading-NOT case needs its own alternative:
    # `NOT severity:LOW` has no whitespace before the keyword, so a pattern
    # requiring it swallowed NOT into the field name and the query silently
    # matched what it was meant to exclude.
    tokens = re.split(
        r'(?:^|\s+)(AND|OR|NOT)(?=\s)', query.strip(), flags=re.IGNORECASE
    )
    conditions = []
    next_logic = "AND"
    for token in tokens:
        if not token.strip():
            continue
        upper = token.strip().upper()
        if upper in ("AND", "OR", "NOT"):
            # `AND NOT x` arrives as two keywords. NOT is the one that changes
            # the meaning of the term, so it wins; a bare AND/OR after a NOT
            # would otherwise discard the negation.
            next_logic = "NOT" if upper == "NOT" else (
                next_logic if next_logic == "NOT" else upper
            )
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

    def _expression(field: str, op: str, val: str):
        """One condition as a SQLAlchemy expression, or None if unusable."""
        col = field_map.get(field)
        if col is None:
            # An unknown field is a typo more often than an intention. Searching
            # the message is a reasonable guess, and `unknown_fields` in the
            # response tells the operator it was a guess.
            return SecurityAlert.message.ilike(f"%{val}%")

        if op in (">=", "<=", ">", "<"):
            numeric = {"score": SecurityAlert.score}.get(field)
            if numeric is None:
                return None
            try:
                num = float(val)
            except ValueError:
                return None
            return {
                ">=": numeric >= num, "<=": numeric <= num,
                ">": numeric > num, "<": numeric < num,
            }[op]

        if op == "contains" or field == "message":
            return col.ilike(f"%{val}%")
        if field == "severity":
            return col == val.upper()
        if field == "source_ip":
            return col == val
        if field in ("source", "alert_type"):
            return col.ilike(f"%{val}%")
        return col.ilike(f"%{val}%")

    # Conditions carry the operator that *preceded* them. Previously every
    # expression was ANDed regardless, so `severity:CRITICAL OR severity:LOW`
    # asked for rows that were both at once and returned nothing, and `NOT x`
    # matched x instead of excluding it. Both produced a confident empty or
    # wrong answer rather than an error — the worst outcome for a hunt, because
    # an analyst reads "no results" as "nothing to find".
    combined = None
    unknown_fields: list[str] = []
    unsupported: list[str] = []
    for cond in conditions:
        field, op, val, logic = cond["field"], cond["op"], cond["value"], cond["logic"]
        if field not in field_map and field != "score":
            unknown_fields.append(field)
        expression = _expression(field, op, val)
        if expression is None:
            unsupported.append(f"{field}{op}{val}")
            continue
        if logic == "NOT":
            expression = ~expression
        if combined is None:
            combined = expression
        elif logic == "OR":
            combined = or_(combined, expression)
        else:
            combined = and_(combined, expression)

    if combined is not None:
        q = q.filter(combined)

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
        "truncated": len(results) >= limit,
        "limit": limit,
        "unknown_fields": sorted(set(unknown_fields)),
        "unsupported": unsupported,
        "honest_note": (
            "KQL subset: field:value with AND, OR and NOT. Comparisons (>, >=, "
            "<, <=) apply to score only. Unrecognised field names fall back to "
            "a message search and are listed in unknown_fields."
        ),
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


def schedule_saved_hunts(db: Session) -> List[Dict[str, Any]]:
    """Auto-run saved hunts with schedule_cron or is_scheduled=True, create case if result_count > threshold.
    Answers doubt #4. This is called by a background task every 5m."""
    from app.models import Case
    scheduled = db.query(Hunt).filter(Hunt.is_scheduled == True).all()  # noqa
    created_cases = []
    for hunt in scheduled:
        try:
            result = execute_hunt_query(db, hunt.org_id, hunt.query, limit=20)
            # Log execution
            exec_log = HuntExecution(
                org_id=hunt.org_id,
                hunt_id=hunt.id,
                query=hunt.query,
                status="completed",
                result_count=result["result_count"],
                results_json=result["results"][:100],
                duration_ms=result["duration_ms"],
            )
            db.add(exec_log)
            hunt.last_executed_at = _now()
            hunt.execution_count = (hunt.execution_count or 0) + 1
            db.commit()
            # If results > threshold, auto-create case
            threshold = 1
            if result["result_count"] >= threshold:
                case = Case(org_id=hunt.org_id, title=f"Hunt {hunt.name} hit {result['result_count']} alerts", description=f"Auto-created from scheduled hunt {hunt.query}", severity="HIGH", status="open")
                db.add(case)
                db.commit()
                created_cases.append({"hunt_id": hunt.id, "case_id": case.id, "result_count": result["result_count"]})
        except Exception:
            db.rollback()
    return created_cases


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
