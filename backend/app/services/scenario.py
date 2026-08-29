"""Scenario injector for the autonomous-analyst walking skeleton (Phases 18-19).

Provides multi-scenario simulation (credential leak, phishing outbreak, data exfiltration,
compromised API key) entirely in-process. Each scenario fabricates a realistic incident,
builds a blast-radius graph, invokes LLM/heuristic reasoning, and opens a pending case.
"""

from __future__ import annotations

from app.models import SecurityAlert, Case
from app.services import entity_graph, llm_client
from app.services.soar import ACTION_DEFAULT_SEVERITY
from app.utils.helpers import severity_to_score, serialize_alert, create_audit_log

# Deterministic actors/assets for scenarios.
_LEAKED_EMAIL = "jdoe@acme.com"
_LEAKED_ACCOUNT = "jdoe"
_SENSITIVE_HOST = "finance-db"
_ATTACKER_IP = "203.0.113.66"  # RFC 5737 TEST-NET-3

_PHISHING_SENDER = "hr-update@security-verify-acme.net"
_TARGET_USER = "alice.smith@acme.com"
_TARGET_ACCOUNT = "asmith"
_WORKSTATION = "ws-eng-042"
_C2_SERVER = "198.51.100.44"

_EXFIL_BUCKET = "acme-customer-pii-backup"
_SUSPECT_IP = "198.51.100.88"
_IAM_ROLE = "arn:aws:iam::123456789012:role/DataSyncRole"

_STOLEN_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
_ATTACKER_LOCATION = "192.0.2.105"
_CREATED_ADMIN_USER = "backdoor-admin"

# Phase 36 — additional scenarios
_INSIDER_USER = "bob.wilson@acme.com"
_INSIDER_ACCOUNT = "bwilson"
_PRIVILEGED_HOST = "hr-payroll-db"
_CREDENTIAL_DUMP = "ntds.dit"
_RANSOMWARE_HOST = "ws-finance-019"
_RANSOMWARE_IP = "203.0.113.99"
_ENCRYPTED_FILE = "invoice_2024.xlsx.locked"


def run_credential_leak(db, org_id: int, actor: str, created_by_id: int | None = None) -> Case:
    """Simulate a credential-leak incident and open a pending analyst case."""
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
    db.flush()

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

    analysis = llm_client.analyze_incident(serialize_alert(alert), entities)
    rec = analysis.get("recommended_action") or {}
    proposed_action = {
        "action_type": rec.get("action_type", "REVOKE_CREDENTIALS"),
        "target": rec.get("target", f"account:{_LEAKED_ACCOUNT}"),
        "severity": ACTION_DEFAULT_SEVERITY.get(rec.get("action_type", ""), alert.severity or "HIGH"),
        "rationale": rec.get("rationale", "Revoke compromised user session and force password reset."),
        "undo": rec.get("undo", f"Re-enable user account:{_LEAKED_ACCOUNT} and issue temporary login token."),
    }

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

    create_audit_log(
        db,
        action="ANALYST_CASE_OPENED",
        actor=actor,
        resource=f"case:{case.id}",
        details=f"credential_leak alert:{alert.id} action:{proposed_action['action_type']}",
    )
    return case


def run_phishing_outbreak(db, org_id: int, actor: str, created_by_id: int | None = None) -> Case:
    """Simulate a targeted phishing attack leading to execution on workstation."""
    alert = SecurityAlert(
        org_id=org_id,
        alert_type="phishing_execution",
        source_ip=_C2_SERVER,
        source="email-gateway",
        severity="CRITICAL",
        score=severity_to_score("CRITICAL"),
        message=(
            f"Phishing email from {_PHISHING_SENDER} delivered to {_TARGET_USER}. "
            f"Attachment executed on {_WORKSTATION} establishing outbound beacon to C2 {_C2_SERVER}."
        ),
        mitre_tactic="Initial Access",
        mitre_technique_id="T1566",
        mitre_technique="Phishing",
    )
    db.add(alert)
    db.flush()

    sender = entity_graph.upsert_entity(db, "email", _PHISHING_SENDER, org_id, {"kind": "malicious_sender"})
    target = entity_graph.upsert_entity(db, "email", _TARGET_USER, org_id, {"kind": "targeted_user"})
    workstation = entity_graph.upsert_entity(db, "host", _WORKSTATION, org_id, {"kind": "endpoint"})
    c2 = entity_graph.upsert_entity(db, "ip", _C2_SERVER, org_id, {"kind": "c2_server"})

    for ent in (sender, target, workstation, c2):
        ent.risk_score = max(ent.risk_score or 0.0, float(alert.score or 0.0))
    db.flush()

    entity_graph.link_entities(db, sender, target, alert, "targets")
    entity_graph.link_entities(db, target, workstation, alert, "uses_device")
    entity_graph.link_entities(db, workstation, c2, alert, "communicates")
    db.flush()

    entities = [entity_graph.serialize_entity(e) for e in (sender, target, workstation, c2)]
    graph = entity_graph.entity_graph(db, target.id, depth=2, org_id=org_id)
    blast_radius = {
        "root_entity_id": graph.get("root"),
        "nodes": graph.get("nodes", []),
        "links": graph.get("links", []),
    }

    analysis = llm_client.analyze_incident(serialize_alert(alert), entities)
    rec = analysis.get("recommended_action") or {}
    proposed_action = {
        "action_type": rec.get("action_type", "QUARANTINE_ENDPOINT"),
        "target": rec.get("target", f"host:{_WORKSTATION}"),
        "severity": "HIGH",
        "rationale": rec.get("rationale", "Isolate endpoint from network to sever C2 communication."),
        "undo": rec.get("undo", f"Re-attach host:{_WORKSTATION} to local network interface."),
    }

    case = Case(
        org_id=org_id,
        title=analysis.get("headline") or f"Phishing payload execution on {_WORKSTATION}",
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

    create_audit_log(
        db,
        action="ANALYST_CASE_OPENED",
        actor=actor,
        resource=f"case:{case.id}",
        details=f"phishing_execution alert:{alert.id} action:{proposed_action['action_type']}",
    )
    return case


def run_data_exfiltration(db, org_id: int, actor: str, created_by_id: int | None = None) -> Case:
    """Simulate public exposure / exfiltration from an internal cloud database bucket."""
    alert = SecurityAlert(
        org_id=org_id,
        alert_type="data_exfiltration",
        source_ip=_SUSPECT_IP,
        source="cloud-audit",
        severity="CRITICAL",
        score=severity_to_score("CRITICAL"),
        message=(
            f"Anomalous bulk download (48 GB) from S3 bucket {_EXFIL_BUCKET} via role {_IAM_ROLE} "
            f"to untrusted IP {_SUSPECT_IP}."
        ),
        mitre_tactic="Exfiltration",
        mitre_technique_id="T1048",
        mitre_technique="Exfiltration Over Alternative Protocol",
    )
    db.add(alert)
    db.flush()

    bucket = entity_graph.upsert_entity(db, "host", _EXFIL_BUCKET, org_id, {"kind": "cloud_storage"})
    role = entity_graph.upsert_entity(db, "account", _IAM_ROLE, org_id, {"kind": "iam_role"})
    suspect_ip = entity_graph.upsert_entity(db, "ip", _SUSPECT_IP, org_id, {"kind": "untrusted_ip"})

    for ent in (bucket, role, suspect_ip):
        ent.risk_score = max(ent.risk_score or 0.0, float(alert.score or 0.0))
    db.flush()

    entity_graph.link_entities(db, role, bucket, alert, "accesses")
    entity_graph.link_entities(db, role, suspect_ip, alert, "communicates")
    db.flush()

    entities = [entity_graph.serialize_entity(e) for e in (bucket, role, suspect_ip)]
    graph = entity_graph.entity_graph(db, bucket.id, depth=2, org_id=org_id)
    blast_radius = {
        "root_entity_id": graph.get("root"),
        "nodes": graph.get("nodes", []),
        "links": graph.get("links", []),
    }

    analysis = llm_client.analyze_incident(serialize_alert(alert), entities)
    rec = analysis.get("recommended_action") or {}
    proposed_action = {
        "action_type": rec.get("action_type", "BLOCK_SOURCE_IP"),
        "target": rec.get("target", f"ip:{_SUSPECT_IP}"),
        "severity": "HIGH",
        "rationale": rec.get("rationale", "Block suspect IP at cloud firewall and attach restrictive IAM boundary."),
        "undo": rec.get("undo", f"Remove ip:{_SUSPECT_IP} from perimeter blocklist."),
    }

    case = Case(
        org_id=org_id,
        title=analysis.get("headline") or f"Data exfiltration from {_EXFIL_BUCKET}",
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

    create_audit_log(
        db,
        action="ANALYST_CASE_OPENED",
        actor=actor,
        resource=f"case:{case.id}",
        details=f"data_exfiltration alert:{alert.id} action:{proposed_action['action_type']}",
    )
    return case


def run_compromised_api_key(db, org_id: int, actor: str, created_by_id: int | None = None) -> Case:
    """Simulate compromised cloud API key used to create backdoor accounts."""
    alert = SecurityAlert(
        org_id=org_id,
        alert_type="compromised_api_key",
        source_ip=_ATTACKER_LOCATION,
        source="iam-audit",
        severity="HIGH",
        score=severity_to_score("HIGH"),
        message=(
            f"Cloud API Key {_STOLEN_KEY_ID} used from {_ATTACKER_LOCATION} to spawn backdoor "
            f"admin user {_CREATED_ADMIN_USER}."
        ),
        mitre_tactic="Persistence",
        mitre_technique_id="T1098",
        mitre_technique="Account Manipulation",
    )
    db.add(alert)
    db.flush()

    key = entity_graph.upsert_entity(db, "account", _STOLEN_KEY_ID, org_id, {"kind": "api_key"})
    admin_user = entity_graph.upsert_entity(db, "account", _CREATED_ADMIN_USER, org_id, {"kind": "unauthorized_user"})
    attacker = entity_graph.upsert_entity(db, "ip", _ATTACKER_LOCATION, org_id, {"kind": "attacker_ip"})

    for ent in (key, admin_user, attacker):
        ent.risk_score = max(ent.risk_score or 0.0, float(alert.score or 0.0))
    db.flush()

    entity_graph.link_entities(db, key, admin_user, alert, "derives_from")
    entity_graph.link_entities(db, key, attacker, alert, "communicates")
    db.flush()

    entities = [entity_graph.serialize_entity(e) for e in (key, admin_user, attacker)]
    graph = entity_graph.entity_graph(db, key.id, depth=2, org_id=org_id)
    blast_radius = {
        "root_entity_id": graph.get("root"),
        "nodes": graph.get("nodes", []),
        "links": graph.get("links", []),
    }

    analysis = llm_client.analyze_incident(serialize_alert(alert), entities)
    rec = analysis.get("recommended_action") or {}
    proposed_action = {
        "action_type": rec.get("action_type", "REVOKE_CREDENTIALS"),
        "target": rec.get("target", f"account:{_STOLEN_KEY_ID}"),
        "severity": "HIGH",
        "rationale": rec.get("rationale", "Deactivate compromised API key and purge spawned backdoor accounts."),
        "undo": rec.get("undo", f"Re-enable API key:{_STOLEN_KEY_ID}."),
    }

    case = Case(
        org_id=org_id,
        title=analysis.get("headline") or f"Compromised API Key {_STOLEN_KEY_ID}",
        description=analysis.get("what_happened"),
        status="open",
        priority="high",
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

    create_audit_log(
        db,
        action="ANALYST_CASE_OPENED",
        actor=actor,
        resource=f"case:{case.id}",
        details=f"compromised_api_key alert:{alert.id} action:{proposed_action['action_type']}",
    )
    return case


def run_insider_threat(db, org_id: int, actor: str, created_by_id: int | None = None) -> Case:
    """Simulate an insider attempting credential dumping on a privileged host."""
    alert = SecurityAlert(
        org_id=org_id,
        alert_type="credential_dumping",
        source_ip="10.0.1.45",
        source="edr",
        severity="HIGH",
        score=severity_to_score("HIGH"),
        message=(
            f"User {_INSIDER_USER} attempted to access {_CREDENTIAL_DUMP} on "
            f"{_PRIVILEGED_HOST} outside business hours. LSASS memory access detected."
        ),
        mitre_tactic="Credential Access",
        mitre_technique_id="T1003",
        mitre_technique="OS Credential Dumping",
    )
    db.add(alert)
    db.flush()

    insider = entity_graph.upsert_entity(db, "account", _INSIDER_ACCOUNT, org_id, {"kind": "corporate_account"})
    email = entity_graph.upsert_entity(db, "email", _INSIDER_USER, org_id, {"kind": "insider_user"})
    host = entity_graph.upsert_entity(db, "host", _PRIVILEGED_HOST, org_id, {"kind": "privileged_asset"})
    file_entity = entity_graph.upsert_entity(db, "file", _CREDENTIAL_DUMP, org_id, {"kind": "credential_store"})
    for ent in (insider, email, host, file_entity):
        ent.risk_score = max(ent.risk_score or 0.0, float(alert.score or 0.0))
    db.flush()

    entity_graph.link_entities(db, insider, host, alert, "accesses")
    entity_graph.link_entities(db, insider, file_entity, alert, "accesses")
    entity_graph.link_entities(db, email, insider, alert, "derives_from")
    db.flush()

    entities = [entity_graph.serialize_entity(e) for e in (insider, email, host, file_entity)]
    graph = entity_graph.entity_graph(db, insider.id, depth=2, org_id=org_id)
    blast_radius = {
        "root_entity_id": graph.get("root"),
        "nodes": graph.get("nodes", []),
        "links": graph.get("links", []),
    }

    analysis = llm_client.analyze_incident(serialize_alert(alert), entities)
    rec = analysis.get("recommended_action") or {}
    proposed_action = {
        "action_type": rec.get("action_type", "DISABLE_ACCOUNT"),
        "target": rec.get("target", f"account:{_INSIDER_ACCOUNT}"),
        "severity": "HIGH",
        "rationale": rec.get("rationale", "Temporarily disable account pending HR review of off-hours credential access."),
        "undo": rec.get("undo", f"Re-enable account:{_INSIDER_ACCOUNT} after investigation."),
    }

    case = Case(
        org_id=org_id,
        title=analysis.get("headline") or f"Potential insider credential dumping by {_INSIDER_ACCOUNT}",
        description=analysis.get("what_happened"),
        status="open",
        priority="high",
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

    create_audit_log(
        db,
        action="ANALYST_CASE_OPENED",
        actor=actor,
        resource=f"case:{case.id}",
        details=f"insider_threat alert:{alert.id} action:{proposed_action['action_type']}",
    )
    return case


def run_ransomware_activity(db, org_id: int, actor: str, created_by_id: int | None = None) -> Case:
    """Simulate early ransomware encryption activity on an endpoint."""
    alert = SecurityAlert(
        org_id=org_id,
        alert_type="ransomware_activity",
        source_ip=_RANSOMWARE_IP,
        source="edr",
        severity="CRITICAL",
        score=severity_to_score("CRITICAL"),
        message=(
            f"Ransomware-like file encryption detected on {_RANSOMWARE_HOST}: "
            f"{_ENCRYPTED_FILE} created, shadow copies deleted, C2 beacon to {_RANSOMWARE_IP}."
        ),
        mitre_tactic="Impact",
        mitre_technique_id="T1486",
        mitre_technique="Data Encrypted for Impact",
    )
    db.add(alert)
    db.flush()

    host = entity_graph.upsert_entity(db, "host", _RANSOMWARE_HOST, org_id, {"kind": "endpoint"})
    ip = entity_graph.upsert_entity(db, "ip", _RANSOMWARE_IP, org_id, {"kind": "c2_server"})
    file_entity = entity_graph.upsert_entity(db, "file", _ENCRYPTED_FILE, org_id, {"kind": "encrypted_file"})
    for ent in (host, ip, file_entity):
        ent.risk_score = max(ent.risk_score or 0.0, float(alert.score or 0.0))
    db.flush()

    entity_graph.link_entities(db, host, file_entity, alert, "derives_from")
    entity_graph.link_entities(db, host, ip, alert, "communicates")
    db.flush()

    entities = [entity_graph.serialize_entity(e) for e in (host, ip, file_entity)]
    graph = entity_graph.entity_graph(db, host.id, depth=2, org_id=org_id)
    blast_radius = {
        "root_entity_id": graph.get("root"),
        "nodes": graph.get("nodes", []),
        "links": graph.get("links", []),
    }

    analysis = llm_client.analyze_incident(serialize_alert(alert), entities)
    rec = analysis.get("recommended_action") or {}
    proposed_action = {
        "action_type": rec.get("action_type", "QUARANTINE_ENDPOINT"),
        "target": rec.get("target", f"host:{_RANSOMWARE_HOST}"),
        "severity": "CRITICAL",
        "rationale": rec.get("rationale", "Isolate endpoint immediately to halt encryption and preserve forensic evidence."),
        "undo": rec.get("undo", f"Release host:{_RANSOMWARE_HOST} from quarantine after clean scan."),
    }

    case = Case(
        org_id=org_id,
        title=analysis.get("headline") or f"Ransomware activity on {_RANSOMWARE_HOST}",
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

    create_audit_log(
        db,
        action="ANALYST_CASE_OPENED",
        actor=actor,
        resource=f"case:{case.id}",
        details=f"ransomware_activity alert:{alert.id} action:{proposed_action['action_type']}",
    )
    return case


# Catalogue of scenarios for API and UI
SCENARIO_CATALOG: list[dict] = [
    {
        "id": "credential_leak",
        "label": "Credential Leak (T1078)",
        "mitre": "T1078",
        "severity": "CRITICAL",
        "description": "Leaked corporate credential used from external IP",
    },
    {
        "id": "phishing_outbreak",
        "label": "Phishing Outbreak (T1566)",
        "mitre": "T1566",
        "severity": "CRITICAL",
        "description": "Phishing email leading to C2 beacon on workstation",
    },
    {
        "id": "data_exfiltration",
        "label": "Data Exfiltration (T1048)",
        "mitre": "T1048",
        "severity": "CRITICAL",
        "description": "Bulk download from S3 bucket to untrusted IP",
    },
    {
        "id": "compromised_api_key",
        "label": "Compromised API Key (T1098)",
        "mitre": "T1098",
        "severity": "HIGH",
        "description": "Stolen cloud API key spawning backdoor admin",
    },
    {
        "id": "insider_threat",
        "label": "Insider Threat (T1003)",
        "mitre": "T1003",
        "severity": "HIGH",
        "description": "Off-hours credential dumping on privileged host",
    },
    {
        "id": "ransomware_activity",
        "label": "Ransomware Activity (T1486)",
        "mitre": "T1486",
        "severity": "CRITICAL",
        "description": "File encryption and shadow copy deletion on endpoint",
    },
]


def list_scenarios() -> list[dict]:
    return SCENARIO_CATALOG


def run_scenario(
    db, scenario_type: str, org_id: int, actor: str, created_by_id: int | None = None
) -> Case:
    """Dispatch scenario injection by type name."""
    scenarios = {
        "credential_leak": run_credential_leak,
        "phishing_outbreak": run_phishing_outbreak,
        "data_exfiltration": run_data_exfiltration,
        "compromised_api_key": run_compromised_api_key,
        "insider_threat": run_insider_threat,
        "ransomware_activity": run_ransomware_activity,
    }
    handler = scenarios.get(scenario_type, run_credential_leak)
    return handler(db, org_id=org_id, actor=actor, created_by_id=created_by_id)
