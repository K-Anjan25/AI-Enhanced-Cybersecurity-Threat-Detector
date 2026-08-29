"""Connector OAuth API — GitHub App + Slack OAuth."""

from app.models import Org
from app.services import connector_oauth_service


def test_connector_oauth_requires_auth(client):
    r = client.get("/api/v1/connectors/github/oauth/status")
    assert r.status_code == 401


def test_connector_oauth_status_not_connected(client, auth_headers, db_session):
    # auth_headers has org_id, but no OAuth connection yet
    r = client.get("/api/v1/connectors/github/oauth/status", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["connected"] is False


def test_connector_oauth_only_github_slack(client, auth_headers):
    r = client.get("/api/v1/connectors/okta/oauth/start", headers=auth_headers)
    assert r.status_code == 400
    assert "only supported for github and slack" in r.json()["detail"].lower()


def test_connector_oauth_disconnect_not_found(client, auth_headers):
    r = client.delete("/api/v1/connectors/github/oauth", headers=auth_headers)
    assert r.status_code == 404
