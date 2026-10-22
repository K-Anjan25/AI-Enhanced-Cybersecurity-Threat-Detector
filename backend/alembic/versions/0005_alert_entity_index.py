"""An index on ``alerts.entity_id`` for the entity retention sweep (NFR-05).

Retention now deletes entity rows that no retained alert refers to. That check is a
``NOT EXISTS`` on ``alerts`` keyed by ``entity_id``. The foreign key does not index its
referencing column in PostgreSQL, so without this index each candidate entity costs a
scan of every alert partition.

On a declaratively partitioned parent, ``CREATE INDEX`` creates the index on every
partition, including partitions created later, so one statement covers the table. Down
drops it. Offline DDL like the rest of the chain; ``tests/test_schema_conformance.py``
checks the result against the ORM metadata.
"""

from __future__ import annotations

from alembic import op

revision = "0005_alert_entity_index"
down_revision = "0004_flow_events"
branch_labels = None
depends_on = None

_INDEX = "ix_alerts_entity_id"


def upgrade() -> None:
    """Index the foreign key the entity sweep filters on."""
    op.create_index(_INDEX, "alerts", ["entity_id"])


def downgrade() -> None:
    """Drop the index."""
    op.drop_index(_INDEX, table_name="alerts")
