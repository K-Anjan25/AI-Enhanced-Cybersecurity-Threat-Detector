"""A Suricata alert posted to ingest is visible on the alerts API (Phase 1 gap).

Before this, the alert event landed only in the log tail: the rule engine scored flows
and the correlator never saw the sensor's own alert. This drives the real routes.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.auth.tokens import TokenService
from app.core.config import Environment, Settings
from app.main import create_app
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app/services/capture/bridges"))
from suricata_bridge import parse_alert, to_log_v1  # noqa: E402

SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret

EVE = {
    "event_type": "alert",
    "timestamp": "2026-10-31T10:00:00.000000+0000",
    "src_ip": "10.0.0.5",
    "src_port": 5555,
    "dest_ip": "203.0.113.9",
    "dest_port": 4444,
    "proto": "TCP",
    "alert": {
        "signature_id": 2100498,
        "signature": "ET MALWARE test beacon",
        "category": "A Network Trojan was detected",
        "severity": 1,
        "action": "allowed",
    },
}


@pytest.fixture
def client() -> TestClient:
    settings = Settings(env=Environment.TEST, service_name="aegis-backend-test", secret_key=SECRET,
                        log_level="WARNING")
    built = create_app(settings)
    built.state.token_service = TokenService(SECRET)
    with TestClient(built) as test_client:
        yield test_client


def _headers(client: TestClient, role: str) -> dict[str, str]:
    pair = client.app.state.token_service.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def test_suricata_alert_appears_on_alerts_api(client: TestClient) -> None:
    # The event must sit inside the read window, which ends at the wall clock.
    recent = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    line = json.dumps(to_log_v1(parse_alert({**EVE, "timestamp": recent}))).encode()
    posted = client.post(
        "/api/v1/ingest/logs",
        content=line,
        headers={**_headers(client, "analyst"), "content-type": "application/x-ndjson"},
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["accepted"] == 1

    read = client.get(
        "/api/v1/alerts",
        params={"start": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                "end": datetime.now(UTC).isoformat()},
        headers=_headers(client, "viewer"),
    )
    assert read.status_code == 200, read.text
    body = read.json()
    items = body.get("items", body if isinstance(body, list) else [])
    families = [item.get("family") for item in items]
    assert "ids:A Network Trojan was detected" in families


def test_daily_report_counts_stored_alerts_and_states_them(client: TestClient) -> None:
    recent = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    line = json.dumps(to_log_v1(parse_alert({**EVE, "timestamp": recent}))).encode()
    client.post(
        "/api/v1/ingest/logs",
        content=line,
        headers={**_headers(client, "analyst"), "content-type": "application/x-ndjson"},
    )
    day = datetime.now(UTC).date().isoformat()
    report = client.get(
        "/api/v1/reports/daily", params={"day": day}, headers=_headers(client, "viewer")
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["source"] == "stored alerts only"
    assert body["totals"]["alerts"] == 1
    assert body["totals"]["by_severity"]["critical"] == 1
    assert body["facts"][0].startswith("1 alerts were recorded on")
    bad = client.get(
        "/api/v1/reports/daily", params={"day": "31/10/2026"}, headers=_headers(client, "viewer")
    )
    assert bad.status_code == 400
