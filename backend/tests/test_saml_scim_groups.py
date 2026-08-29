"""Phase 41: SAML, SCIM Groups + Bulk, Connector OAuth."""

import base64
import pytest

from app.models import Org
from app.models.sso import ScimGroup
from app.services import sso_service, scim_service, connector_oauth_service


@pytest.fixture()
def org(db_session):
    row = Org(name="Acme Inc", slug="acme")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


# SAML

def test_saml_config_disabled_by_default(db_session):
    cfg = sso_service.get_sso_config(db_session, org_id=None)
    # No SAML by default
    assert cfg.get("saml") is None or cfg.get("saml", {}).get("enabled") is not True


def test_saml_upsert_provider(db_session, org):
    provider = sso_service.upsert_provider(
        db_session,
        org_id=org.id,
        payload={
            "provider_type": "saml",
            "display_name": "Test SAML",
            "saml_sso_url": "https://idp.example.com/sso",
            "saml_entity_id": "https://noctra.example.com",
            "enabled": True,
            "jit_provisioning": True,
        },
        actor="admin",
    )
    assert provider.id is not None
    assert provider.provider_type == "saml"
    assert provider.saml_sso_url == "https://idp.example.com/sso"

    cfg = sso_service.get_sso_config(db_session, org_id=org.id)
    assert cfg.get("saml") is not None
    assert cfg["saml"]["enabled"] is True


def test_saml_authn_request_creation(db_session, org):
    sso_service.upsert_provider(
        db_session,
        org_id=org.id,
        payload={
            "provider_type": "saml",
            "display_name": "Test SAML",
            "saml_sso_url": "https://idp.example.com/sso",
            "saml_entity_id": "https://noctra.example.com",
            "enabled": True,
        },
        actor="admin",
    )

    acs_url = "https://noctra.example.com/api/v1/auth/sso/saml/callback"
    redirect_url, relay_state = sso_service.create_saml_authn_request(
        db_session, org_id=org.id, acs_url=acs_url
    )
    assert "https://idp.example.com/sso" in redirect_url
    assert "SAMLRequest" in redirect_url
    assert relay_state

    sso_service.reset_state_store()


def test_saml_response_parsing():
    # Minimal SAMLResponse with email
    saml_xml = """<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
        <saml:Assertion>
            <saml:Subject><saml:NameID>user@example.com</saml:NameID></saml:Subject>
            <saml:AttributeStatement>
                <saml:Attribute Name="email"><saml:AttributeValue>user@example.com</saml:AttributeValue></saml:Attribute>
            </saml:AttributeStatement>
        </saml:Assertion>
    </samlp:Response>"""
    b64 = base64.b64encode(saml_xml.encode()).decode()

    parsed = sso_service._parse_saml_response(b64)
    assert parsed["email"] == "user@example.com"
    assert parsed["sub"] == "user@example.com"


def test_saml_callback_jit(db_session, org):
    sso_service.upsert_provider(
        db_session,
        org_id=org.id,
        payload={
            "provider_type": "saml",
            "display_name": "Test SAML",
            "saml_sso_url": "https://idp.example.com/sso",
            "saml_entity_id": "https://noctra.example.com",
            "enabled": True,
            "jit_provisioning": True,
        },
        actor="admin",
    )

    saml_xml = """<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
        <saml:Assertion>
            <saml:Subject><saml:NameID>samluser@example.com</saml:NameID></saml:Subject>
            <saml:AttributeStatement>
                <saml:Attribute Name="email"><saml:AttributeValue>samluser@example.com</saml:AttributeValue></saml:Attribute>
            </saml:AttributeStatement>
        </saml:Assertion>
    </samlp:Response>"""
    b64 = base64.b64encode(saml_xml.encode()).decode()

    # Create state
    acs_url = "https://noctra.example.com/api/v1/auth/sso/saml/callback"
    _, relay_state = sso_service.create_saml_authn_request(db_session, org_id=org.id, acs_url=acs_url)

    user, access, refresh = sso_service.handle_saml_callback(
        db_session, saml_response=b64, relay_state=relay_state
    )
    assert user.email == "samluser@example.com"
    assert access
    assert refresh

    sso_service.reset_state_store()


# SCIM Groups

def test_scim_group_crud(db_session, org):
    # Create user first
    user_payload = {
        "userName": "groupuser",
        "emails": [{"value": "groupuser@acme.com"}],
        "active": True,
    }
    created_user = scim_service.create_user(db_session, org_id=org.id, payload=user_payload)
    user_id = int(created_user["id"])

    # Create group
    group_payload = {
        "displayName": "Security Team",
        "externalId": "sec-team",
        "members": [{"value": str(user_id)}],
    }
    created_group = scim_service.create_group(db_session, org_id=org.id, payload=group_payload)
    assert created_group["displayName"] == "Security Team"
    assert len(created_group["members"]) == 1

    group_id = int(created_group["id"])

    # List groups
    listed = scim_service.list_groups(db_session, org_id=org.id)
    assert listed["totalResults"] >= 1

    # Filter
    filtered = scim_service.list_groups(db_session, org_id=org.id, filter_str='displayName eq "Security Team"')
    assert filtered["totalResults"] == 1

    # Get group
    fetched = scim_service.get_group(db_session, org_id=org.id, group_id=group_id)
    assert fetched["displayName"] == "Security Team"

    # Patch add member
    # Create another user
    user2_payload = {
        "userName": "groupuser2",
        "emails": [{"value": "groupuser2@acme.com"}],
        "active": True,
    }
    created_user2 = scim_service.create_user(db_session, org_id=org.id, payload=user2_payload)
    user2_id = int(created_user2["id"])

    patched = scim_service.patch_group(
        db_session,
        org_id=org.id,
        group_id=group_id,
        payload={
            "Operations": [
                {"op": "add", "path": "members", "value": [{"value": str(user2_id)}]}
            ]
        },
    )
    assert len(patched["members"]) == 2

    # Patch remove member
    patched2 = scim_service.patch_group(
        db_session,
        org_id=org.id,
        group_id=group_id,
        payload={
            "Operations": [
                {"op": "remove", "path": "members", "value": [{"value": str(user_id)}]}
            ]
        },
    )
    assert len(patched2["members"]) == 1

    # Delete group
    scim_service.delete_group(db_session, org_id=org.id, group_id=group_id)
    with pytest.raises(ValueError):
        scim_service.get_group(db_session, org_id=org.id, group_id=group_id)


# SCIM Bulk

def test_scim_bulk_users(db_session, org):
    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkRequest"],
        "failOnErrors": 1,
        "Operations": [
            {
                "method": "POST",
                "path": "/Users",
                "bulkId": "user1",
                "data": {
                    "userName": "bulkuser1",
                    "emails": [{"value": "bulkuser1@acme.com"}],
                    "active": True,
                },
            },
            {
                "method": "POST",
                "path": "/Users",
                "bulkId": "user2",
                "data": {
                    "userName": "bulkuser2",
                    "emails": [{"value": "bulkuser2@acme.com"}],
                    "active": True,
                },
            },
        ],
    }

    result = scim_service.handle_bulk(db_session, org_id=org.id, payload=payload)
    assert "Operations" in result
    assert len(result["Operations"]) == 2
    assert result["Operations"][0]["status"]["code"] == "201"
    assert result["Operations"][1]["status"]["code"] == "201"


def test_scim_bulk_max_ops(db_session, org):
    payload = {
        "Operations": [{"method": "POST", "path": "/Users", "data": {}} for _ in range(21)]
    }
    with pytest.raises(ValueError, match="max 20"):
        scim_service.handle_bulk(db_session, org_id=org.id, payload=payload)


# Connector OAuth

def test_connector_oauth_status_not_connected(db_session, org):
    status = connector_oauth_service.get_connector_oauth_status(db_session, org_id=org.id, connector_id="github")
    assert status["connected"] is False


def test_connector_oauth_state():
    connector_oauth_service.reset_state_store()
    assert len(connector_oauth_service._STATE_STORE) == 0


def test_connector_oauth_config_missing(db_session, org):
    # Without env config, should fail
    with pytest.raises(ValueError, match="OAuth not configured"):
        connector_oauth_service.create_oauth_authorization_url(
            db_session, org_id=org.id, connector_id="github", redirect_uri="https://example.com/callback"
        )


def test_connector_oauth_disconnect_not_found(db_session, org):
    with pytest.raises(ValueError, match="No OAuth connection"):
        connector_oauth_service.disconnect_oauth(db_session, org_id=org.id, connector_id="github")
