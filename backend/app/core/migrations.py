"""
Lightweight schema migrations for the ABAC + multi-tenant migrations.

The project uses Base.metadata.create_all, which never adds columns to an
existing table. These helpers apply additive ALTER TABLE statements so existing
tables gain the ABAC subject-attribute columns and the multi-tenant org_id FK.
"""

import logging

from sqlalchemy import text

_LOGGER = logging.getLogger("app")


ADDITIVE_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS clearance_level INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS department VARCHAR(100)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0",
    # Multi-tenancy (v3): orgs table + org_id on tenant-owned tables.
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES orgs(id) ON DELETE CASCADE",
    "ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES orgs(id) ON DELETE CASCADE",
    "ALTER TABLE scanned_alerts ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES orgs(id) ON DELETE CASCADE",
    "ALTER TABLE scan_batches ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES orgs(id) ON DELETE CASCADE",
    # MITRE ATT&CK mapping (v3) on security alerts.
    "ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS mitre_tactic VARCHAR(100)",
    "ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS mitre_technique_id VARCHAR(20)",
    "ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS mitre_technique VARCHAR(150)",
    # Threat-intel enrichment (v3): JSON blob with source-IP reputation context.
    "ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS threat_intel JSON",
    # Autonomous analyst (v4, Phase 18): additive columns so the "Feed of
    # decisions" reuses the existing cases table. All nullable -> the legacy
    # Incidents page (which ignores unknown keys) is unaffected.
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS kind VARCHAR(30) DEFAULT 'manual'",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS analysis JSON",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS blast_radius JSON",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposed_action JSON",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS decision VARCHAR(20) DEFAULT 'pending'",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS decided_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS soar_action_id VARCHAR(64)",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS report TEXT",
    # Phase 40: SSO/SCIM — User columns for external identity
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS external_id VARCHAR(255)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_provider VARCHAR(50)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_sso_user BOOLEAN DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS scim_external_id VARCHAR(255)",
]


def ensure_default_org(engine) -> None:
    """Seed a default organization so existing (single-tenant) rows have a home."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM orgs WHERE slug = 'default' LIMIT 1")
        ).fetchone()
        if not row:
            conn.execute(
                text("INSERT INTO orgs (name, slug) VALUES ('Default Organization', 'default')")
            )
            _LOGGER.info("Seeded default org")
        org_id = conn.execute(
            text("SELECT id FROM orgs WHERE slug = 'default' LIMIT 1")
        ).scalar()
        # Backfill existing tenant-owned rows into the default org.
        for table in ("security_alerts", "scanned_alerts", "scan_batches", "cases", "entities", "entity_links", "soar_actions", "soar_playbooks"):
            conn.execute(
                text(f"UPDATE {table} SET org_id = :oid WHERE org_id IS NULL"),
                {"oid": org_id},
            )
        conn.execute(
            text("UPDATE users SET org_id = :oid WHERE org_id IS NULL"),
            {"oid": org_id},
        )


def run_additive_migrations(engine) -> None:
    """Apply idempotent additive migrations to the live database."""
    with engine.begin() as conn:
        for statement in ADDITIVE_MIGRATIONS:
            try:
                conn.execute(text(statement))
            except Exception as exc:  # pragma: no cover - non-critical on startup
                _LOGGER.warning("Migration skipped (%s): %s", statement, exc)
