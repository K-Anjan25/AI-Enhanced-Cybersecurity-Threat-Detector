"""SOAR (Security Orchestration, Automation and Response) action executor.

Evaluates raised alerts against active detection rules and maps matched rules
to automated responses. Responses are published to the ``actions.executed``
Kafka topic (when enabled) and recorded in ``soar_actions`` so analysts can
audit what the platform did automatically.

DO NOT disrupt core ingestion: ``should_respond`` is a pure function and
``execute_action`` degrades to a no-op log when anything fails.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.models import DetectionRule, SoarAction
from app.services.kafka_producer import send_action

# List of actions this phase can auto-execute. Each maps severity thresholds to
# a response; production deployments add concrete connectors (firewall, EDR…).
SUPPORTED_ACTIONS = {
    "BLOCK_SOURCE_IP",
    "QUARANTINE_ENDPOINT",
    "REVOKE_CREDENTIALS",
    "ALERT_OPERATOR",
    "DISABLE_ACCOUNT",
    "REVIEW_ONLY",
}

# Default severity per action when a rule does not specify one.
ACTION_DEFAULT_SEVERITY = {
    "BLOCK_SOURCE_IP": "HIGH",
    "QUARANTINE_ENDPOINT": "HIGH",
    "REVOKE_CREDENTIALS": "CRITICAL",
    "DISABLE_ACCOUNT": "HIGH",
    "ALERT_OPERATOR": "MEDIUM",
    "REVIEW_ONLY": "LOW",
}

_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b")


def evaluate_alert(alert: dict, rules: Sequence[DetectionRule]) -> list[dict]:
    """Pure rule evaluation: return a list of matched actions for an alert.

    ``alert`` is the normalized alert dict produced by ``process_log``.
    """
    actions: list[dict] = []
    message = (alert.get("message") or "").lower()
    alert_type = (alert.get("alert_type") or "").lower()
    mitre_tech = (alert.get("mitre_technique_id") or "").lower()

    for rule in rules:
        if not getattr(rule, "is_active", True):
            continue
        pattern = (rule.pattern or "").lower()
        if not pattern:
            continue

        # Match against message text, alert type, or a MITRE technique token.
        matched = (
            (re.search(re.escape(pattern), message) is not None)
            or (pattern == alert_type)
            or (pattern in mitre_tech)
        )
        if not matched:
            continue

        action_type = _action_for_rule(rule)
        sev = (rule.severity or ACTION_DEFAULT_SEVERITY[action_type]).upper()
        actions.append({
            "action_type": action_type,
            "severity": sev,
            "rule_name": rule.name,
            "rule_id": rule.id,
        })

    # No rule matched but the alert is grave: always notify the operator.
    if not actions and _severity_rank(alert.get("severity")) >= _severity_rank("HIGH"):
        actions.append({
            "action_type": "ALERT_OPERATOR",
            "severity": (alert.get("severity") or "HIGH").upper(),
            "rule_name": "default",
            "rule_id": None,
        })
    return actions


def _action_for_rule(rule: DetectionRule) -> str:
    """Map a rule to a supported action type, defaulting by severity."""
    name = (rule.name or "").lower()
    if "credential" in name or "brute" in name.lower():
        return "REVOKE_CREDENTIALS"
    if "ransomware" in name.lower():
        return "QUARANTINE_ENDPOINT"
    if "account" in name.lower() or "user" in name.lower():
        return "DISABLE_ACCOUNT"
    severity = (rule.severity or "MEDIUM").upper()
    if severity == "CRITICAL":
        return "BLOCK_SOURCE_IP"
    if severity == "HIGH":
        return "ALERT_OPERATOR"
    return "REVIEW_ONLY"


def _severity_rank(sev: Optional[str]) -> int:
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get((sev or "LOW").upper(), 0)


def respond_to_alert(db, alert: dict, rules: Sequence[DetectionRule]) -> list[dict]:
    """Evaluate an alert and execute every matched action.

    Returns the executed action dicts (audited). Publishing to Kafka and the
    DB insert are both best-effort; a failure never raises out to the caller
    (ingestion must not break because SOAR is down).
    """
    matched = evaluate_alert(alert, rules)
    results: list[dict] = []
    for m in matched:
        if m["action_type"] not in SUPPORTED_ACTIONS:
            continue
        performed = execute_action(db, alert, m)
        results.append(performed)
    return results


def execute_action(db, alert: dict, matched: dict) -> dict:
    """Execute a single matched action and record it in ``soar_actions``."""
    action = {
        "action_type": matched["action_type"],
        "severity": matched["severity"],
        "rule_name": matched.get("rule_name"),
        "rule_id": matched.get("rule_id"),
        "org_id": alert.get("org_id"),
        "payload": {
            "alert_id": alert.get("id"),
            "source_ip": alert.get("source_ip"),
            "mitre_technique_id": alert.get("mitre_technique_id"),
            "trigger": f"{alert.get('alert_type')}::{matched['action_type']}",
        },
    }

    row = None
    try:
        row = SoarAction(
            action_id=str(uuid4()),
            org_id=action["org_id"],
            action_type=action["action_type"],
            severity=action["severity"],
            rule_name=matched.get("rule_name"),
            alert_id=alert.get("id"),
            payload=action["payload"],
            status="executed",
        )
        db.add(row)
        db.flush()
    except IntegrityError:
        db.rollback()
        row = None

    # Kafka publish (non-fatal).
    try:
        send_action(action)
    except Exception:
        pass

    response = {
        "action_id": row.action_id if row else None,
        "action_type": action["action_type"],
        "severity": action["severity"],
        "rule_name": matched.get("rule_name"),
        "status": "executed" if row else "failed",
        "payload": action["payload"],
    }
    return response


def list_actions(db, page: int = 1, limit: int = 20, org_id: Optional[int] = None) -> tuple[list, int]:
    from app.utils.helpers import paginate

    query = db.query(SoarAction).order_by(SoarAction.created_at.desc())
    if org_id is not None:
        query = query.filter(SoarAction.org_id == org_id)
    return paginate(db, query, page, limit)