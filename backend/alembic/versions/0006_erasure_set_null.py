"""Erasure can delete a user without deleting the history that names them (NFR-05, R-37).

Three foreign keys point at ``users.id`` with no ``ON DELETE`` action, so deleting a
user who ever triaged an alert would fail with a constraint violation, and erasure
could never reach the ``users`` table. The three are:

* ``alerts.assigned_to``
* ``alerts.verdict_by``
* ``model_versions_history.promoted_by``

They change to ``ON DELETE SET NULL``. The alert, its verdict and the promotion record
all stay; only the pointer to the person is cleared. That is the same choice the
erasure service makes for entities (redact the identifier, keep the record), and it is
a decision recorded in memory.md (D-096), not a default. ``audit_log.actor_id`` has no
foreign key by design (R-31) and is reported as preserved, not changed here.

Constraint names are PostgreSQL's defaults (``<table>_<column>_fkey``), which is what
``0001_initial`` produced. Down restores the plain foreign keys.
"""

from __future__ import annotations

from alembic import op

revision = "0006_erasure_set_null"
down_revision = "0005_alert_entity_index"
branch_labels = None
depends_on = None

#: (table, column) of every foreign key to ``users.id`` that erasure must clear.
_REFERENCES: tuple[tuple[str, str], ...] = (
    ("alerts", "assigned_to"),
    ("alerts", "verdict_by"),
    ("model_versions_history", "promoted_by"),
)


def _name(table: str, column: str) -> str:
    return f"{table}_{column}_fkey"


def upgrade() -> None:
    """Replace each user reference with one that nulls on delete."""
    for table, column in _REFERENCES:
        op.drop_constraint(_name(table, column), table, type_="foreignkey")
        op.create_foreign_key(
            _name(table, column), table, "users", [column], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    """Restore the plain foreign keys. Refuses nothing: no data is changed."""
    for table, column in _REFERENCES:
        op.drop_constraint(_name(table, column), table, type_="foreignkey")
        op.create_foreign_key(_name(table, column), table, "users", [column], ["id"])
