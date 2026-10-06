"""T-321: fixed-precision scores and a severity the column checks (R-38, R-39).

The task was raised while writing T-308's row mapping: ``alerts.score`` and
``thresholds.value`` were ``Float`` and ``alerts.severity`` was an unconstrained
``String(20)``. Both are schema changes, and the app runs no PostgreSQL (D-030), so
the claims are checked two ways that need no server:

* the ORM metadata and the DDL it compiles to, so the model cannot quietly stay a
  float; and
* the migration's own SQL, emitted by Alembic in ``--sql`` (offline) mode, so the
  migration that will be applied is the one that was reviewed.

The live round trip -- a score of 0.90 read back as exactly 0.9000 -- is in
``test_migration_live.py``, which skips without ``AEGIS_DATABASE_URL``.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from app.db.models import SEVERITY_CHECK, Alert, Severity, Threshold
from app.services import correlator as correlator_module
from app.services.correlator import Severity as CorrelatorSeverity
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

BACKEND_ROOT = Path(__file__).resolve().parent.parent
VERSIONS = BACKEND_ROOT / "alembic" / "versions"
MIGRATION = VERSIONS / "0002_typed_scores_and_severity_check.py"

#: Offline mode never connects, so any PostgreSQL-shaped URL works.
# The credentials are placeholders for offline DDL generation and never dialled.
_URL = "postgresql://aegis:aegis@localhost:5432/aegis"  # pragma: allowlist secret

SCORE_COLUMNS = ((Alert, "score"), (Threshold, "value"))


def _alembic(*args: str) -> str:
    """Run Alembic and return stdout, or fail with its stderr."""
    result = subprocess.run(
        # S607 is a false positive: sys.executable is an absolute path.
        [sys.executable, "-m", "alembic", *args],  # noqa: S607
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "AEGIS_DATABASE_URL": _URL},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _module_literal(path: Path, name: str) -> object:
    """The literal a migration module assigns to ``name``."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if name in targets:
                return ast.literal_eval(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path.name} does not assign {name}")


# --- the model --------------------------------------------------------------


@pytest.mark.parametrize(("model", "column"), SCORE_COLUMNS)
def test_a_score_column_is_fixed_precision(model: type[object], column: str) -> None:
    """R-39: a score is ``numeric(5, 4)`` in the database, never a float."""
    declared = model.__table__.c[column].type  # type: ignore[attr-defined]
    assert isinstance(declared, sa.Numeric)
    assert not isinstance(declared, sa.Float)
    assert (declared.precision, declared.scale) == (5, 4)
    assert declared.asdecimal is True, "a float would come back, not a Decimal"


def test_the_compiled_ddl_types_the_score_columns() -> None:
    """The claim, in the DDL a server would run."""
    dialect = postgresql.dialect()
    alerts = str(CreateTable(Alert.__table__).compile(dialect=dialect))
    thresholds = str(CreateTable(Threshold.__table__).compile(dialect=dialect))
    assert "score NUMERIC(5, 4) NOT NULL" in alerts
    assert "value NUMERIC(5, 4) NOT NULL" in thresholds
    assert "FLOAT" not in alerts


def test_the_severity_check_is_the_enum() -> None:
    """R-38: the enum is defined once, and the column checks it."""
    assert issubclass(Severity, str), "the column stores the text, not a member repr"
    assert [member.value for member in Severity] == ["info", "low", "medium", "high", "critical"]
    assert SEVERITY_CHECK == "severity IN ('info', 'low', 'medium', 'high', 'critical')"
    assert CorrelatorSeverity is Severity, "the correlator re-exports it, never redefines it"
    assert "Severity" in correlator_module.__all__  # the re-export is public API

    named = {constraint.name: constraint for constraint in Alert.__table__.constraints}
    assert "ck_alerts_severity" in named
    assert str(named["ck_alerts_severity"].sqltext) == SEVERITY_CHECK


def test_the_ranks_are_the_band_order() -> None:
    """The enum carries its own ordering, worst first."""
    assert Severity.critical.rank > Severity.high.rank > Severity.medium.rank
    assert Severity.medium.rank > Severity.low.rank > Severity.info.rank


# --- the migration ----------------------------------------------------------


def test_the_migration_literal_matches_the_model() -> None:
    """An applied migration keeps its literal; a test keeps the two equal."""
    assert _module_literal(MIGRATION, "SEVERITY_CHECK") == SEVERITY_CHECK


def test_the_migration_follows_the_only_initial_revision() -> None:
    """The chain is linear: ``0002`` revises ``0001`` and defines both directions."""
    assert _module_literal(MIGRATION, "revision") == "0002_typed_scores"
    assert _module_literal(MIGRATION, "down_revision") == "0001_initial"
    source = MIGRATION.read_text(encoding="utf-8")
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source


def test_the_migration_chain_has_exactly_one_head() -> None:
    """``head`` has to mean what every reader assumes it means."""
    revisions: dict[str, str | None] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        revisions[str(_module_literal(path, "revision"))] = _module_literal(
            path, "down_revision"
        )  # type: ignore[assignment]
    heads = set(revisions) - {down for down in revisions.values() if down}
    assert heads == {"0002_typed_scores"}


def test_the_offline_upgrade_types_the_columns_and_checks_severity() -> None:
    """Alembic emits the DDL with no server, so CI checks what will be applied."""
    upgraded = _alembic("upgrade", "0001_initial:head", "--sql")
    assert "ALTER TABLE alerts ALTER COLUMN score TYPE NUMERIC(5, 4)" in upgraded
    assert "ALTER TABLE thresholds ALTER COLUMN value TYPE NUMERIC(5, 4)" in upgraded
    assert "USING score::numeric(5, 4)" in upgraded
    assert "ALTER TABLE alerts ADD CONSTRAINT ck_alerts_severity CHECK" in upgraded
    assert SEVERITY_CHECK in upgraded


def test_the_offline_downgrade_reverses_it() -> None:
    """A migration that cannot go back is a trap, not a migration."""
    downgraded = _alembic("downgrade", "head:0001_initial", "--sql")
    assert "ALTER TABLE alerts DROP CONSTRAINT ck_alerts_severity" in downgraded
    assert "ALTER TABLE alerts ALTER COLUMN score TYPE FLOAT" in downgraded
    assert "ALTER TABLE thresholds ALTER COLUMN value TYPE FLOAT" in downgraded
    assert "USING score::double precision" in downgraded
