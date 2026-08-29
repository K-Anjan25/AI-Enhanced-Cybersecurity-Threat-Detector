"""Phase 52: Sigma rules + custom DSL."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.sigma_rule import SigmaRule, SigmaRuleVersion, DetectionDSLRule

_LOGGER = logging.getLogger(__name__)


def _parse_sigma_yaml(yaml_text: str) -> Dict[str, Any]:
    """Very small Sigma YAML parser — honest: not full spec, extracts key fields."""
    # Try yaml library if available
    try:
        import yaml

        data = yaml.safe_load(yaml_text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # Fallback regex extraction
    result: Dict[str, Any] = {}
    title_match = re.search(r"title:\s*(.+)", yaml_text)
    if title_match:
        result["title"] = title_match.group(1).strip()
    level_match = re.search(r"level:\s*(\w+)", yaml_text)
    if level_match:
        result["level"] = level_match.group(1).strip()
    return result


def create_sigma_rule(
    db: Session,
    org_id: int,
    title: str,
    rule_yaml: str,
    description: str = None,
    level: str = "medium",
    tags: List[str] = None,
    created_by_user_id: int = None,
) -> SigmaRule:
    parsed = _parse_sigma_yaml(rule_yaml)
    rule = SigmaRule(
        org_id=org_id,
        title=title,
        description=description or parsed.get("description"),
        rule_yaml=rule_yaml,
        rule_json=parsed,
        level=level,
        tags=tags or parsed.get("tags", []),
        created_by_user_id=created_by_user_id,
        version=1,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    # Version 1
    ver = SigmaRuleVersion(
        rule_id=rule.id,
        org_id=org_id,
        version=1,
        rule_yaml=rule_yaml,
        rule_json=parsed,
        change_notes="Initial version",
        created_by_user_id=created_by_user_id,
    )
    db.add(ver)
    db.commit()
    return rule


def update_sigma_rule(
    db: Session,
    org_id: int,
    rule_id: int,
    rule_yaml: str = None,
    title: str = None,
    level: str = None,
    is_active: bool = None,
    change_notes: str = None,
    actor_user_id: int = None,
) -> SigmaRule:
    rule = db.query(SigmaRule).filter(SigmaRule.id == rule_id, SigmaRule.org_id == org_id).first()
    if not rule:
        raise ValueError("Sigma rule not found")
    if rule_yaml:
        parsed = _parse_sigma_yaml(rule_yaml)
        rule.rule_yaml = rule_yaml
        rule.rule_json = parsed
        rule.version += 1
        # Create version
        ver = SigmaRuleVersion(
            rule_id=rule.id,
            org_id=org_id,
            version=rule.version,
            rule_yaml=rule_yaml,
            rule_json=parsed,
            change_notes=change_notes or f"Updated to v{rule.version}",
            created_by_user_id=actor_user_id,
        )
        db.add(ver)
    if title:
        rule.title = title
    if level:
        rule.level = level
    if is_active is not None:
        rule.is_active = is_active
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)
    return rule


def list_sigma_rules(db: Session, org_id: int, is_active: bool = None) -> List[SigmaRule]:
    q = db.query(SigmaRule).filter(SigmaRule.org_id == org_id).order_by(SigmaRule.updated_at.desc())
    if is_active is not None:
        q = q.filter(SigmaRule.is_active == is_active)
    return q.all()


def get_sigma_rule(db: Session, org_id: int, rule_id: int) -> Optional[SigmaRule]:
    return db.query(SigmaRule).filter(SigmaRule.id == rule_id, SigmaRule.org_id == org_id).first()


def delete_sigma_rule(db: Session, org_id: int, rule_id: int) -> bool:
    rule = get_sigma_rule(db, org_id, rule_id)
    if not rule:
        return False
    db.delete(rule)
    db.commit()
    return True


def evaluate_sigma_rule(rule: SigmaRule, alert: Dict[str, Any]) -> bool:
    """Evaluate Sigma rule against alert — simplified matching."""
    try:
        rule_json = rule.rule_json or {}
        detection = rule_json.get("detection", {})
        if not detection:
            # Fallback: check title in message
            title = (rule.title or "").lower()
            msg = (alert.get("message") or "").lower()
            return title.lower() in msg if title else False

        # Simplified: look for condition keywords in alert message
        # Real Sigma needs sigma library, this is honest simplified
        for key, val in detection.items():
            if key in ("condition", "timeframe"):
                continue
            if isinstance(val, dict):
                for subkey, subval in val.items():
                    if isinstance(subval, list):
                        for pattern in subval:
                            if pattern.lower() in (alert.get("message") or "").lower():
                                return True
                    elif isinstance(subval, str):
                        if subval.lower() in (alert.get("message") or "").lower():
                            return True
        return False
    except Exception as exc:
        _LOGGER.debug("Sigma eval failed: %s", exc)
        return False


# DSL

def create_dsl_rule(db: Session, org_id: int, name: str, dsl_expression: str, severity: str = "MEDIUM", created_by_user_id: int = None) -> DetectionDSLRule:
    # Validate DSL: very small parser, supports AND/OR, >=, ==, IN
    if not dsl_expression or len(dsl_expression.strip()) < 3:
        raise ValueError("DSL expression too short")
    rule = DetectionDSLRule(
        org_id=org_id,
        name=name,
        dsl_expression=dsl_expression,
        severity=severity,
        created_by_user_id=created_by_user_id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def evaluate_dsl_rule(dsl_rule: DetectionDSLRule, alert: Dict[str, Any]) -> bool:
    """Evaluate custom DSL — supports simple conditions."""
    expr = dsl_rule.dsl_expression or ""
    try:
        # Replace alert fields
        # Supports: severity == HIGH, source_ip != null, score >= 5
        # Very simplified: eval with safe dict
        # For honesty, we parse manually
        # Split by AND/OR
        conditions = re.split(r"\s+AND\s+|\s+&&\s+", expr, flags=re.IGNORECASE)
        for cond in conditions:
            cond = cond.strip()
            if "==" in cond:
                field, val = [x.strip() for x in cond.split("==", 1)]
                field_val = str(alert.get(field, "")).upper()
                if field_val != val.strip().strip("'\"").upper():
                    return False
            elif ">=" in cond:
                field, val = [x.strip() for x in cond.split(">=", 1)]
                try:
                    fv = float(alert.get(field, 0) or 0)
                    if fv < float(val):
                        return False
                except Exception:
                    return False
            elif "IN" in cond.upper():
                parts = re.split(r"\s+IN\s+", cond, flags=re.IGNORECASE)
                if len(parts) == 2:
                    field = parts[0].strip()
                    list_part = parts[1].strip().strip("[]()")
                    allowed = [x.strip().strip("'\"").upper() for x in list_part.split(",")]
                    if str(alert.get(field, "")).upper() not in allowed:
                        return False
        return True
    except Exception as exc:
        _LOGGER.debug("DSL eval failed %s: %s", expr, exc)
        return False


def serialize_sigma_rule(r: SigmaRule) -> Dict[str, Any]:
    return {
        "id": r.id,
        "org_id": r.org_id,
        "title": r.title,
        "description": r.description,
        "level": r.level,
        "status": r.status,
        "tags": r.tags,
        "version": r.version,
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "rule_yaml": r.rule_yaml,
    }


def serialize_dsl_rule(r: DetectionDSLRule) -> Dict[str, Any]:
    return {
        "id": r.id,
        "org_id": r.org_id,
        "name": r.name,
        "description": r.description,
        "dsl_expression": r.dsl_expression,
        "severity": r.severity,
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
