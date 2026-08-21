"""Scenario injector for the autonomous-analyst walking skeleton (Phase 18).

``run_credential_leak`` fabricates one realistic incident -- a leaked corporate
credential being used from an attacker IP -- entirely in-process (no cloud setup
required). It reuses the real engine: it persists a ``SecurityAlert``, builds a
blast radius on the entity graph, asks the LLM to reason about it, and opens a
``pending`` analyst ``Case``. This is the demo's "sense" step; later phases
replace it with real connectors (Okta / EDR / firewall).
"""

from __future__ import annotations

from app.models import SecurityAlert, Case
from app.services import entity_graph, llm_client
from app.services.soar import ACTION_DEFAULT_SEVERITY
from app.utils.helpers import severity_to_score, serialize_alert, create_audit_log

# Deterministic actors/assets for the simulated credential leak.
_LEAKED_EMAIL = "jdoe@acme.com"
_LEAKED_ACCOUNT = "jdoe"
_SENSITIVE_HOST = "finance-db"
_ATTACKER_IP = "203.0.113.66"  # TEST-NET-3 (RFC 5737) - safe, non-routable example IP


def run_credential_leak(db, org_id: int, actor: str, created_by_id: int | None = None) -> Case:
    """Simulate a credential-leak incident and open a pending analyst case."""
    # 1. Sense: persist the raised alert.
    alert = SecurityAlert(
        org_id=org_id,
        alert_type="credential_leak",
        source_ip=_ATTACKER_IP,
        source="identity-provider",
        severity="CRITICAL",
        score=severity_to_score("CRITICAL"),
        message=(
            f"Corporate credential for {_LEAKED_EMAIL} used to sign in from {_ATTACKER_IP}; "
            f"credential also seen in a public paste. Access reached {_SENSITIVE_HOST}."
        ),
        mitre_tactic="Initial Access",
        mitre_technique_id="T1078",
        mitre_technique="Valid Accounts",
    )
    db.add(alert)
    db.flush()  # assign alert.id for links + soar payloads

    # 2. Build a deterministic blast radius on the entity graph.
    #    email (leaked credential) --derives_from--> account
    #    account --communicates--> host (sensitive asset)
    #    account --communicates--> attacker IP
    #    Rooted at the email, a depth-2 out-edge walk reaches every node.
    email = entity_graph.upsert_entity(db, "email", _LEAKED_EMAIL, org_id, {"kind": "leaked_credential"})
    account = entity_graph.upsert_entity(db, "account", _LEAKED_ACCOUNT, org_id, {"kind": "corporate_account"})
    host = entity_graph.upsert_entity(db, "host", _SENSITIVE_HOST, org_id, {"kind": "sensitive_asset"})
    attacker = entity_graph.upsert_entity(db, "ip", _ATTACKER_IP, org_id, {"kind": "external"})
    for ent in (email, account, host, attacker):
        ent.risk_score = max(ent.risk_score or 0.0, float(alert.score or 0.0))
    db.flush()

    entity_graph.link_entities(db, email, account, alert, "derives_from")
    entity_graph.link_entities(db, account, host, alert, "communicates")
    entity_graph.link_entities(db, account, attacker, alert, "communicates")
    db.flush()

    entities = [entity_graph.serialize_entity(e) for e in (email, account, host, attacker)]
    graph = entity_graph.entity_graph(db, email.id, depth=2, org_id=org_id)
    blast_radius = {
        "root_entity_id": graph.get("root"),
        "nodes": graph.get("nodes", []),
        "links": graph.get("links", []),
    }

    # 3. Reason: ask the LLM (or fall back to a templated narrative).
    analysis = llm_client.analyze_incident(serialize_alert(alert), entities)
    rec = analysis.get("recommended_action") or {}
    proposed_action = {
        "action_type": rec.get("action_type", "ALERT_OPERATOR"),
        "target": rec.get("target", f"account:{_LEAKED_ACCOUNT}"),
        "severity": ACTION_DEFAULT_SEVERITY.get(rec.get("action_type", ""), alert.severity or "HIGH"),
        "rationale": rec.get("rationale", ""),
        "undo": rec.get("undo", ""),
    }

    # 4. Open a pending analyst case (built directly to carry the analyst fields
    #    and to keep a single ANALYST_CASE_OPENED audit entry).
    case = Case(
        org_id=org_id,
        title=analysis.get("headline") or "Leaked credential in use",
        description=analysis.get("what_happened"),
        status="open",
        priority="critical",
        source_alert_id=alert.id,
        created_by_id=created_by_id,
        kind="analyst",
        analysis=analysis,
        blast_radius=blast_radius,
        proposed_action=proposed_action,
        decision="pending",
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    # 5. Accountability.
    create_audit_log(
        db,
        action="ANALYST_CASE_OPENED",
        actor=actor,
        resource=f"case:{case.id}",
        details=f"credential_leak alert:{alert.id} action:{proposed_action['action_type']}",
    )
    return case
