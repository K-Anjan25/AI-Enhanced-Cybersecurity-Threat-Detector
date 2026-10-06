"""The hunt export's request shape and its CSV contract (T-408).

An export is a *read that leaves the system*, which is why it is the one read in
this codebase with a request body: the body **is** the query definition, and the
audit entry records it verbatim. A reviewer asking "what did this analyst take out
of the system?" reads the trail and finds the same filters the screen ran.

The request re-uses :class:`~app.schemas.query.AlertQuery` rather than restating
its fields. Two copies of a filter set drift, and the failure would be silent: an
export whose rows no longer match the view it was launched from, with both halves
looking correct in isolation. The one thing an export does *not* accept is a
cursor, and that is refused by type rather than ignored -- see below.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.schemas.query import AlertQuery

__all__ = ["CSV_MEDIA_TYPE", "HUNT_CSV_COLUMNS", "HuntExportRequest"]

#: The media type an export answers with.
CSV_MEDIA_TYPE = "text/csv"

#: The CSV's columns, in order. This is the **wire** shape, not the rendered one:
#: instants are ISO-8601 and numbers are numbers, because a spreadsheet column of
#: `06 Oct 2026, 10:04:59Z` sorts and filters as text. Every field of the row is
#: here, including the ones the table hides by default -- the column picker is a
#: reading aid on screen, and silently dropping a field from an export would be
#: data loss nobody asked for.
HUNT_CSV_COLUMNS: tuple[str, ...] = (
    "id",
    "created_at",
    "entity_id",
    "family",
    "severity",
    "score",
    "status",
    "first_seen",
    "last_seen",
    "occurrence_count",
    "trace_id",
)


class HuntExportRequest(AlertQuery):
    """A hunt's query, as the body of an export.

    The filter set and the window are the alert query's own, so an export and the
    view it mirrors cannot disagree about what "matching" means.
    """

    #: Refused by type. An export mirrors the first page of the query the analyst
    #: ran; a caller who could pass a cursor could export a page nobody saw, and
    #: the audit row would then describe a read that never happened.
    cursor: Annotated[
        None,
        Field(description="Not accepted: an export mirrors the query's first page."),
    ] = None

    def to_query(self) -> AlertQuery:
        """The store query this export runs, so its rows are the query's rows."""
        return AlertQuery(**self.model_dump(exclude={"cursor"}))
