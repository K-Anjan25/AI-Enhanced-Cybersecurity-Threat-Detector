"""SSO + SCIM — enterprise auth tests."""

import pytest
from unittest.mock import patch, MagicMock

from app.models import Org
from app.models.sso import SsoProvider, ScimToken
from app.services import sso_service, scim_service


@pytest.fixture()
def org(db_session):
    row = Org(name="Acme Inc", slug="acme")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_sso_config_disabled_by_default(db_session):
    cfg = sso_service.get_sso_config(db_session, org_id=None)
    assert cfg["enabled"] is False


def test_sso_config_env_enabled(monkeypatch, db_session):
    monkeypatch.setattr("app.services.sso_service.settings.SSO_ENABLED", True)
    monkeypatch.setattr("app.services.sso_service.settings.SSO_OIDC_ISSUER", "https://accounts.google.com")
    monkeypatch.setattr("app.services.sso_service.settings.SSO_OIDC_CLIENT_ID", "test-client")
    cfg = sso_service.get_sso_config(db_session, org_id=None)
    assert cfg["enabled"] is True
    assert cfg["issuer"] == "https://accounts.google.com"


def test_sso_upsert_provider(db_session, org):
    provider = sso_service.upsert_provider(
        db_session,
        org_id=org.id,
        payload={
            "provider_type": "oidc",
            "display_name": "Test SSO",
            "issuer": "https://example.com",
            "client_id": "cid",
            "client_secret": "secret123",
            "scopes": "openid email",
            "enabled": True,
            "jit_provisioning": True,
        },
        actor="admin",
    )
    assert provider.id is not None
    assert provider.issuer == "https://example.com"
    assert provider.client_secret_encrypted is not None

    cfg = sso_service.get_sso_config(db_session, org_id=org.id)
    assert cfg["enabled"] is True
    assert cfg["issuer"] == "https://example.com"


def test_sso_only_oidc_saml_supported(db_session, org):
    # Phase 41: both oidc and saml supported, invalid type should fail
    with pytest.raises(ValueError, match="must be 'oidc' or 'saml'"):
        sso_service.upsert_provider(
            db_session,
            org_id=org.id,
            payload={
                "provider_type": "invalid",
                "issuer": "https://example.com",
                "client_id": "cid",
            },
            actor="admin",
        )


def test_sso_state_store():
    sso_service.reset_state_store()
    # State store should be empty after reset
    assert len(sso_service._STATE_STORE) == 0


def test_scim_token_create_and_verify(db_session, org):
    row, raw = scim_service.create_scim_token(db_session, org_id=org.id, name="Test Token", created_by="admin")
    assert row.id is not None
    assert raw.startswith("scim_")
    assert row.token_prefix == raw[:8]

    # Verify
    result = scim_service.verify_scim_token(db_session, raw)
    assert result is not None
    token_row, org_id = result
    assert org_id == org.id
    assert token_row.id == row.id

    # Wrong token
    assert scim_service.verify_scim_token(db_session, "wrong-token") is None


def test_scim_list_tokens(db_session, org):
    scim_service.create_scim_token(db_session, org_id=org.id, name="Token 1")
    scim_service.create_scim_token(db_session, org_id=org.id, name="Token 2")
    tokens = scim_service.list_scim_tokens(db_session, org_id=org.id)
    assert len(tokens) >= 2


def test_scim_user_crud(db_session, org):
    # Create
    payload = {
        "userName": "scimuser",
        "emails": [{"value": "scimuser@acme.com"}],
        "externalId": "ext-123",
        "active": True,
    }
    created = scim_service.create_user(db_session, org_id=org.id, payload=payload)
    assert created["userName"] == "scimuser"
    assert created["id"]

    user_id = int(created["id"])

    # List
    listed = scim_service.list_users(db_session, org_id=org.id)
    assert listed["totalResults"] >= 1

    # Filter
    filtered = scim_service.list_users(db_session, org_id=org.id, filter_str='userName eq "scimuser"')
    assert filtered["totalResults"] == 1

    # Get
    fetched = scim_service.get_user(db_session, org_id=org.id, user_id=user_id)
    assert fetched["userName"] == "scimuser"

    # Update
    updated = scim_service.update_user(db_session, org_id=org.id, user_id=user_id, payload={"active": False})
    assert updated["active"] is False

    # Patch
    patched = scim_service.patch_user(db_session, org_id=org.id, user_id=user_id, payload={"Operations": [{"op": "replace", "path": "active", "value": True}]})
    assert patched["active"] is True

    # Delete (soft)
    scim_service.delete_user(db_session, org_id=org.id, user_id=user_id)
    deleted = scim_service.get_user(db_session, org_id=org.id, user_id=user_id)
    assert deleted["active"] is False


def test_scim_discovery(db_session):
    cfg = scim_service.service_provider_config()
    assert "authenticationSchemes" in cfg

    rtypes = scim_service.resource_types()
    assert rtypes["totalResults"] == 2

    schemas = scim_service.schemas()
    assert schemas["totalResults"] == 2

    groups = scim_service.list_groups(db_session, org_id=None)
    assert groups["totalResults"] == 0


def test_connector_catalogue_expanded():
    from app.services.connector_service import CATALOGUE
    assert len(CATALOGUE) == 10
    ids = [c[0] for c in CATALOGUE]
    assert "github" in ids
    assert "slack" in ids
    assert "gworkspace" in ids
    assert "azuread" in ids
    assert "datadog" in ids
    assert "splunk" in ids
