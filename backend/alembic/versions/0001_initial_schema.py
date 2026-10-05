"""Initial schema: architecture.md §6, with monthly partitions.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-05

Up creates every table, the enum types, and the first partitions for the two
monthly-partitioned tables. Down drops them in reverse dependency order.

Two things a reviewer should check against a real server, because neither is
exercised by the test suite -- declarative partitioning is PostgreSQL-only and CI
runs without one:

* the partitioned primary keys. ``alerts`` is ``(id, created_at)`` and
  ``ingest_stats`` ``(id, window_start)``; PostgreSQL cannot enforce a key that
  excludes the partition column.
* the ``FOR VALUES FROM/TO`` bounds. They are half-open, so consecutive months
  neither overlap nor leave a gap. The pure builders in ``app.db.partitions`` are
  unit-tested; the emitted statements are not executed here.

There is no default partition. A row outside every partition is rejected, which
is loud; a default partition would accept it silently and accumulate until it
defeated the retention model that dropping partitions provides.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from app.db.partitions import create_partition_sql, drop_partition_sql
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

#: Partitions created by this migration. Enough to receive traffic immediately;
#: a scheduled job (T-320 territory) is responsible for creating future ones.
_INITIAL_MONTHS: tuple[tuple[int, int], ...] = ((2026, 3), (2026, 4), (2026, 5))

#: Creation order: parents before children. Down reverses it.
_TABLES_IN_ORDER: tuple[str, ...] = (
    "users",
    "entities",
    "api_keys",
    "alerts",
    "models",
    "model_versions_history",
    "audit_log",
    "thresholds",
    "ingest_stats",
)

_ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("user_role", ("viewer", "analyst", "responder", "admin")),
    ("entity_kind", ("host", "ip", "user", "service")),
    ("alert_status", ("open", "acknowledged", "closed")),
    ("verdict", ("true_positive", "false_positive", "benign")),
    ("model_kind", ("flow", "log")),
    ("model_status", ("staging", "active", "retired")),
)


def upgrade() -> None:
    """Create the schema and the initial partitions."""
    for name, values in _ENUMS:
        postgresql.ENUM(*values, name=name, create_type=False).create(
            op.get_bind(), checkfirst=True
        )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("argon2_hash", sa.Text, nullable=False),
        sa.Column("role", postgresql.ENUM(name="user_role", create_type=False), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "entities",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("kind", postgresql.ENUM(name="entity_kind", create_type=False), nullable=False),
        sa.Column("value", sa.String(512), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("kind", "value", name="uq_entities_kind_value"),
    )
    op.create_index("ix_entities_last_seen", "entities", ["last_seen"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String(60)), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    op.create_table(
        "alerts",
        # Partition key inside the primary key: PostgreSQL cannot enforce a key
        # that excludes the partition column.
        sa.Column("id", sa.BigInteger, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("entity_id", sa.BigInteger, sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("family", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("model_flow_id", sa.String(200)),
        sa.Column("model_log_id", sa.String(200)),
        sa.Column("window_ref", postgresql.JSONB),
        sa.Column(
            "explanation", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="alert_status", create_type=False),
            nullable=False,
            server_default="open",
        ),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("assigned_to", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("verdict", postgresql.ENUM(name="verdict", create_type=False)),
        sa.Column("verdict_at", sa.DateTime(timezone=True)),
        sa.Column("verdict_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.PrimaryKeyConstraint("id", "created_at", name="pk_alerts"),
        postgresql_partition_by="RANGE (created_at)",
    )

    op.create_table(
        "models",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="model_kind", create_type=False), nullable=False),
        sa.Column("artifact_uri", sa.Text, nullable=False),
        sa.Column(
            "metrics", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "training_manifest",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status", postgresql.ENUM(name="model_status", create_type=False), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("name", "version", name="uq_models_name_version"),
    )

    op.create_table(
        "model_versions_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("model_id", sa.BigInteger, sa.ForeignKey("models.id"), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True)),
    )

    # Append only (R-31). Deliberately no foreign key on actor_id: a cascade from
    # users would give this table a delete path through the relationship.
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.BigInteger, nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=False),
        sa.Column("target_id", sa.String(120), nullable=False),
        sa.Column(
            "detail", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("ip", postgresql.INET),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])

    op.create_table(
        "thresholds",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(80), nullable=False),
        sa.Column("family", sa.String(80), nullable=False),
        sa.Column("band", sa.String(40), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "family", "band", name="uq_thresholds_tenant_family_band"),
    )

    op.create_table(
        "ingest_stats",
        sa.Column("id", sa.BigInteger, nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("accepted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "rejected_reasons",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("id", "window_start", name="pk_ingest_stats"),
        postgresql_partition_by="RANGE (window_start)",
    )

    for year, month in _INITIAL_MONTHS:
        op.execute(create_partition_sql("alerts", year, month))
        op.execute(create_partition_sql("ingest_stats", year, month))


def downgrade() -> None:
    """Reverse the upgrade: partitions first, then tables in reverse order."""
    for year, month in reversed(_INITIAL_MONTHS):
        op.execute(drop_partition_sql("alerts", year, month))
        op.execute(drop_partition_sql("ingest_stats", year, month))

    for table in reversed(_TABLES_IN_ORDER):
        op.drop_table(table)

    for name, _values in reversed(_ENUMS):
        op.execute(sa.text(f"DROP TYPE IF EXISTS {name}"))
