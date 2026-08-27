"""Seed the preview database with a demo analyst and realistic alert telemetry.

Usage (from backend/):
    DATABASE_URL=sqlite:///./noctra_preview.db .venv/bin/python seed_preview.py

Creates (idempotently):
  - the demo user  demo / demo@noctra.ai / DemoPass123!  (role ANALYST)
  - ~60 security alerts spread over the last 7 days across severities and
    alert types, so /analytics (KPIs, trend, severity pie, top threats,
    recent detections) renders real data.
"""

import random
import sys
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import get_password_hash as hash_password
from app.models import Entity, EntityLink, Org, SecurityAlert, User

DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@noctra.ai"
DEMO_PASSWORD = "DemoPass123!"

# (message, alert_type, mitre_technique_id, mitre_technique, mitre_tactic)
THREATS = [
    ("SQL injection exploit detected on database", "log", "T1190", "Exploit Public-Facing Application", "Initial Access"),
    ("Credential stuffing burst against SSH bastion", "log", "T1110", "Brute Force", "Credential Access"),
    ("Leaked corporate credential is being used to sign in", "log", "T1078", "Valid Accounts", "Credential Access"),
    ("Outbound beaconing to known C2 infrastructure", "network", "T1071", "Application Layer Protocol", "Command and Control"),
    ("Mass DNS query storm from single host", "dns", "T1568", "Dynamic Resolution", "Command and Control"),
    ("Phishing attachment delivered to 12 inboxes", "email", "T1566", "Phishing", "Initial Access"),
    ("RDP brute force from foreign IP range", "network", "T1110", "Brute Force", "Credential Access"),
    ("Suspicious PowerShell execution on workstation", "log", "T1059", "Command and Scripting Interpreter", "Execution"),
    ("Data exfiltration via large outbound HTTPS transfer", "network", "T1048", "Exfiltration Over Alternative Protocol", "Exfiltration"),
    ("Anomalous AWS console login from unrecognized region", "log", "T1078", "Valid Accounts", "Credential Access"),
    ("Port scan across internal subnet", "network", "T1046", "Network Service Scanning", "Discovery"),
    ("Impossible travel: same account, two continents, 10 minutes", "log", "T1078", "Valid Accounts", "Credential Access"),
    ("Malicious macro enabled document opened", "email", "T1204", "User Execution", "Execution"),
    ("Unauthorized USB device enumeration", "log", "T1091", "Replication Through Removable Media", "Lateral Movement"),
    ("Privilege escalation via vulnerable service", "log", "T1068", "Exploitation for Privilege Escalation", "Privilege Escalation"),
    ("Tunneling traffic through DNS queries", "dns", "T1572", "Protocol Tunneling", "Command and Control"),
]

SOURCES = ["203.0.113.42", "198.51.100.7", "192.0.2.88", "10.0.4.12", "10.0.7.201", "172.16.3.9"]
SEVERITIES = ["CRITICAL", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "LOW"]


def main() -> None:
    # Build schema (idempotent)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Default org (created by ensure_default_org at startup, but be safe)
        org = db.query(Org).filter(Org.slug == "default").first()
        if not org:
            org = db.query(Org).first()
        if not org:
            org = Org(name="Default Org", slug="default", description="Default preview workspace")
            db.add(org)
            db.flush()

        # Demo users (idempotent): ANALYST for the day-to-day dashboard,
        # ADMIN so the admin pages (roster edit, roles, engine settings…) can
        # actually be exercised in the preview.
        user = db.query(User).filter(User.username == DEMO_USERNAME).first()
        if not user:
            user = User(
                username=DEMO_USERNAME,
                email=DEMO_EMAIL,
                password=hash_password(DEMO_PASSWORD),
                org_id=org.id,
                role="ANALYST",
                clearance_level=2,
                is_active=True,
                department="Security Operations",
            )
            db.add(user)
            db.flush()
            print(f"created user {DEMO_USERNAME}")

        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@noctra.ai",
                password=hash_password("AdminPass123!"),
                org_id=org.id,
                role="ADMIN",
                clearance_level=4,
                is_active=True,
                department="Platform Administration",
            )
            db.add(admin)
            db.flush()
            print("created user admin")

        # Persist users BEFORE the alerts early-return below, so a partial
        # reseed (alerts already present) still creates new users.
        db.commit()

        # Deterministic entity graph so the Entities & Graph page (list,
        # summary, path finder, node/edge graph) has data to explore.
        rng = random.Random(7)  # deterministic seed
        if db.query(Entity).count() == 0:
            now = datetime.now(timezone.utc)
            seed_entities = [
                # (entity_type, value, risk_score, occurrences, meta)
                ("ip", "203.0.113.42", 0.85, 14, {"asn": "AS64500", "geo": "unknown"}),
                ("ip", "198.51.100.7", 0.72, 8, {"asn": "AS64501", "geo": "unknown"}),
                ("ip", "10.0.4.12", 0.3, 5, {"scope": "internal"}),
                ("domain", "evil-update.tk", 0.9, 11, {"tld": "tk"}),
                ("domain", "update-account.tk", 0.66, 6, {"tld": "tk"}),
                ("hash", "a4f9c2e7b1d34a5f8c6e0d9b2a7f4c8e", 0.78, 4, {"algorithm": "SHA256"}),
                ("email", "hr@corp.local", 0.45, 3, {}),
                ("file", "invoice_2026.exe", 0.82, 7, {"size_kb": 412}),
                ("account", "svc_agent", 0.58, 5, {}),
                ("host", "finance-ws-14", 0.5, 6, {"os": "Windows 11"}),
            ]
            created: dict[str, Entity] = {}
            for etype, value, risk, occ, meta in seed_entities:
                entity = Entity(
                    org_id=org.id,
                    entity_type=etype,
                    value=value,
                    risk_score=risk,
                    occurrences=occ,
                    meta=meta,
                    first_seen=now - timedelta(days=8),
                    last_seen=now - timedelta(hours=rng.randint(1, 40)),
                )
                db.add(entity)
                db.flush()
                created[value] = entity
            seed_links = [
                ("evil-update.tk", "203.0.113.42", "resolves_to"),
                ("update-account.tk", "203.0.113.42", "resolves_to"),
                ("203.0.113.42", "10.0.4.12", "communicates"),
                ("10.0.4.12", "finance-ws-14", "communicates"),
                ("invoice_2026.exe", "evil-update.tk", "derives_from"),
                ("hr@corp.local", "invoice_2026.exe", "attaches"),
                ("a4f9c2e7b1d34a5f8c6e0d9b2a7f4c8e", "invoice_2026.exe", "derives_from"),
                ("svc_agent", "finance-ws-14", "authenticates"),
                ("198.51.100.7", "evil-update.tk", "communicates"),
            ]
            for src, dst, rel in seed_links:
                db.add(
                    EntityLink(
                        org_id=org.id,
                        source_entity_id=created[src].id,
                        target_entity_id=created[dst].id,
                        relation=rel,
                    )
                )
            db.commit()
            print(f"seeded {len(seed_entities)} entities and {len(seed_links)} links")

        # Alerts only if the table is empty (idempotent-ish per run)
        existing = db.query(SecurityAlert).count()
        if existing > 0:
            print(f"alerts already present ({existing}); skipping alert seeding")
            return

        now = datetime.now(timezone.utc)
        created = 0
        for day_offset in range(7, -1, -1):
            day = now - timedelta(days=day_offset)
            count = rng.randint(3, 9)
            for _ in range(count):
                threat = rng.choice(THREATS)
                message, alert_type, mitre_id, mitre_tech, mitre_tac = threat
                severity = rng.choice(SEVERITIES)
                created_at = day.replace(
                    hour=rng.randint(0, 23), minute=rng.randint(0, 59)
                )
                db.add(
                    SecurityAlert(
                        org_id=org.id,
                        alert_type=alert_type,
                        source_ip=rng.choice(SOURCES),
                        source=f"{alert_type}-{rng.randint(100, 999)}",
                        severity=severity,
                        score=round(rng.uniform(0.55, 0.99), 4),
                        message=message,
                        mitre_tactic=mitre_tac,
                        mitre_technique_id=mitre_id,
                        mitre_technique=mitre_tech,
                        threat_intel={
                            "reputation": rng.choice(["malicious", "suspicious", "unknown"]),
                            "whois_org": "Example Telecom",
                        },
                        created_at=created_at,
                    )
                )
                created += 1
        db.commit()
        print(f"seeded {created} security alerts across 8 days")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
