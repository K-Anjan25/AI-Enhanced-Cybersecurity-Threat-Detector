"""
Lightweight schema migrations for the ABAC + multi-tenant migrations.

The project uses Base.metadata.create_all, which never adds columns to an
existing table. These helpers apply additive ALTER TABLE statements so existing
tables gain the ABAC subject-attribute columns and the multi-tenant org_id FK.
"""

import logging
import re

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
    "ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS event_time TIMESTAMP",
    # Threat-intel enrichment (v3): JSON blob with source-IP reputation context.
    "ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS threat_intel JSON",
    # Autonomous analyst (v4, Phase 18): additive columns so the "Feed of
    # decisions" reuses the existing cases table. All nullable -> the legacy
    # Incidents page (which ignores unknown keys) is unaffected.
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS kind VARCHAR(30) DEFAULT 'manual'",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES orgs(id) ON DELETE CASCADE",
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
    # Phase 47: service accounts
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_service_account BOOLEAN DEFAULT FALSE",
    # Phase 41: SAML columns on sso_providers + SCIM Groups + Connector OAuth handled by create_all
    "ALTER TABLE sso_providers ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES orgs(id) ON DELETE CASCADE",
    "ALTER TABLE sso_providers ADD COLUMN IF NOT EXISTS saml_entity_id TEXT",
    "ALTER TABLE sso_providers ADD COLUMN IF NOT EXISTS saml_acs_url TEXT",
    "ALTER TABLE sso_providers ADD COLUMN IF NOT EXISTS saml_sso_url TEXT",
    "ALTER TABLE sso_providers ADD COLUMN IF NOT EXISTS saml_certificate TEXT",
    "ALTER TABLE sso_providers ADD COLUMN IF NOT EXISTS saml_nameid_format VARCHAR(255)",
    # Phase 42: incremental sync for real connector fetch (GitHub, Slack)
    "ALTER TABLE connector_sources ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES orgs(id) ON DELETE CASCADE",
    "ALTER TABLE connector_sources ADD COLUMN IF NOT EXISTS last_cursor TEXT",
    "ALTER TABLE connector_sources ADD COLUMN IF NOT EXISTS sync_state TEXT",
    "ALTER TABLE connector_sources ADD COLUMN IF NOT EXISTS event_time_zone VARCHAR(64)",
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
        for table in ("security_alerts", "scanned_alerts", "scan_batches", "cases", "connector_sources", "sso_providers", "entities", "entity_links", "soar_actions", "soar_playbooks"):
            conn.execute(
                text(f"UPDATE {table} SET org_id = :oid WHERE org_id IS NULL"),
                {"oid": org_id},
            )
        conn.execute(
            text("UPDATE users SET org_id = :oid WHERE org_id IS NULL"),
            {"oid": org_id},
        )


_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+(.*)",
    re.IGNORECASE | re.DOTALL,
)


def _existing_columns(conn, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
    except Exception:  # pragma: no cover - table may not exist yet
        return set()


def _rewrite_for_sqlite(statement: str, conn) -> str | None:
    """Translate `ADD COLUMN IF NOT EXISTS` for SQLite, which lacks it.

    SQLite rejects the `IF NOT EXISTS` clause outright, so every additive
    migration raised and was swallowed by the warning below — meaning existing
    SQLite databases never received a new column, while a fresh one got it from
    create_all(). The divergence only showed up as a missing attribute at
    runtime, long after startup looked clean.
    """
    match = _ADD_COLUMN_RE.match(statement.strip())
    if not match:
        return statement
    table, column, definition = match.group(1), match.group(2), match.group(3)
    if column in _existing_columns(conn, table):
        return None  # already applied; genuinely nothing to do
    return f"ALTER TABLE {table} ADD COLUMN {column} {definition}"


def run_additive_migrations(engine) -> None:
    """Apply idempotent additive migrations to the live database."""
    is_sqlite = engine.dialect.name == "sqlite"
    with engine.begin() as conn:
        for statement in ADDITIVE_MIGRATIONS:
            try:
                effective = statement
                if is_sqlite:
                    effective = _rewrite_for_sqlite(statement, conn)
                    if effective is None:
                        continue
                conn.execute(text(effective))
            except Exception as exc:  # pragma: no cover - non-critical on startup
                _LOGGER.warning("Migration skipped (%s): %s", statement, exc)
