"""Endpoints must distinguish "nothing here" from "this broke".

Every endpoint used to wrap its body in a blanket `except Exception` that
returned either `[]` or `{"status": "error"}` with HTTP 200. Both are lies:

  * `return []` renders in the UI as a perfectly normal empty state, so a
    database outage looked exactly like "you have no assets yet".
  * `{"status": "error"}` at HTTP 200 is worse — axios resolves the promise,
    the page's `catch` never runs, and the operator sees a success toast for a
    write that never happened.

These tests pin the corrected contract: failures surface as 5xx, deliberate
HTTPExceptions keep their own status, and success is unchanged.
"""

from unittest.mock import patch

import pytest

from app.services import (
    attack_coverage_service,
    data_lifecycle_service,
    risk_based_service,
)


# ---------------------------------------------------------------------------
# Reads must not disguise a failure as an empty collection
# ---------------------------------------------------------------------------

def test_failing_read_is_a_500_not_an_empty_list(client, admin_headers):
    with patch.object(risk_based_service, "list_assets", side_effect=RuntimeError("db down")):
        r = client.get("/api/v1/risk-based/assets", headers=admin_headers)

    assert r.status_code == 500, "a broken read must not look like an empty inventory"
    assert r.json() != []


def test_successful_read_still_returns_an_empty_list(client, admin_headers):
    """The honest empty case must keep working — that is the whole point."""
    r = client.get("/api/v1/risk-based/assets", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_failing_coverage_read_is_a_500(client, admin_headers):
    with patch.object(
        attack_coverage_service, "list_coverage", side_effect=RuntimeError("boom")
    ):
        r = client.get("/api/v1/attack-coverage/", headers=admin_headers)
    assert r.status_code == 500


def test_failing_policy_read_propagates_rather_than_returning_empty(client, admin_headers):
    """This endpoint has no catch-all, so the error reaches FastAPI.

    That is the correct behaviour and worth pinning: the failure must not be
    quietly converted into an empty policy list, which the retention page would
    render as "no policies configured".
    """
    with patch.object(
        data_lifecycle_service, "list_policies", side_effect=RuntimeError("boom")
    ):
        with pytest.raises(RuntimeError):
            client.get("/api/v1/data-lifecycle/policies", headers=admin_headers)


# ---------------------------------------------------------------------------
# Writes must not report success for work that did not happen
# ---------------------------------------------------------------------------

def test_failing_write_is_not_a_200_with_an_error_body(client, admin_headers):
    with patch.object(risk_based_service, "create_asset", side_effect=RuntimeError("db down")):
        r = client.post(
            "/api/v1/risk-based/assets",
            headers=admin_headers,
            json={"name": "Server", "criticality": 3},
        )

    assert r.status_code == 500, (
        "a failed write returning HTTP 200 makes the dashboard show a success toast"
    )
    body = r.json()
    assert body.get("status") != "error", "the error must be in the status code, not the body"


def test_successful_write_is_unchanged(client, admin_headers):
    r = client.post(
        "/api/v1/risk-based/assets",
        headers=admin_headers,
        json={"name": "Primary file server", "criticality": 4, "hostname": "fs01"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Primary file server"


# ---------------------------------------------------------------------------
# A deliberate HTTPException must survive the blanket handler
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    ["/api/v1/risk-based/assets", "/api/v1/data-lifecycle/policies"],
)
def test_auth_errors_are_not_swallowed_into_success(client, path):
    """Without credentials these must 401 — never 200 with an empty list."""
    r = client.get(path)
    assert r.status_code in (401, 403)
    assert r.json() != []


def test_http_exception_keeps_its_own_status_code(client, admin_headers):
    """`except HTTPException: raise` must run before the catch-all."""
    from fastapi import HTTPException

    with patch.object(
        risk_based_service,
        "list_assets",
        side_effect=HTTPException(status_code=404, detail="no such org"),
    ):
        r = client.get("/api/v1/risk-based/assets", headers=admin_headers)

    assert r.status_code == 404, "a deliberate 404 must not be rewritten as a 500"
    assert r.json()["detail"] == "no such org"
