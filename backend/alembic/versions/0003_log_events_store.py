"""The log read model's store: ``log_events`` (T-419, FR-02).

The log explorer read a process's own bounded tail (T-407): accepted lines were
validated, admitted and published, and then kept nowhere a second process or a
restart could reach them. This migration creates the table they are stored in, so a
read is answered from the database.

Three things are deliberate:

* **The cluster key is a stored column, not an expression.** ``key`` holds exactly
  what ``app.services.log_tail.cluster_key`` computes — the collector's template id,
  or ``message:<sha256[:12]>`` for a line that carried none. Storing it keeps the
  fold to one definition and makes "the lines behind this cluster" a plain indexed
  lookup; recomputing a digest per row per query would also mean the read model and
  the live tail could disagree about what a cluster is.
* **No default export and no partition.** Unlike ``alerts`` and ``ingest_stats``,
  this table is not declaratively partitioned: the read API never scans it without a
  time bound, and retention reaches it by the same rule the raw records use
  (FR-05's 30 days), which is recorded in the plan as an *unevictable* for now
  rather than pretended to be enforced here. A partition scheme is a follow-up, and
  `app.db.models.PARTITIONED_TABLES` is where it would be declared.
* **Three indexes, all time-first-pair.** Every read is "these keys, in this
  window": ``(timestamp)`` for a window scan, ``(key, timestamp)`` for a cluster
  fold and the row lookup behind it, ``(host, timestamp)`` for the tail's host
  filter. Nothing indexes ``message``; text search is deliberately not offered.

Up creates the table and its indexes. Down drops them, in reverse. Both are offline
DDL like the rest of the chain here: declarative partitioning aside, nothing in this
file needs a live server to be correct, and ``tests/test_schema_conformance.py``
checks it against the ORM metadata.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_log_events"
down_revision = "0002_typed_scores"
branch_labels = None
depends_on = None

_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_log_events_timestamp", ("timestamp",)),
    ("ix_log_events_key_timestamp", ("key", "timestamp")),
    ("ix_log_events_host_timestamp", ("host", "timestamp")),
)


def upgrade() -> None:
    """Create the log store and its indexes."""
    op.create_table(
        "log_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("host", sa.String(512), nullable=False),
        sa.Column("service", sa.String(200), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("template_id", sa.String(200), nullable=True),
        sa.Column(
            "parameters",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # The cluster key, written with the line. Deliberately no server default: a
        # row whose key was computed by the database would be a second definition of
        # the fold, and the two would drift.
        sa.Column("key", sa.String(300), nullable=False),
    )
    for name, columns in _INDEXES:
        op.create_index(name, "log_events", list(columns))


def downgrade() -> None:
    """Drop the indexes and the table."""
    for name, _columns in _INDEXES:
        op.drop_index(name, table_name="log_events")
    op.drop_table("log_events")
