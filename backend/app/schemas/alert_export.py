"""The alert batch export's request shape (T-415, FR-23).

Same contract as the hunt export (:mod:`app.schemas.hunt`), for the same reason: the
body **is** the query definition, the rows in the file are the rows the view showed,
and the audit entry records the definition verbatim. What T-415 adds is the *format*:
the triage queue exports the batch it is filtering, and FR-23 asks for CSV and PDF.

The request re-uses :class:`~app.schemas.query.AlertQuery` rather than restating its
fields, so the queue's filters and the export's filters cannot drift apart -- the
failure would be silent, an export whose rows no longer match the view it was
launched from with both halves looking correct in isolation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from app.schemas.hunt import CSV_MEDIA_TYPE
from app.schemas.query import AlertQuery

__all__ = ["AlertExportRequest", "CSV_MEDIA_TYPE", "ExportFormat"]


class ExportFormat(StrEnum):
    """The two shapes an alert batch leaves in (FR-23).

    The values are the wire names, and they are the filename suffixes: one
    spelling for the request, the response's media type and the download.
    """

    CSV = "csv"
    PDF = "pdf"


class AlertExportRequest(AlertQuery):
    """A queue filter, as the body of an export."""

    #: Refused by type. An export mirrors the first page of the query the analyst
    #: ran; a caller who could pass a cursor could export a page nobody saw, and the
    #: audit row would then describe a read that never happened.
    cursor: Annotated[
        None,
        Field(description="Not accepted: an export mirrors the query's first page."),
    ] = None

    format: ExportFormat = Field(
        default=ExportFormat.CSV,
        description=(
            "csv (rows only, for a spreadsheet) or pdf (a report, with the filter on the page)."
        ),
    )

    def to_query(self) -> AlertQuery:
        """The store query this export runs, so its rows are the query's rows."""
        return AlertQuery(**self.model_dump(exclude={"cursor", "format"}))
