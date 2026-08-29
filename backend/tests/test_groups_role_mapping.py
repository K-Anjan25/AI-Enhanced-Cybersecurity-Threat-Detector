"""Phase 43: Groups→Roles mapping + SAML hardening."""

from app.models import Org, User
from app.services import scim_service
from app.services.scim_service import ScimGroup, ScimGroupRoleMapping


def test_group_role_mapping_crud(db_session):
    org = Org(name="TestOrg", slug="testorg")
    db_session.add(org)
    db_session.commit()

    mapping = scim_service.set_group_role_mapping(db_session, org_id=org.id, group_display_name="Security Team", role="ANALYST")
    assert mapping["group_display_name"] == "Security Team"
    assert mapping["role"] == "ANALYST"

    mappings = scim_service.get_group_role_mappings(db_session, org_id=org.id)
    assert len(mappings) == 1

    # Update
    mapping2 = scim_service.set_group_role_mapping(db_session, org_id=org.id, group_display_name="Security Team", role="USER")
    assert mapping2["role"] == "USER"

    # Delete
    result = scim_service.delete_group_role_mapping(db_session, org_id=org.id, mapping_id=mapping["id"])
    assert result["deleted"] == mapping["id"]


def test_group_role_mapping_upgrades_user(db_session):
    org = Org(name="TestOrg2", slug="testorg2")
    db_session.add(org)
    db_session.commit()

    user = User(username="alice", email="alice@example.com", password="hash", role="USER", org_id=org.id, is_active=True)
    db_session.add(user)
    db_session.commit()

    # Create mapping
    scim_service.set_group_role_mapping(db_session, org_id=org.id, group_display_name="Security Team", role="ANALYST")

    # Create group with member
    group = ScimGroup(display_name="Security Team", org_id=org.id, members=[{"value": str(user.id), "display": "alice"}])
    db_session.add(group)
    db_session.commit()

    # Apply mapping on add
    scim_service._apply_group_role_on_add(db_session, org_id=org.id, group_display_name="Security Team", user_id=user.id)

    db_session.refresh(user)
    assert user.role == "ANALYST"


def test_group_role_mapping_never_admin(db_session):
    org = Org(name="TestOrg3", slug="testorg3")
    db_session.add(org)
    db_session.commit()

    try:
        scim_service.set_group_role_mapping(db_session, org_id=org.id, group_display_name="Admins", role="ADMIN")
        assert False, "Should have raised"
    except ValueError as e:
        assert "ADMIN never via SCIM" in str(e) or "must be USER or ANALYST" in str(e)


def test_saml_signature_verification_no_cert():
    # When no cert, verification skipped but logs warning — should not raise when not required
    from app.services import sso_service
    from app.core.config import settings

    # Ensure not requiring signed
    orig = settings.SSO_SAML_REQUIRE_SIGNED_ASSERTIONS
    settings.SSO_SAML_REQUIRE_SIGNED_ASSERTIONS = False
    try:
        # Parsing should work even without xmlsec
        saml_xml = """<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"><saml:Assertion><saml:Subject><saml:NameID>alice@example.com</saml:NameID></saml:Subject><saml:AttributeStatement><saml:Attribute Name="email"><saml:AttributeValue>alice@example.com</saml:AttributeValue></saml:Attribute></saml:AttributeStatement></saml:Assertion></samlp:Response>"""
        import base64

        b64 = base64.b64encode(saml_xml.encode()).decode()
        parsed = sso_service._parse_saml_response(b64)
        assert parsed["email"] == "alice@example.com"
    finally:
        settings.SSO_SAML_REQUIRE_SIGNED_ASSERTIONS = orig
