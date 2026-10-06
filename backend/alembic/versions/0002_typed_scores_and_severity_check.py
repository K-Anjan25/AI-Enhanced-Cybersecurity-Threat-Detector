"""Typed scores and a checked severity (T-321, R-38, R-39).

Revision ID: 0002_typed_scores
Revises: 0001_initial
Create Date: 2026-10-05

``alerts.score`` and ``thresholds.value`` become ``numeric(5, 4)``, and
``alerts.severity`` gains the check constraint R-38 asks for. Both were raised
while writing T-308's row mapping and are fixed here rather than there, because
they are schema changes to a migration no deployment has applied (D-030).

Two things a reviewer should know:

* ``USING <column>::numeric(5, 4)`` is explicit. PostgreSQL would cast a float to
  numeric without it, but the cast is what fixes the scale: 0.9 becomes 0.9000.
  A stored value with more than four decimals would round (half away from zero)
  rather than fail; no score produced here has more than four, and a value that
  did would be a units bug the banding rule's tests refuse.
* The check's values are a literal, not imported from the model: an applied
  migration must not change when the enum does. ``tests/test_schema_conformance.py``
  parses this file and asserts the literal equals ``app.db.models.SEVERITY_CHECK``,
  so the two cannot drift apart without a failing test.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_typed_scores"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

#: R-38's constraint text. Kept in step with ``app.db.models.SEVERITY_CHECK`` by
#: ``tests/test_schema_conformance.py``.
SEVERITY_CHECK = "severity IN ('info', 'low', 'medium', 'high', 'critical')"

#: Table and column of every fixed-precision score.
_SCORE_COLUMNS: tuple[tuple[str, str], ...] = (("alerts", "score"), ("thresholds", "value"))


def upgrade() -> None:
    """Type the score columns and check the severity column."""
    for table, column in _SCORE_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Float(),
            type_=sa.Numeric(5, 4),
            existing_nullable=False,
            postgresql_using=f"{column}::numeric(5, 4)",
        )
    op.create_check_constraint("ck_alerts_severity", "alerts", SEVERITY_CHECK)


def downgrade() -> None:
    """Back to a float score and an unchecked severity."""
    op.drop_constraint("ck_alerts_severity", "alerts", type_="check")
    for table, column in _SCORE_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Numeric(5, 4),
            type_=sa.Float(),
            existing_nullable=False,
            postgresql_using=f"{column}::double precision",
        )
