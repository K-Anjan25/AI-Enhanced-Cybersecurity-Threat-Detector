"""Multi-tenancy tests: orgs table, org_id backfill, and registration scoping."""

from app.models import Org, User, SecurityAlert, Base
from app.core.migrations import ensure_default_org


def test_register_assigns_default_org(client, db_session):
    """New users land in the seeded default org (multi-tenancy v3)."""
    client.post(
        "/api/v1/register",
        json={"username": "orguser", "email": "orguser@example.com", "password": "secret123", "role": "USER"},
    )
    user = db_session.query(User).filter(User.username == "orguser").first()
    assert user.org_id is not None
    org = db_session.query(Org).filter(Org.id == user.org_id).first()
    assert org.slug == "default"


def test_ensure_default_org_seeds_and_backfills(client, db_session):
    """ensure_default_org creates the default org and backfills orphaned rows."""
    # Pre-create an alert with no org to simulate pre-migration data.
    db_session.add(SecurityAlert(alert_type="log", severity="HIGH", score=0.8, message="pre-migration"))
    db_session.commit()

    Base.metadata.create_all(bind=db_session.bind)  # ensure orgs table exists
    ensure_default_org(db_session.bind)

    org = db_session.query(Org).filter(Org.slug == "default").first()
    assert org is not None
    # Backfilled (refresh the cached instance so we see the UPDATE).
    db_session.expire_all()
    alert = db_session.query(SecurityAlert).filter(SecurityAlert.message == "pre-migration").first()
    assert alert.org_id == org.id