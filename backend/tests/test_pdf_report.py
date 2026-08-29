"""PDF report rendering — honest, server-side, no external renderer."""

import pytest

from app.services.pdf_report import render_markdown_pdf, _strip_md


def test_strip_md_removes_bold_italic_code():
    assert _strip_md("**bold**") == "bold"
    assert _strip_md("*italic*") == "italic"
    assert _strip_md("`code`") == "code"
    assert _strip_md("# Heading") == "Heading"


def test_render_produces_pdf_bytes():
    md = "# Case #1 - Test\n\n*Generated now by NOCTRA analyst (test (templated fallback)).*\n\n## Summary\nSomething happened\n"
    pdf = render_markdown_pdf(md, case_id=1, title="Test")
    assert pdf.startswith(b"%PDF")
    assert b"Case #1" in pdf or b"Case" in pdf


def test_render_preserves_fallback_note():
    md = "# Case #2 - Leak\n\n*Generated now by NOCTRA analyst (claude-3 (templated fallback)).*\n\n## Summary\nLeaked credential in use\n"
    pdf = render_markdown_pdf(md, case_id=2)
    # fallback note must be preserved verbatim — honesty contract
    assert b"templated fallback" in pdf


def test_render_strips_markdown_syntax():
    md = "# Case #3\n\n**Bold** and *italic* and `code`\n\n| Asset | Value |\n| --- | --- |\n| host | server-1 |\n"
    pdf = render_markdown_pdf(md, case_id=3)
    assert b"**" not in pdf
    assert b"| --- |" not in pdf


def test_render_empty_raises():
    with pytest.raises(ValueError):
        render_markdown_pdf("", case_id=1)
    with pytest.raises(ValueError):
        render_markdown_pdf("   \n  ", case_id=1)


def test_render_missing_reportlab_raises(monkeypatch):
    # Simulate missing reportlab by making import fail
    import sys
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("reportlab"):
            raise ImportError("No module named 'reportlab'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # Need to reimport module to trigger lazy import inside function — but function does lazy import
    # So calling render should raise RuntimeError
    with pytest.raises(RuntimeError, match="reportlab"):
        render_markdown_pdf("# Case #1\n\nSummary\n", case_id=1)


def test_render_table():
    md = "# Case #4\n\n## Blast radius\n\n| Asset type | Value |\n| --- | --- |\n| host | web-01 |\n| account | jdoe |\n"
    pdf = render_markdown_pdf(md, case_id=4)
    assert pdf.startswith(b"%PDF")
    assert b"web-01" in pdf
    assert b"jdoe" in pdf
