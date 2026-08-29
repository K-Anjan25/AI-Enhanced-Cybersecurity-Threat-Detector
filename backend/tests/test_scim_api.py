"""SCIM API endpoints — Bearer token auth + CRUD."""

from app.models import Org
from app.services import scim_service


def test_scim_discovery_endpoints(client):
    # No auth required for discovery per spec
    r = client.get("/api/v1/scim/v2/ServiceProviderConfig")
    assert r.status_code == 200
    assert "authenticationSchemes" in r.json()

    r = client.get("/api/v1/scim/v2/ResourceTypes")
    assert r.status_code == 200
    assert r.json()["totalResults"] == 2

    r = client.get("/api/v1/scim/v2/Schemas")
    assert r.status_code == 200


def test_scim_users_requires_auth(client):
    r = client.get("/api/v1/scim/v2/Users")
    assert r.status_code == 401


def test_scim_users_crud_with_token(client, db_session):
    # Create org and token
    org = Org(name="Acme Inc", slug="acme")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)

    row, raw = scim_service.create_scim_token(db_session, org_id=org.id, name="Test")

    headers = {"Authorization": f"Bearer {raw}"}

    # List empty
    r = client.get("/api/v1/scim/v2/Users", headers=headers)
    assert r.status_code == 200
    assert r.json()["totalResults"] == 0

    # Create user
    payload = {
        "userName": "alice",
        "emails": [{"value": "alice@acme.com"}],
        "active": True,
    }
    r = client.post("/api/v1/scim/v2/Users", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]

    # Get user
    r = client.get(f"/api/v1/scim/v2/Users/{user_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["userName"] == "alice"

    # List with filter
    r = client.get('/api/v1/scim/v2/Users?filter=userName%20eq%20%22alice%22', headers=headers)
    assert r.status_code == 200
    assert r.json()["totalResults"] == 1

    # PATCH active false
    r = client.patch(f"/api/v1/scim/v2/Users/{user_id}", json={"Operations": [{"op": "replace", "path": "active", "value": False}]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["active"] is False

    # DELETE (soft)
    r = client.delete(f"/api/v1/scim/v2/Users/{user_id}", headers=headers)
    assert r.status_code == 204

    # Groups minimal
    r = client.get("/api/v1/scim/v2/Groups", headers=headers)
    assert r.status_code == 200
    assert r.json()["totalResults"] == 0


def test_scim_invalid_token(client):
    r = client.get("/api/v1/scim/v2/Users", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401


def test_sso_config_endpoint(client):
    r = client.get("/api/v1/auth/sso/config")
    assert r.status_code == 200
    assert "enabled" in r.json()
