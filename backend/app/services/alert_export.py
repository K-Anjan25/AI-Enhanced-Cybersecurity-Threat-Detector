r"""The alert batch as a PDF report (T-415, FR-23).

The triage queue's export answers in two shapes, and they are for two readers:

* **CSV** is for a spreadsheet: rows and nothing else, the filter definition in the
  audit trail (:mod:`app.services.table_export`).
* **PDF** is for a person: a report that has to say *what it is* before it shows
  rows. So the first thing on the page is the window and the filters that produced
  it, and a truncation is stated in the header -- an unattributed table of alerts is
  a document somebody forwards without knowing what it covers.

**The PDF is written here rather than by a library, and that is a size decision.**
A page of fixed-width text with a core font and no compression is about a hundred
lines, it has no dependency to pin or patch, and it is deterministic, which is what
makes it testable: the tests read the bytes back and assert on the strings this
module writes. No compression is deliberate for that reason -- a report is
kilobytes, and an inspector can read the file.

Three limitations are stated rather than hidden:

* **Instants are rendered to the second.** A report reads better without
  microseconds, and the column would not otherwise fit the page. The CSV keeps the
  exact wire value; the two files are for different readers.
* **The core font is WinAnsi.** A character outside it renders as ``?``. This
  build's columns are ids, instants, enums and trace ids, and the trace id is the
  one attacker-supplied field in the table (``traceparent``), so the substitution is
  documented rather than silent -- and ``(``, ``)`` and ``\\`` are escaped, which is
  the injection this format actually has.
* **A cell too long for its column is clipped** with an ASCII ellipsis, because a
  page cannot scroll. The columns are weighted so that the values this build
  produces fit: a 55-character W3C traceparent is inside its column's 71 characters.
  The CSV is the complete machine-readable copy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from app.schemas.hunt import HUNT_CSV_COLUMNS
from app.schemas.query import AlertQuery, AlertRow
from app.services.table_export import cell_text, query_definition

__all__ = [
    "PDF_MEDIA_TYPE",
    "alert_export_filename",
    "definition_line",
    "render_rows_pdf",
]

#: The media type the report answers with.
PDF_MEDIA_TYPE: Final = "application/pdf"

#: A4 landscape, in points. The row has eleven columns, so the long edge is the
#: reading edge.
_PAGE_WIDTH: Final = 842
_PAGE_HEIGHT: Final = 595
_MARGIN: Final = 28
_ROW_HEIGHT: Final = 12
_ROW_FONT: Final = 6.5
_HEAD_FONT: Final = 6.5
_TITLE_FONT: Final = 13
_META_FONT: Final = 8.5

#: Where the column headers and the first data row sit, as text baselines.
_HEADER_Y: Final = _PAGE_HEIGHT - 112
_LAST_ROW_Y: Final = _MARGIN + 6

#: Column weights, summing to 1.0: each is a share of the usable page width. They
#: are chosen from the values the columns actually hold -- a trace id is the longest
#: and the one an analyst reads, so it gets the most room; an id or a score gets
#: almost none. A column in ``HUNT_CSV_COLUMNS`` with no weight here fails a test
#: rather than silently producing a zero-width column.
_COLUMN_WEIGHTS: Final[dict[str, float]] = {
    "id": 0.04,
    "created_at": 0.105,
    "entity_id": 0.045,
    "family": 0.085,
    "severity": 0.055,
    "score": 0.045,
    "status": 0.055,
    "first_seen": 0.105,
    "last_seen": 0.105,
    "occurrence_count": 0.065,
    "trace_id": 0.295,
}

#: Rows a page holds, derived from the layout rather than typed in.
_ROWS_PER_PAGE: Final = int((_HEADER_Y - _ROW_HEIGHT - _LAST_ROW_Y) // _ROW_HEIGHT) + 1


def definition_line(query: AlertQuery) -> str:
    """The filter definition as one line a reader can check the rows against.

    Built from the same mapping the audit entry records, so the file and the trail
    cannot describe two different reads.
    """
    return "Filter: " + " · ".join(
        f"{name}={value}" for name, value in query_definition(query).items()
    )


def alert_export_filename(query: AlertQuery, suffix: str) -> str:
    """A filename that carries the window, so a saved file says when it covers.

    The instants are colon-free (``2026-10-06T10-00-00Z``) because the filename
    travels through ``Content-Disposition`` and a filesystem, and a colon is illegal
    in a Windows path element -- a download that silently renames itself is a small
    lie about what the file contains.
    """
    start = query.start.isoformat().replace(":", "-")
    end = query.end.isoformat().replace(":", "-")
    return f"aegis-alerts-{start}-to-{end}.{suffix}"


def _pdf_cell(value: object) -> str:
    """One cell as the report writes it: instants to the second, the rest as the CSV."""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return cell_text(value)


def _pdf_text(value: str) -> str:
    r"""One PDF string literal's content: escaped, and inside the core font's range.

    ``(``, ``)`` and ``\\`` are the string delimiters' own characters; everything
    outside WinAnsi becomes ``?`` (see the module docstring).
    """
    out: list[str] = []
    for character in value:
        if character in "()\\":
            out.append("\\" + character)
        elif 32 <= ord(character) < 127 or 160 <= ord(character) <= 255:
            out.append(character)
        else:
            out.append("?")
    return "".join(out)


def _clip(text: str, width: float) -> str:
    """Clip a cell to its column, with an ASCII ellipsis rather than a silent cut."""
    limit = max(4, int(width / (_ROW_FONT * 0.5)))
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _column_widths() -> list[float]:
    usable = _PAGE_WIDTH - 2 * _MARGIN
    return [_COLUMN_WEIGHTS[column] * usable for column in HUNT_CSV_COLUMNS]


def _text(x: float, y: float, size: float, value: str, font: str = "F1") -> str:
    """One string, absolutely positioned.

    ``Tm`` rather than ``Td``, so a line's position does not depend on the line
    before it.
    """
    return f"BT /{font} {size} Tf 1 0 0 1 {x:.1f} {y:.1f} Tm ({_pdf_text(value)}) Tj ET"


def _page_lines(
    rows: list[list[str]],
    *,
    page: int,
    pages: int,
    query: AlertQuery,
    generated_at: datetime,
    total: int,
    truncated: bool,
) -> list[str]:
    """The operators for one page: the header band, the column headers, the rows."""
    widths = _column_widths()
    title = (
        "Aegis alert export" if pages == 1 else f"Aegis alert export - page {page + 1} of {pages}"
    )
    lines = [_text(_MARGIN, _PAGE_HEIGHT - 44, _TITLE_FONT, title)]
    if page == 0:
        lines.append(_text(_MARGIN, _PAGE_HEIGHT - 62, _META_FONT, definition_line(query)))
        lines.append(
            _text(
                _MARGIN,
                _PAGE_HEIGHT - 74,
                _META_FONT,
                f"Generated {generated_at.isoformat(timespec='seconds')} · {total} rows"
                + (
                    " (the first page of a longer result; the query held more)" if truncated else ""
                ),
            )
        )
    else:
        lines.append(_text(_MARGIN, _PAGE_HEIGHT - 62, _META_FONT, definition_line(query)))
    x = float(_MARGIN)
    for index, column in enumerate(HUNT_CSV_COLUMNS):
        lines.append(_text(x, _HEADER_Y, _HEAD_FONT, _clip(column, widths[index]), "F2"))
        x += widths[index]
    y = _HEADER_Y - _ROW_HEIGHT
    for row in rows:
        x = float(_MARGIN)
        for index, cell in enumerate(row):
            lines.append(_text(x, y, _ROW_FONT, _clip(cell, widths[index])))
            x += widths[index]
        y -= _ROW_HEIGHT
    return lines


def _content_stream(lines: list[str]) -> bytes:
    """A page's content stream. Uncompressed on purpose (module docstring)."""
    body = "\n".join(lines).encode("latin-1")
    return b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"


def _assemble(bodies: list[bytes]) -> bytes:
    """Objects in number order, then the cross-reference table and the trailer.

    Object numbers are positional: this takes the bodies in the order they are
    numbered, so ``1 0 obj`` is the catalog and every reference in the document is an
    index into this list.
    """
    document = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(bodies, start=1):
        offsets.append(len(document))
        document += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_at = len(document)
    document += f"xref\n0 {len(bodies) + 1}\n".encode("ascii")
    document += b"0000000000 65535 f \n"
    for offset in offsets:
        document += f"{offset:010d} 00000 n \n".encode("ascii")
    document += (
        f"trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("ascii")
    return bytes(document)


def render_rows_pdf(
    rows: list[AlertRow],
    query: AlertQuery,
    *,
    generated_at: datetime,
    truncated: bool = False,
) -> bytes:
    """The rows as a paginated PDF report, with the filter definition on page one.

    Args:
        rows: The rows the export is of -- the same list the CSV renderer is given,
            so the two documents cannot contain different alert sets.
        query: The definition that produced them, printed on the first page.
        generated_at: When the file was rendered, stated so a reader knows its age.
        truncated: Whether the query held more rows than the export's limit. Stated
            in the header rather than left to be inferred from the row count.

    Returns:
        The whole document as bytes. Empty rows still produce one page: a report
        that says "0 rows" is an answer, and a caller that got no bytes back would
        have to guess whether the export ran.
    """
    columns = list(HUNT_CSV_COLUMNS)
    rendered = [[_pdf_cell(row.model_dump().get(column)) for column in columns] for row in rows]
    pages = max(1, -(-len(rendered) // _ROWS_PER_PAGE))
    page_bodies: list[bytes] = []
    for page in range(pages):
        chunk = rendered[page * _ROWS_PER_PAGE : (page + 1) * _ROWS_PER_PAGE]
        page_bodies.append(
            _content_stream(
                _page_lines(
                    chunk,
                    page=page,
                    pages=pages,
                    query=query,
                    generated_at=generated_at,
                    total=len(rendered),
                    truncated=truncated,
                )
            )
        )

    kids = " ".join(f"{5 + 2 * page} 0 R" for page in range(pages))
    bodies: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    for page, content in enumerate(page_bodies):
        bodies.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {6 + 2 * page} 0 R >>"
            ).encode("ascii")
        )
        bodies.append(content)
    return _assemble(bodies)


def now_utc() -> datetime:
    """The clock, named so a test can pass its own instant in."""
    return datetime.now(UTC)
