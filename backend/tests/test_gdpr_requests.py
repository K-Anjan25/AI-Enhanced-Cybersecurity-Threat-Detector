"""Erasure requests: a decision that cannot be undone must not be repeatable."""

import pytest

from app.models.data_lifecycle import GDPRDeletionRequest
from app.services import data_lifecycle_service

ORG = 1


def _request(db, **kw):
    kw.setdefault("target_email", "person@example.com")
    kw.setdefault("status", "pending")
    row = GDPRDeletionRequest(org_id=ORG, **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_unknown_action_is_rejected(db_session):
    """It used to fall through every branch and report success unchanged."""
    req = _request(db_session)
    with pytest.raises(ValueError, match="Unknown action"):
        data_lifecycle_service.process_gdpr_request(db_session, ORG, req.id, action="delete")

    db_session.refresh(req)
    assert req.status == "pending", "a bad action must not change the request"


def test_approve_then_reject_is_refused(db_session):
    """Erasure is irreversible, so the outcome cannot be flipped afterwards."""
    req = _request(db_session)
    data_lifecycle_service.process_gdpr_request(db_session, ORG, req.id, action="approve")

    with pytest.raises(ValueError, match="already approved"):
        data_lifecycle_service.process_gdpr_request(db_session, ORG, req.id, action="reject")


def test_rejected_request_cannot_be_approved_later(db_session):
    req = _request(db_session)
    data_lifecycle_service.process_gdpr_request(db_session, ORG, req.id, action="reject")

    with pytest.raises(ValueError, match="already rejected"):
        data_lifecycle_service.process_gdpr_request(db_session, ORG, req.id, action="approve")


def test_completing_an_approved_request_is_allowed(db_session):
    """approve -> complete is the normal lifecycle, not a re-decision."""
    req = _request(db_session)
    data_lifecycle_service.process_gdpr_request(db_session, ORG, req.id, action="approve")
    done = data_lifecycle_service.process_gdpr_request(db_session, ORG, req.id, action="complete")

    assert done.status == "completed"
    assert done.completed_at is not None


def test_missing_request_is_not_found(db_session):
    with pytest.raises(ValueError, match="not found"):
        data_lifecycle_service.process_gdpr_request(db_session, ORG, 999_999, action="approve")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_queue_exposes_the_reason_for_audit(client, admin_headers):
    created = client.post(
        "/api/v1/data-lifecycle/gdpr",
        headers=admin_headers,
        json={"target_email": "p@example.com", "reason": "Emailed the DPO"},
    )
    assert created.status_code == 200

    rows = client.get("/api/v1/data-lifecycle/gdpr", headers=admin_headers).json()
    assert rows[0]["reason"] == "Emailed the DPO"
    assert "completed_at" in rows[0]


def test_bad_action_is_a_400_not_a_404(client, admin_headers):
    created = client.post(
        "/api/v1/data-lifecycle/gdpr",
        headers=admin_headers,
        json={"target_email": "p@example.com"},
    ).json()

    r = client.post(
        f"/api/v1/data-lifecycle/gdpr/{created['id']}/destroy", headers=admin_headers
    )
    assert r.status_code == 400
    assert "Unknown action" in r.json()["detail"]


def test_unknown_request_is_still_a_404(client, admin_headers):
    r = client.post("/api/v1/data-lifecycle/gdpr/424242/approve", headers=admin_headers)
    assert r.status_code == 404


def test_re_deciding_through_the_api_is_a_400(client, admin_headers):
    created = client.post(
        "/api/v1/data-lifecycle/gdpr",
        headers=admin_headers,
        json={"target_email": "p@example.com"},
    ).json()
    client.post(f"/api/v1/data-lifecycle/gdpr/{created['id']}/approve", headers=admin_headers)

    again = client.post(
        f"/api/v1/data-lifecycle/gdpr/{created['id']}/reject", headers=admin_headers
    )
    assert again.status_code == 400
    assert "cannot be reversed" in again.json()["detail"]
