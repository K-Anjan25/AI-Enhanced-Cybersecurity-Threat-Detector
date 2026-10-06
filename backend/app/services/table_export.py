"""The CSV contract two exports share (T-408, T-415).

Two routes export alert rows — the hunt console's and the triage queue's — and they
export the *same rows in the same columns*, so the rendering lives here rather than
in either of them. Two copies would drift, and the drift would be invisible: both
files would open, and only a reader comparing them would find that one of them had
started quoting or defusing differently.

Three rules, each a decision rather than a formatting detail:

* **The CSV is the wire shape.** Instants are ISO-8601 and numbers are numbers. A
  spreadsheet column of ``06 Oct 2026, 10:04:59Z`` sorts and filters as text, so an
  export that re-rendered the screen's formatting would be a file nobody can
  compute over.
* **A cell that could start a formula is defused.** ``family`` and ``trace_id``
  carry data that arrived from a collector, and a trace id is an *attacker-supplied
  header* (``traceparent``) that the alert row keeps. A cell beginning ``=``, ``+``,
  ``-``, ``@``, a tab or a carriage return is a formula to Excel, Numbers and
  LibreOffice, which for a security export means the report can run code on the
  machine of the person reading it. Those cells are prefixed with an apostrophe,
  which is the OWASP-recommended defence and the least destructive one: the value
  is still legible, and every other cell is untouched. No numeric column here can
  begin with ``-`` -- ids, counts and scores are all non-negative by schema -- so
  the rule never mangles a number.
* **The filter definition goes to the trail, not into the CSV.** Every row would
  repeat the same query, and a preamble line would make the file unparseable by
  anything that does not know this exporter's convention. The audit entry carries
  the window, the filters, the order, the limit and the row count; the filename
  carries the window. The PDF *does* print it, because a PDF is read by a person
  rather than parsed by a program -- see :mod:`app.services.alert_export`.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from app.schemas.hunt import HUNT_CSV_COLUMNS
from app.schemas.query import AlertQuery, AlertRow

__all__ = [
    "cell_text",
    "defuse_formula",
    "query_definition",
    "render_rows_csv",
]

#: Characters that make a spreadsheet treat a cell as a formula.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

#: RFC 4180 says CRLF between records; Excel is the consumer an export is most
#: likely to meet, and it is the reading this repository's other CSV (the dataset
#: loader) does not have to take a position on -- a human-facing export does.
_LINE_TERMINATOR = "\r\n"


def cell_text(value: object) -> str:
    """One value as the text an export writes. ``None`` becomes empty, not ``"None"``.

    Shared by both renderers so a CSV and a PDF cannot disagree about what an
    instant or a score looks like.
    """
    if value is None:
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def defuse_formula(text: str) -> str:
    """A cell a spreadsheet will read as text rather than as a formula."""
    if text.startswith(_FORMULA_STARTS):
        return f"'{text}"
    return text


def render_rows_csv(rows: Sequence[AlertRow], columns: Sequence[str] = HUNT_CSV_COLUMNS) -> str:
    """The rows as RFC-4180 CSV, one header row, in the columns' own order.

    The column set defaults to the published one (``schemas/hunt.py``) and is a
    parameter so a caller can point at it explicitly; it is one constant for both
    exports, because a second list is how two files start disagreeing about which
    fields exist.

    Returns:
        The whole document as text. A row is never skipped: an export that dropped
        a row because a field was empty would be worse than a wide file.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=_LINE_TERMINATOR)
    writer.writerow(list(columns))
    for row in rows:
        record = row.model_dump()
        writer.writerow([defuse_formula(cell_text(record.get(column))) for column in columns])
    return buffer.getvalue()


def query_definition(query: AlertQuery) -> dict[str, object]:
    """The filter definition an audit entry records for one export.

    Absent filters are omitted rather than written as ``null``: the question the
    record answers is "what narrowed this read", and a definition that lists only
    what was set is the shortest true answer. The window and the order are always
    present, because an export with no window cannot exist (R-34) and the order is
    what makes the row set reproducible.

    The cursor is not part of a definition -- an export has no cursor (see
    :class:`~app.schemas.alert_export.AlertExportRequest`).
    """
    definition: dict[str, object] = {
        "start": query.start.isoformat(),
        "end": query.end.isoformat(),
        "order": query.order,
        "limit": query.limit,
    }
    for name, value in (
        ("severity", query.severity),
        ("status", query.status),
        ("family", query.family),
    ):
        if value:
            definition[name] = sorted(value)
    if query.entity_id is not None:
        definition["entity_id"] = query.entity_id
    if query.min_score is not None:
        definition["min_score"] = query.min_score
    return definition
