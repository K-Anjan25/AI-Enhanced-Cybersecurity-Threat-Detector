"""The hunt console's CSV rendering and the audit definition it records (T-408).

The rendering itself moved to :mod:`app.services.table_export` when the triage
queue's export (T-415) needed the same rows in the same columns; the rules it
follows are documented there. Two things stay here because they are the hunt's:

* the **filename**, which says ``aegis-hunt`` where the queue's says ``aegis-alerts``;
* the import surface its callers and tests already use, kept as a re-export rather
  than churned: ``render_rows_csv`` and ``query_definition`` are the same functions
  the queue's export calls, so the two files cannot drift.
"""

from __future__ import annotations

from app.schemas.hunt import HUNT_CSV_COLUMNS
from app.schemas.query import AlertQuery
from app.services.table_export import (
    cell_text,
    defuse_formula,
    query_definition,
    render_rows_csv,
)

__all__ = [
    "HUNT_CSV_COLUMNS",
    "cell_text",
    "defuse_formula",
    "export_filename",
    "query_definition",
    "render_rows_csv",
]


def export_filename(query: AlertQuery) -> str:
    """A filename that carries the window, so a saved file says when it covers.

    The instants are colon-free (``2026-10-06T10-00-00Z``) because the filename
    travels through ``Content-Disposition`` and a filesystem, and a colon is illegal
    in a Windows path element -- a download that silently renames itself is a small
    lie about what the file contains.
    """
    start = query.start.isoformat().replace(":", "-")
    end = query.end.isoformat().replace(":", "-")
    return f"aegis-hunt-{start}-to-{end}.csv"
