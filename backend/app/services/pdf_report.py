"""PDF rendering for case reports — honest, server-side, no external renderer.

The report is generated from the recorded markdown in case.report, which itself
was built from real rows at decision time. The PDF must not present templated
fallback reasoning as verified analysis, so the engine note (including
'(templated fallback)') is preserved verbatim.

Dependency: reportlab (pure Python). Imported lazily so a missing library does
not break startup — the endpoint returns 501 with a clear message.
"""

from __future__ import annotations

import io
import re
from typing import Any


def _strip_md(text: str) -> str:
    """Very small markdown stripper for the subset build_case_report emits."""
    if not text:
        return "-"
    # Remove bold/italic markers, inline code backticks
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    # Remove leading # for headings (we handle headings separately)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return text.strip()


def render_markdown_pdf(markdown_text: str, case_id: int | str = "?", title: str = "") -> bytes:
    """Render markdown report to PDF bytes.

    Uses pageCompression=0 so the content stream is uncompressed and text is
    greppable in tests (and by simple tools). Returns bytes starting with %PDF.
    Raises RuntimeError if reportlab is not installed.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
    except ImportError as exc:
        raise RuntimeError("PDF export needs reportlab (pip install reportlab)") from exc

    if not markdown_text or not markdown_text.strip():
        raise ValueError("No report content to render")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=f"NOCTRA Case #{case_id} Report",
        author="NOCTRA",
        pageCompression=0,  # uncompressed for test greppability
    )

    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    normal = styles["Normal"]
    normal.leading = 14
    # preserve engine note styling
    italic = ParagraphStyle("italic", parent=normal, fontName="Helvetica-Oblique", textColor=colors.HexColor("#555555"))

    story: list[Any] = []

    # Split markdown into sections roughly
    lines = markdown_text.splitlines()
    # First line is title
    if lines and lines[0].startswith("# "):
        story.append(Paragraph(_strip_md(lines[0]), h1))
        story.append(Spacer(1, 0.15 * inch))
        lines = lines[1:]

    # Process remaining: headings, paragraphs, tables, bullets
    table_buffer: list[list[str]] = []
    in_table = False

    def flush_table():
        nonlocal table_buffer, in_table
        if not table_buffer:
            return
        # Build table
        try:
            t = Table(table_buffer, colWidths=[1.5 * inch, 4.5 * inch])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(t)
            story.append(Spacer(1, 0.12 * inch))
        except Exception:
            # fallback: render as text
            for row in table_buffer:
                story.append(Paragraph(" | ".join(row), normal))
        table_buffer = []
        in_table = False

    for raw in lines:
        line = raw.strip()
        if not line:
            if in_table:
                flush_table()
            story.append(Spacer(1, 0.08 * inch))
            continue

        if line.startswith("|") and "|" in line[1:]:
            # table row
            if not in_table:
                in_table = True
                table_buffer = []
            # split by |, strip empty first/last
            cells = [c.strip() for c in line.strip("|").split("|")]
            # skip separator row
            if all(set(c) <= {"-", ":", " "} for c in cells):
                continue
            table_buffer.append([_strip_md(c) for c in cells])
            continue
        else:
            if in_table:
                flush_table()

        if line.startswith("## "):
            story.append(Paragraph(_strip_md(line), h2))
            story.append(Spacer(1, 0.08 * inch))
        elif line.startswith("*") and line.endswith("*") and len(line) < 200:
            # italic note (engine note)
            story.append(Paragraph(_strip_md(line), italic))
            story.append(Spacer(1, 0.08 * inch))
        elif line.startswith("- "):
            story.append(Paragraph(f"• {_strip_md(line[2:])}", normal))
        else:
            story.append(Paragraph(_strip_md(line), normal))

    if in_table:
        flush_table()

    doc.build(story)
    return buf.getvalue()
