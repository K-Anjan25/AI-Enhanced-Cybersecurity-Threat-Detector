"""SCIM Groups + Bulk API tests — Phase 41."""

from app.models import Org
from app.services import scim_service


def test_scim_groups_crud_api(client, db_session):
    org = Org(name="Acme Inc", slug="acme")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)

    row, raw = scim_service.create_scim_token(db_session, org_id=org.id, name="Test")
    headers = {"Authorization": f"Bearer {raw}"}

    # Create user for membership
    user_payload = {"userName": "member1", "emails": [{"value": "member1@acme.com"}]}
    r = client.post("/api/v1/scim/v2/Users", json=user_payload, headers=headers)
    assert r.status_code == 201
    user_id = r.json()["id"]

    # Create group
    group_payload = {"displayName": "Sec Team", "members": [{"value": user_id}]}
    r = client.post("/api/v1/scim/v2/Groups", json=group_payload, headers=headers)
    assert r.status_code == 201, r.text
    group_id = r.json()["id"]
    assert len(r.json()["members"]) == 1

    # List groups
    r = client.get("/api/v1/scim/v2/Groups", headers=headers)
    assert r.status_code == 200
    assert r.json()["totalResults"] >= 1

    # Get group
    r = client.get(f"/api/v1/scim/v2/Groups/{group_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["displayName"] == "Sec Team"

    # PATCH add member — create second user
    user2_payload = {"userName": "member2", "emails": [{"value": "member2@acme.com"}]}
    r = client.post("/api/v1/scim/v2/Users", json=user2_payload, headers=headers)
    user2_id = r.json()["id"]

    r = client.patch(
        f"/api/v1/scim/v2/Groups/{group_id}",
        json={"Operations": [{"op": "add", "path": "members", "value": [{"value": user2_id}]}]},
        headers=headers,
    )
    assert r.status_code == 200
    assert len(r.json()["members"]) == 2

    # DELETE group
    r = client.delete(f"/api/v1/scim/v2/Groups/{group_id}", headers=headers)
    assert r.status_code == 204


def test_scim_bulk_api(client, db_session):
    org = Org(name="Acme Inc", slug="acme")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)

    row, raw = scim_service.create_scim_token(db_session, org_id=org.id, name="Test")
    headers = {"Authorization": f"Bearer {raw}"}

    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkRequest"],
        "Operations": [
            {
                "method": "POST",
                "path": "/Users",
                "bulkId": "u1",
                "data": {"userName": "bulkapi1", "emails": [{"value": "bulkapi1@acme.com"}]},
            },
            {
                "method": "POST",
                "path": "/Groups",
                "bulkId": "g1",
                "data": {"displayName": "Bulk Group"},
            },
        ],
    }

    r = client.post("/api/v1/scim/v2/Bulk", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["Operations"]) == 2
    assert r.json()["Operations"][0]["status"]["code"] == "201"


def test_saml_login_endpoints(client):
    # Config endpoint should include saml key if enabled? Currently disabled
    r = client.get("/api/v1/auth/sso/config")
    assert r.status_code == 200

    # SAML login without config should 404
    r = client.get("/api/v1/auth/sso/saml/login", follow_redirects=False)
    assert r.status_code in (302, 404)  # 404 if not configured, 302 if env configured


def test_connector_oauth_status_api(client, db_session):
    # Need auth — use client with no auth should 401? Actually get_current_user required
    # Let's use the test client fixture that has auth? Check conftest
    r = client.get("/api/v1/connectors/github/oauth/status")
    # Without auth, should be 401
    assert r.status_code == 401
