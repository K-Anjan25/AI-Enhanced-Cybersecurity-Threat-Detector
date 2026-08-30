"""Approval controls must hold when the API is called directly.

An approval step exists to put a second person between a decision and a
destructive action. If the requester can satisfy it themselves, or one person
can satisfy a two-approval step by deciding twice, the control is decorative.
These tests pin the rules at the service layer, where the UI cannot bypass them.
"""

import pytest

from app.services import approval_workflow_service as svc

ORG = 1
REQUESTER = 42
APPROVER = 7
SECOND_APPROVER = 9


def _dual_workflow(db):
    """The seeded two-step workflow: analyst, then admin."""
    workflows = svc.seed_workflows(db, ORG)
    return next(w for w in workflows if "Dual" in w.name)


def _single_workflow(db):
    workflows = svc.seed_workflows(db, ORG)
    return next(w for w in workflows if "SOC Lead" in w.name)


def _request(db, workflow, requested_by=REQUESTER):
    return svc.request_approval(
        db, ORG, workflow.id, "disable_user", "bob@acme.com",
        requested_by_user_id=requested_by,
    )


# ---------------------------------------------------------------------------
# Separation of duties
# ---------------------------------------------------------------------------

def test_requester_cannot_approve_their_own_request(db_session):
    inst = _request(db_session, _single_workflow(db_session))

    with pytest.raises(ValueError, match="cannot approve it"):
        svc.approve_instance(db_session, ORG, inst.id, approver_user_id=REQUESTER)

    db_session.refresh(inst)
    assert inst.status == "pending", "a refused approval must not change the request"


def test_requester_cannot_reject_their_own_request_either(db_session):
    """Self-rejection is less dangerous but still bypasses the reviewer."""
    inst = _request(db_session, _single_workflow(db_session))

    with pytest.raises(ValueError, match="cannot approve it"):
        svc.approve_instance(
            db_session, ORG, inst.id, approver_user_id=REQUESTER, decision="rejected"
        )


def test_one_person_cannot_satisfy_a_dual_approval_alone(db_session):
    """The bug this suite exists for: two clicks by one person passed review."""
    inst = _request(db_session, _dual_workflow(db_session))

    svc.approve_instance(db_session, ORG, inst.id, approver_user_id=APPROVER)
    db_session.refresh(inst)
    assert inst.current_step == 2, "first approval should advance to step two"

    with pytest.raises(ValueError, match="already decided"):
        svc.approve_instance(db_session, ORG, inst.id, approver_user_id=APPROVER)

    db_session.refresh(inst)
    assert inst.status == "pending", "one approver must not complete a dual workflow"


def test_two_different_people_complete_a_dual_approval(db_session):
    inst = _request(db_session, _dual_workflow(db_session))

    svc.approve_instance(db_session, ORG, inst.id, approver_user_id=APPROVER)
    svc.approve_instance(db_session, ORG, inst.id, approver_user_id=SECOND_APPROVER)

    db_session.refresh(inst)
    assert inst.status == "approved"
    assert inst.decided_at is not None


# ---------------------------------------------------------------------------
# The decision itself
# ---------------------------------------------------------------------------

def test_only_approved_or_rejected_are_accepted(db_session):
    """Any other string used to land in the audit trail as a real decision."""
    inst = _request(db_session, _single_workflow(db_session))

    with pytest.raises(ValueError, match="Unknown decision"):
        svc.approve_instance(
            db_session, ORG, inst.id, approver_user_id=APPROVER, decision="banana"
        )

    db_session.refresh(inst)
    assert inst.approvals_json in ([], None), "nothing should be recorded"


def test_a_rejection_stops_the_request(db_session):
    inst = _request(db_session, _dual_workflow(db_session))

    svc.approve_instance(
        db_session, ORG, inst.id, approver_user_id=APPROVER, decision="rejected"
    )

    db_session.refresh(inst)
    assert inst.status == "rejected"
    assert inst.decided_at is not None


def test_a_settled_request_cannot_be_decided_again(db_session):
    """It used to return the instance unchanged, which reads as success."""
    inst = _request(db_session, _single_workflow(db_session))
    svc.approve_instance(db_session, ORG, inst.id, approver_user_id=APPROVER)

    with pytest.raises(ValueError, match="already approved"):
        svc.approve_instance(
            db_session, ORG, inst.id, approver_user_id=SECOND_APPROVER, decision="rejected"
        )


def test_the_audit_trail_records_who_decided_what(db_session):
    inst = _request(db_session, _dual_workflow(db_session))
    svc.approve_instance(
        db_session, ORG, inst.id, approver_user_id=APPROVER, comment="Checked with the owner"
    )

    db_session.refresh(inst)
    entry = inst.approvals_json[0]
    assert entry["user_id"] == APPROVER
    assert entry["decision"] == "approved"
    assert entry["comment"] == "Checked with the owner"
    assert entry["step"] == 1


# ---------------------------------------------------------------------------
# What the queue shows
# ---------------------------------------------------------------------------

def test_serialized_instance_carries_progress_and_requester(db_session):
    workflow = _dual_workflow(db_session)
    inst = _request(db_session, workflow)

    payload = svc.serialize_instance(inst, workflow)
    assert payload["requested_by_user_id"] == REQUESTER
    assert payload["current_step"] == 1
    assert payload["total_steps"] == 2
    assert payload["workflow_name"] == workflow.name


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_self_approval_through_the_api_is_a_400(client, admin_headers):
    workflows = client.get("/api/v1/approval-workflows/", headers=admin_headers).json()
    created = client.post(
        "/api/v1/approval-workflows/request",
        headers=admin_headers,
        json={
            "workflow_id": workflows[0]["id"],
            "action_type": "block_ip",
            "target": "203.0.113.9",
        },
    ).json()

    # Same account raised it, so the same account must not decide it.
    decided = client.post(
        f"/api/v1/approval-workflows/instances/{created['id']}/decide",
        headers=admin_headers,
        json={"decision": "approved"},
    )
    assert decided.status_code == 400
    assert "cannot approve it" in decided.json()["detail"]


def test_unknown_instance_is_still_a_404(client, admin_headers):
    r = client.post(
        "/api/v1/approval-workflows/instances/424242/decide",
        headers=admin_headers,
        json={"decision": "approved"},
    )
    assert r.status_code == 404


def test_queue_lists_pending_requests(client, admin_headers):
    workflows = client.get("/api/v1/approval-workflows/", headers=admin_headers).json()
    client.post(
        "/api/v1/approval-workflows/request",
        headers=admin_headers,
        json={
            "workflow_id": workflows[0]["id"],
            "action_type": "isolate_host",
            "target": "fs01",
        },
    )

    rows = client.get(
        "/api/v1/approval-workflows/instances?status=pending", headers=admin_headers
    ).json()
    assert len(rows) >= 1
    assert rows[0]["action_type"] == "isolate_host"
    assert rows[0]["total_steps"] is not None
