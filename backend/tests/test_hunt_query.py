"""Hunt queries must answer what was asked, or say they could not.

A hunt returning "no results" is read by an analyst as "nothing to find". That
makes a silently wrong query worse than a failing one: OR was parsed and then
ANDed, so `severity:CRITICAL OR severity:LOW` asked for rows that were both at
once and confidently returned nothing. NOT matched what it was meant to
exclude. Neither raised.
"""

from app.models import SecurityAlert
from app.services import hunt_service

ORG = 1


def _seed(db):
    rows = [
        ("CRITICAL", "okta", "203.0.113.1", "Impossible travel for jo@acme.com"),
        ("LOW", "github", "203.0.113.2", "Dependabot alert on payments-api"),
        ("HIGH", "okta", "203.0.113.3", "Repeated failed logins"),
    ]
    for severity, source, ip, message in rows:
        db.add(SecurityAlert(
            org_id=ORG, severity=severity, source=source,
            source_ip=ip, message=message, alert_type="log",
        ))
    db.commit()


def _count(db, query):
    return hunt_service.execute_hunt_query(db, ORG, query)["result_count"]


# ---------------------------------------------------------------------------
# Boolean logic
# ---------------------------------------------------------------------------

def test_single_condition(db_session):
    _seed(db_session)
    assert _count(db_session, "severity:CRITICAL") == 1


def test_and_narrows(db_session):
    _seed(db_session)
    assert _count(db_session, "severity:CRITICAL AND source:okta") == 1
    assert _count(db_session, "severity:CRITICAL AND source:github") == 0


def test_or_widens(db_session):
    """Previously returned 0: both branches were ANDed into a contradiction."""
    _seed(db_session)
    assert _count(db_session, "severity:CRITICAL OR severity:LOW") == 2


def test_leading_not_excludes(db_session):
    """Previously returned the LOW row — the opposite of what was asked."""
    _seed(db_session)
    assert _count(db_session, "NOT severity:LOW") == 2


def test_not_combines_with_and(db_session):
    _seed(db_session)
    assert _count(db_session, "source:okta AND NOT severity:HIGH") == 1


def test_free_text_searches_the_message(db_session):
    _seed(db_session)
    assert _count(db_session, "Dependabot") == 1


def test_ip_matches_exactly(db_session):
    _seed(db_session)
    assert _count(db_session, "source_ip:203.0.113.1") == 1
    assert _count(db_session, "source_ip:203.0.113.9") == 0


# ---------------------------------------------------------------------------
# Honesty about what it did
# ---------------------------------------------------------------------------

def test_unknown_field_is_reported_not_hidden(db_session):
    """Falling back to a message search is a guess; say so."""
    _seed(db_session)
    result = hunt_service.execute_hunt_query(db_session, ORG, "hostnmae:fs01")
    assert result["unknown_fields"] == ["hostnmae"]


def test_known_fields_produce_no_warning(db_session):
    _seed(db_session)
    result = hunt_service.execute_hunt_query(db_session, ORG, "severity:HIGH")
    assert result["unknown_fields"] == []


def test_a_truncated_result_set_says_so(db_session):
    """"20 results" from a capped query is a different claim from 20 matches."""
    for i in range(30):
        db_session.add(SecurityAlert(
            org_id=ORG, severity="LOW", source="t", message=f"noise {i}"
        ))
    db_session.commit()

    result = hunt_service.execute_hunt_query(db_session, ORG, "noise", limit=10)
    assert result["result_count"] == 10
    assert result["truncated"] is True
    assert result["limit"] == 10


def test_a_complete_result_set_is_not_marked_truncated(db_session):
    _seed(db_session)
    result = hunt_service.execute_hunt_query(db_session, ORG, "severity:CRITICAL", limit=50)
    assert result["truncated"] is False


def test_an_unusable_comparison_is_listed_rather_than_dropped(db_session):
    """`severity:>5` is meaningless; it must not silently become no filter."""
    _seed(db_session)
    result = hunt_service.execute_hunt_query(db_session, ORG, "severity:>5")
    assert result["unsupported"], "an ignored condition must be reported"


def test_results_are_scoped_to_the_tenant(db_session):
    _seed(db_session)
    db_session.add(SecurityAlert(
        org_id=999, severity="CRITICAL", source="other", message="another tenant"
    ))
    db_session.commit()

    assert _count(db_session, "severity:CRITICAL") == 1


def test_an_empty_query_returns_everything_for_the_tenant(db_session):
    _seed(db_session)
    assert _count(db_session, "") == 3


# ---------------------------------------------------------------------------
# Execution is recorded
# ---------------------------------------------------------------------------

def test_running_a_saved_hunt_records_the_execution(db_session):
    _seed(db_session)
    hunt = hunt_service.create_hunt(
        db_session, ORG, "Okta criticals", "severity:CRITICAL AND source:okta"
    )

    execution = hunt_service.execute_and_log_hunt(db_session, ORG, hunt.id)

    assert execution.result_count == 1
    assert execution.id is not None


def test_the_run_history_is_readable(client, admin_headers, db_session):
    _seed(db_session)
    created = client.post(
        "/api/v1/hunts",
        headers=admin_headers,
        json={"name": "Criticals", "query": "severity:CRITICAL"},
    )
    assert created.status_code == 201
    hunt_id = created.json()["id"]

    ran = client.post(f"/api/v1/hunts/{hunt_id}/execute", headers=admin_headers)
    assert ran.status_code == 201

    history = client.get(f"/api/v1/hunts/{hunt_id}/executions", headers=admin_headers)
    assert history.status_code == 200
    assert len(history.json()) >= 1


def test_ad_hoc_execution_does_not_require_saving_first(client, admin_headers, db_session):
    _seed(db_session)
    r = client.post(
        "/api/v1/hunts/execute",
        headers=admin_headers,
        json={"query": "severity:HIGH"},
    )
    assert r.status_code == 200
    assert r.json()["result_count"] == 1
