"""The traffic read model's store: ``flow_events`` (T-418, FR-52).

The traffic explorer counted the records its *alerts* carried: volume was the alerted
subset of the traffic, and an edge meant two entities shared a correlation trace
because there was no flow read model to count relationships from. This migration
creates the table the explorer counts instead.

Four things are deliberate:

* **The columns are the read model's vocabulary.** Timestamp, both addresses, the
  pair's byte and packet totals, and the two fields the explorer can filter on
  (``protocol``, ``direction``). The 25-field ``flow@1`` contract stays on the wire and
  in the scorer's hands; a column nothing reads is a cost on every insert.
* **Bytes are summed once, here.** ``bytes`` is the record's ``src_bytes + dst_bytes``
  and ``packets`` its ``packets``, so no grouping query has to add two columns and the
  addition has one definition — the same rule the log store's ``key`` column follows
  (T-419).
* **No partition.** Like ``log_events`` and unlike ``alerts``, this table is not
  declaratively partitioned: retention reaches it by the same rule the raw records use
  (FR-05's 30 days), which the plan records as an *unevictable* for now rather than
  pretending to enforce here. ``app.db.models.PARTITIONED_TABLES`` is where a scheme
  would be declared.
* **Three indexes, time beside the grouped column.** Every read is a window (R-34), and
  the groupings are by time, by source address and by destination address: ``(timestamp)``
  for the window scan and the bucket series, ``(src_ip, timestamp)`` and
  ``(dst_ip, timestamp)`` for the two ends of the entity and edge folds. Nothing indexes
  ``src_port``/``dst_port``: they are not stored at all, because no read groups by them.

Up creates the table and its indexes. Down drops them, in reverse. Both are offline DDL
like the rest of the chain, and ``tests/test_schema_conformance.py`` checks the result
against the ORM metadata.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_flow_events"
down_revision = "0003_log_events"
branch_labels = None
depends_on = None

_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_flow_events_timestamp", ("timestamp",)),
    ("ix_flow_events_src_ip_timestamp", ("src_ip", "timestamp")),
    ("ix_flow_events_dst_ip_timestamp", ("dst_ip", "timestamp")),
)


def upgrade() -> None:
    """Create the flow store and its indexes."""
    op.create_table(
        "flow_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("src_ip", sa.String(45), nullable=False),
        sa.Column("dst_ip", sa.String(45), nullable=False),
        sa.Column("protocol", sa.String(16), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        # Both totals are written by the ingest path, never by the database: a server
        # default would be a second definition of a number the wire already states.
        sa.Column("bytes", sa.BigInteger, nullable=False),
        sa.Column("packets", sa.BigInteger, nullable=False),
    )
    for name, columns in _INDEXES:
        op.create_index(name, "flow_events", list(columns))


def downgrade() -> None:
    """Drop the indexes and the table."""
    for name, _columns in _INDEXES:
        op.drop_index(name, table_name="flow_events")
    op.drop_table("flow_events")
