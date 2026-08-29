"""Phase 46-48: OAuth refresh + secret rotation + real Google Workspace/AzureAD fetch, API keys + service accounts + per-org rate limiting, evidence bundle PDF."""

import json
from unittest.mock import MagicMock, patch

from app.models import Org
from app.services import apikey_service, connector_service
from app.core.secrets import encrypt_secret as _encrypt_token, decrypt_secret as _decrypt_token


def _get_org_from_auth(db_session):
    from app.models import User
    user = db_session.query(User).filter(User.username == "analyst1").first()
    if user:
        return db_session.query(Org).filter(Org.id == user.org_id).first()
    return db_session.query(Org).first()


def test_oauth_refresh_logic(client, auth_headers, db_session):
    """Phase 46: OAuth token refresh decrypts refresh token and POSTs refresh grant."""
    # Create org and OAuth record with expired access token but valid refresh token
    org = _get_org_from_auth(db_session)
    assert org is not None
    # Use github for test
    from app.models import ConnectorOAuth

    # Encrypt tokens
    enc_access = _encrypt_token("old_access_token")
    enc_refresh = _encrypt_token("my_refresh_token")
    from datetime import datetime, timezone, timedelta

    rec = ConnectorOAuth(
        org_id=org.id,
        connector_id="github",
        provider="github",
        access_token_encrypted=enc_access,
        refresh_token_encrypted=enc_refresh,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # expired
        account_name="testuser",
    )
    db_session.add(rec)
    db_session.commit()

    # Mock requests.post to return new tokens
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 3600,
    }
    mock_resp.raise_for_status = MagicMock()

    # Mock _get_oauth_config to return dummy config so refresh doesn't fail due to missing env
    dummy_cfg = {
        "client_id": "dummy_id",
        "client_secret": "dummy_secret",
        "token_url": "https://example.com/token",
        "scopes": "dummy",
        "provider": "github",
    }

    with patch("app.services.connector_oauth_service.requests.post", return_value=mock_resp) as mock_post, patch(
        "app.services.connector_oauth_service._get_oauth_config", return_value=dummy_cfg
    ):
        from app.services.connector_oauth_service import get_oauth_token

        # get_oauth_token should trigger refresh
        new_token = get_oauth_token(db_session, org_id=org.id, connector_id="github")
        assert new_token == "new_access_token", f"got {new_token}"
        # Check that refresh endpoint was called
        assert mock_post.called
        # Verify DB updated
        db_session.refresh(rec)
        assert rec.access_token_encrypted is not None
        assert _decrypt_token(rec.access_token_encrypted) == "new_access_token"


def test_secret_rotation_endpoint(client, auth_headers, db_session):
    """Phase 46: POST /connectors/{id}/rotate-secret generates new secret once."""
    org = _get_org_from_auth(db_session)
    assert org is not None
    # Create a connector config with ingest token
    cfg = connector_service.upsert_config(
        db_session,
        org_id=org.id,
        connector_id="okta",
        payload={"mode": "push", "ingest_token": "old_secret_123", "enabled": True},
        actor="tester",
    )
    assert cfg["has_ingest_token"] is True

    # Rotate
    r = client.post(f"/api/v1/connectors/okta/rotate-secret", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "ingest_token" in data
    assert data["connector_id"] == "okta"
    assert len(data["ingest_token"]) > 20
    assert data["ingest_token"] != "old_secret_123"

    # Old secret should no longer work for ingest (but we can't test push ingest without token? We can)
    # Try ingest with old secret -> should fail 401
    r2 = client.post(
        "/api/v1/connectors/ingest/okta",
        json={"events": [{"message": "test"}]},
        headers={"X-Connector-Token": "old_secret_123"},
    )
    assert r2.status_code == 401

    # New secret should work
    r3 = client.post(
        "/api/v1/connectors/ingest/okta",
        json={"events": [{"message": "test new secret"}]},
        headers={"X-Connector-Token": data["ingest_token"]},
    )
    assert r3.status_code == 201, r3.text


def test_gworkspace_azuread_oauth_allowed(client, auth_headers):
    """Phase 46: gworkspace and azuread OAuth start should be allowed (not 400 unsupported)."""
    # Without client_id configured, it returns 400 \"OAuth not configured\" — that's allowed, just not \"only supported for github and slack\"
    r = client.get("/api/v1/connectors/gworkspace/oauth/start", headers=auth_headers)
    assert r.status_code in (400, 422, 302, 500), f"unexpected {r.status_code} {r.text}"
    assert "only supported for github and slack" not in r.text.lower()

    r2 = client.get("/api/v1/connectors/azuread/oauth/start", headers=auth_headers)
    assert r2.status_code in (400, 422, 302, 500)
    assert "only supported for github and slack" not in r2.text.lower()


def test_gworkspace_fetch_normalization():
    """Phase 46: Google Workspace fetch normalization maps login failure to HIGH."""
    from app.services.connector_service import _normalize_gworkspace_event

    event = {
        "id": {"time": "2024-01-01T00:00:00Z", "uniqueQualifier": "123"},
        "actor": {"email": "attacker@example.com"},
        "events": [{"name": "login_failure", "parameters": [{"name": "login_type", "value": "password"}]}],
        "ipAddress": "1.2.3.4",
    }
    normalized = _normalize_gworkspace_event(event)
    assert normalized["severity"] == "HIGH"
    assert "login_failure" in normalized["message"]
    assert normalized["source_ip"] == "1.2.3.4"


def test_azuread_fetch_normalization():
    """Phase 46: AzureAD sign-in failure -> HIGH."""
    from app.services.connector_service import _normalize_azuread_event

    event = {
        "id": "abc-123",
        "userPrincipalName": "user@contoso.com",
        "ipAddress": "5.6.7.8",
        "status": {"errorCode": 50126, "failureReason": "Invalid username or password"},
        "conditionalAccessStatus": "failure",
        "riskLevelDuringSignIn": "high",
        "createdDateTime": "2024-01-01T00:00:00Z",
    }
    normalized = _normalize_azuread_event(event)
    assert normalized["severity"] == "HIGH"
    # Message contains failed or failure or error code
    msg_lower = normalized["message"].lower()
    assert ("failed" in msg_lower) or ("failure" in msg_lower) or ("50126" in msg_lower)


def test_api_key_create_verify_revoke(client, auth_headers, db_session):
    """Phase 47: API keys create, verify, list, revoke."""
    org = _get_org_from_auth(db_session)
    assert org is not None

    # Create via service
    rec, raw = apikey_service.create_api_key(
        db_session, org_id=org.id, name="test-key", scopes="alerts:read,alerts:write", created_by_user_id=1
    )
    assert raw.startswith("sk_")
    assert rec.prefix in raw
    assert rec.last4 in raw

    # Verify
    verified = apikey_service.verify_api_key(db_session, raw)
    assert verified is not None
    assert verified.id == rec.id

    # List via API
    r = client.get("/api/v1/apikeys", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert any(k["prefix"] == rec.prefix for k in data)

    # Use API key to auth (X-API-Key header)
    r2 = client.get("/api/v1/apikeys/rate-limit/status", headers={"X-API-Key": raw})
    assert r2.status_code == 200, r2.text
    assert r2.json()["org_id"] == org.id

    # Revoke
    r3 = client.delete(f"/api/v1/apikeys/{rec.id}", headers=auth_headers)
    assert r3.status_code == 200

    # Verify after revoke should fail
    verified2 = apikey_service.verify_api_key(db_session, raw)
    assert verified2 is None


def test_service_account_create_revoke(client, auth_headers, db_session):
    """Phase 47: service accounts."""
    org = _get_org_from_auth(db_session)
    assert org is not None

    sa, user = apikey_service.create_service_account(
        db_session, org_id=org.id, name="bot-test", description="test bot", role="service"
    )
    assert sa.name == "bot-test"
    assert user.is_service_account is True

    # Create API key for service account
    rec, raw = apikey_service.create_api_key(
        db_session, org_id=org.id, name="sa-key", scopes="alerts:read", service_account_id=sa.id
    )
    assert rec.service_account_id == sa.id

    # List service accounts via API
    r = client.get("/api/v1/apikeys/service-accounts", headers=auth_headers)
    assert r.status_code == 200
    assert any(s["id"] == sa.id for s in r.json())

    # Revoke SA should revoke its keys
    r2 = client.delete(f"/api/v1/apikeys/service-accounts/{sa.id}", headers=auth_headers)
    assert r2.status_code == 200

    # Key should now be invalid
    assert apikey_service.verify_api_key(db_session, raw) is None


def test_org_rate_limiting(client, auth_headers, db_session):
    """Phase 47: per-org rate limiting (in-memory fallback)."""
    from app.core.config import settings

    # Temporarily set low limits
    orig_rps = settings.ORG_RATE_LIMIT_RPS
    orig_burst = settings.ORG_RATE_LIMIT_BURST
    orig_enabled = settings.ORG_RATE_LIMIT_ENABLED

    try:
        settings.ORG_RATE_LIMIT_ENABLED = True
        settings.ORG_RATE_LIMIT_RPS = 2
        settings.ORG_RATE_LIMIT_BURST = 2

        # Clear in-memory buckets
        apikey_service._org_buckets.clear()

        org = _get_org_from_auth(db_session)
        assert org is not None
        rec, raw = apikey_service.create_api_key(
            db_session, org_id=org.id, name="rate-limit-test", scopes="alerts:read"
        )

        # First 2 requests should pass
        for _ in range(2):
            r = client.get("/api/v1/apikeys/rate-limit/status", headers={"X-API-Key": raw})
            assert r.status_code == 200, r.text

        # Third should be rate limited (429)
        r3 = client.get("/api/v1/apikeys/rate-limit/status", headers={"X-API-Key": raw})
        assert r3.status_code == 429, f"expected 429 got {r3.status_code} {r3.text}"

        # Cleanup key
        apikey_service.revoke_api_key(db_session, org_id=org.id, key_id=rec.id)

    finally:
        settings.ORG_RATE_LIMIT_RPS = orig_rps
        settings.ORG_RATE_LIMIT_BURST = orig_burst
        settings.ORG_RATE_LIMIT_ENABLED = orig_enabled
        apikey_service._org_buckets.clear()


def test_org_isolation_api_keys(client, db_session):
    """Phase 47: org isolation — keys from one org cannot be revoked by another org."""
    from app.models import Org
    import pytest

    # Ensure we have two distinct orgs
    org1 = Org(name="Acme Inc", slug="acme-isolation")
    db_session.add(org1)
    db_session.commit()
    db_session.refresh(org1)

    org2 = Org(name="Other Org", slug="other-org")
    db_session.add(org2)
    db_session.commit()
    db_session.refresh(org2)

    assert org1.id != org2.id

    rec, raw = apikey_service.create_api_key(
        db_session, org_id=org1.id, name="isolation-test", scopes="alerts:read"
    )

    # Try to revoke key from other org via service layer — should raise ValueError (not found)
    with pytest.raises(ValueError, match="not found"):
        apikey_service.revoke_api_key(db_session, org_id=org2.id, key_id=rec.id)

    # Correct org should succeed
    apikey_service.revoke_api_key(db_session, org_id=org1.id, key_id=rec.id)

    # Cleanup
    db_session.delete(org2)
    db_session.commit()


def test_evidence_bundle_pdf_generation(client, auth_headers, admin_headers, db_session):
    """Phase 48: evidence bundle PDF rendering."""
    from app.services import case_service
    from app.models import Org

    org = _get_org_from_auth(db_session)
    assert org is not None

    # Create a case via service (payload dict)
    case = case_service.create_case(
        db_session,
        payload={
            "title": "Test Case for Evidence PDF",
            "description": "Test case",
            "severity": "HIGH",
            "priority": "high",
            "status": "open",
        },
        actor="tester",
        org_id=org.id,
    )

    # Get chain-of-custody
    r = client.get(f"/api/v1/compliance/cases/{case.id}/chain-of-custody", headers=auth_headers)
    assert r.status_code == 200, r.text
    chain = r.json()
    assert "chain" in chain
    assert "last_hash" in chain

    # Get evidence bundle JSON
    r2 = client.get(f"/api/v1/compliance/cases/{case.id}/evidence-bundle", headers=auth_headers)
    assert r2.status_code == 200, r2.text
    assert "chain_of_custody" in r2.json()

    # Get evidence bundle PDF
    r3 = client.get(
        f"/api/v1/compliance/cases/{case.id}/evidence-bundle/pdf", headers=auth_headers
    )
    assert r3.status_code == 200, r3.text
    assert r3.headers["content-type"] == "application/pdf"
    assert r3.content.startswith(b"%PDF")
    # Check headers for chain hash
    assert "X-Chain-Last-Hash" in r3.headers
    assert "X-Audit-Chain-Valid" in r3.headers

    # PDF should contain case title (uncompressed)
    assert b"Test Case for Evidence PDF" in r3.content or b"Evidence Bundle" in r3.content

    # Test SOC2 PDF (requires ADMIN)
    r4 = client.get("/api/v1/compliance/audit/evidence/pdf?days=30", headers=admin_headers)
    assert r4.status_code == 200
    assert r4.content.startswith(b"%PDF")
    assert b"SOC2" in r4.content or b"Evidence" in r4.content


def test_audit_verify_endpoint(client, admin_headers):
    """Phase 48: audit verify returns chain_valid."""
    r = client.get("/api/v1/compliance/audit/verify?limit=100", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert "chain_valid" in data
    assert "total_checked" in data
    assert "last_hash" in data
