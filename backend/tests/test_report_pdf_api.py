"""PDF report endpoint — HTTP layer."""

import pytest

from app.core.config import settings
from app.models import Org
from app.services import scenario, analyst_service


@pytest.fixture(autouse=True)
def _force_llm_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_ENABLED", False)


def test_report_pdf_downloads_for_decided_case(client, auth_headers):
    # create case via API (ensures org matches)
    r = client.post("/api/v1/analyst/simulate?scenario_type=credential_leak", headers=auth_headers)
    assert r.status_code == 201, r.text
    case_id = r.json()["id"]

    # approve to generate report
    r2 = client.post(f"/api/v1/analyst/cases/{case_id}/approve", headers=auth_headers)
    assert r2.status_code == 200, r2.text

    # download PDF
    r3 = client.get(f"/api/v1/analyst/cases/{case_id}/report.pdf", headers=auth_headers)
    assert r3.status_code == 200, r3.text
    assert r3.headers["content-type"] == "application/pdf"
    assert "noctra-case-" in r3.headers["content-disposition"]
    assert r3.content.startswith(b"%PDF")
    # honesty: fallback note preserved
    assert b"templated fallback" in r3.content or b"fallback" in r3.content.lower()
    # no markdown leakage
    assert b"| --- |" not in r3.content


def test_report_pdf_refuses_undecided_case(client, auth_headers):
    r = client.post("/api/v1/analyst/simulate?scenario_type=phishing_outbreak", headers=auth_headers)
    assert r.status_code == 201
    case_id = r.json()["id"]

    r2 = client.get(f"/api/v1/analyst/cases/{case_id}/report.pdf", headers=auth_headers)
    assert r2.status_code == 409
    assert "No report yet" in r2.text


def test_report_pdf_404_for_missing_case(client, auth_headers):
    r = client.get("/api/v1/analyst/cases/999999/report.pdf", headers=auth_headers)
    assert r.status_code == 404


def test_report_pdf_requires_auth(client):
    r = client.get("/api/v1/analyst/cases/1/report.pdf")
    assert r.status_code == 401


def test_report_pdf_reports_missing_renderer(client, auth_headers, monkeypatch):
    # create and approve case
    r = client.post("/api/v1/analyst/simulate?scenario_type=credential_leak", headers=auth_headers)
    assert r.status_code == 201
    case_id = r.json()["id"]
    client.post(f"/api/v1/analyst/cases/{case_id}/approve", headers=auth_headers)

    # monkeypatch render to raise RuntimeError
    import app.services.pdf_report as pdf_mod

    def fake_render(*args, **kwargs):
        raise RuntimeError("PDF export needs reportlab (pip install reportlab)")

    monkeypatch.setattr(pdf_mod, "render_markdown_pdf", fake_render)

    r2 = client.get(f"/api/v1/analyst/cases/{case_id}/report.pdf", headers=auth_headers)
    assert r2.status_code == 501
    assert "reportlab" in r2.text.lower()
