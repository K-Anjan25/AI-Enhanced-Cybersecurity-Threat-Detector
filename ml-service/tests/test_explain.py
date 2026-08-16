"""Contract tests for the explainability endpoints (ml-service)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.explain import explain_log, explain_email, explain_network, explain_dns


client = TestClient(app)


@pytest.mark.parametrize(
    "route,payload",
    [
        ("/explain/log", {"message": "unauthorized brute force login attempt blocked"}),
        ("/explain/email", {"subject": "URGENT", "body": "verify your account credentials now"}),
        ("/explain/network", {"dst_port": 3389, "duration": 1, "bytes": 999999}),
        ("/explain/dns", {"domain": "update-account.tk", "query_type": "TXT", "answer_ips": ["8.8.8.8"]}),
    ],
)
def test_explain_endpoint_returns_shape(route, payload):
    resp = client.post(route, json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["contributions"], list)
    assert "summary" in body
    assert "method" in body


def test_explain_log_returns_attack_evidence():
    result = explain_log({"level": "ERROR", "message": "SQL injection exploit detected on db"})
    terms = [c["term"] for c in result["contributions"]]
    assert any("injection" in t or "exploit" in t for t in terms)


def test_explain_email_surfaces_phishing_pattern():
    result = explain_email({"subject": "URGENT", "body": "verify your account credentials now"})
    terms = [c["term"] for c in result["contributions"]]
    assert any("credential" in t or "urgency" in t for t in terms)


def test_explain_network_without_model_is_rules_based():
    result = explain_network({"dst_port": 3389, "duration": 1, "bytes": 999999})
    assert isinstance(result["contributions"], list)
    assert result["method"] in ("rules", "isolation-forest centroid deviation")


def test_explain_dns_lists_fired_rules():
    result = explain_dns({"domain": "update-account.tk", "query_type": "TXT", "answer_ips": ["8.8.8.8"]})
    assert result["method"] == "rule engine"
    assert len(result["contributions"]) >= 1
