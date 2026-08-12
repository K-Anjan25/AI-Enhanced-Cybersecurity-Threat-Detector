"""Incident/case management service tests."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Case, Org, User
from app.services import case_service


@pytest.fixture
def org(db_session):
    org = Org(name="Acme Corp", slug="acme")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def analyst(db_session, org):
    from app.core.security import get_password_hash

    user = User(
        username="analyst",
        email="analyst@acme.com",
        password=get_password_hash("pw"),
        role="ANALYST",
        org_id=org.id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_create_case_defaults(db_session, org, analyst):
    case = case_service.create_case(
        db_session,
        {"title": "Suspicious login spike"},
        actor=analyst.username,
        org_id=org.id,
    )
    assert case.status == "open"
    assert case.priority == "medium"
    assert case.org_id == org.id
    assert case.title == "Suspicious login spike"


def test_create_case_invalid_status_raises(db_session, org, analyst):
    with pytest.raises(ValueError):
        case_service.create_case(
            db_session,
            {"title": "x", "status": "bogus"},
            actor=analyst.username,
            org_id=org.id,
        )


def test_update_case_status(db_session, org, analyst):
    case = case_service.create_case(
        db_session, {"title": "x"}, actor=analyst.username, org_id=org.id
    )
    updated = case_service.update_case(db_session, case, {"status": "resolved"}, actor=analyst.username)
    assert updated.status == "resolved"
    db_session.refresh(case)
    assert case.status == "resolved"


def test_update_case_invalid_priority_raises(db_session, org, analyst):
    case = case_service.create_case(
        db_session, {"title": "x"}, actor=analyst.username, org_id=org.id
    )
    with pytest.raises(ValueError):
        case_service.update_case(db_session, case, {"priority": "urgent"}, actor=analyst.username)


def test_list_cases_org_scoped(db_session, org, analyst):
    other = Org(name="Other Co", slug="other")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    case_service.create_case(db_session, {"title": "mine"}, actor=analyst.username, org_id=org.id)
    case_service.create_case(db_session, {"title": "theirs"}, actor=analyst.username, org_id=other.id)

    items, total = case_service.list_cases(db_session, org_id=org.id)
    assert total == 1
    assert items[0].title == "mine"


def test_get_case_org_scoped(db_session, org, analyst):
    case = case_service.create_case(
        db_session, {"title": "x"}, actor=analyst.username, org_id=org.id
    )
    assert case_service.get_case(db_session, case.id, org_id=org.id) is case
    assert case_service.get_case(db_session, case.id, org_id=999) is None


def test_serialize_case_shape(db_session, org, analyst):
    case = case_service.create_case(
        db_session, {"title": "x", "description": "d"}, actor=analyst.username, org_id=org.id
    )
    data = case_service.serialize_case(case)
    assert data["status"] == "open"
    assert data["priority"] == "medium"
    assert data["created_at"] is not None
    assert data["source_alert_id"] is None
