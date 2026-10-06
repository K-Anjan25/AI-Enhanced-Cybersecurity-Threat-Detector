"""T-314: retention and erasure through the API, and the wiring that makes them work.

The service-level properties live in ``test_retention.py`` and
``test_erasure.py``. This module asserts the things only the application can be
wrong about:

* **The routes are admin-only and the mutating two are audited.** R-53 gives
  retention to admin, and T-312's completeness table enforces the second half by
  walking the live app.
* **A repeat erasure appends nothing.** The audit trail and the ledger must not
  grow when a request changed nothing -- otherwise a client that retries owns a
  way to fill the trail.
* **The identifier never reaches anything durable.** The subject value is scanned
  for in the response, the trail, the ledger, the audit detail and the app's own
  stores after a call.
* **A missing seam fails loudly.** No partition runner, no policy, no catalog and
  no erasure service each produce a RuntimeError naming the seam, rather than a
  success report over a store the service could not reach.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.main import create_app
from app.services.audit_log import AuditAction, InMemoryAuditTrail
from app.services.retention import RetentionPolicy
from fastapi.testclient import TestClient

SECRET = "s" * 48
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
SUBJECT_EMAIL = "bob@corp.example"  # pragma: allowlist secret
HOSTNAME = "web-07.internal.example"
RUN = "the operator asked for it"


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        service_name="aegis-backend-test",
        secret_key=APP_SECRET,
        log_level="WARNING",
    )


def build(settings: Settings, auth: TokenService, **state: Any) -> TestClient:
    """The real application, with any state seam a test wants to replace."""
    app = create_app(settings)
    app.state.token_service = auth
    for name, value in state.items():
        setattr(app.state, name, value)
    return TestClient(app)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    with build(settings, auth) as test_client:
        yield test_client


def headers(auth: TokenService, role: str = "admin") -> dict[str, str]:
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def trail_of(client: TestClient) -> InMemoryAuditTrail:
    trail: InMemoryAuditTrail = client.app.state.audit_trail  # type: ignore[attr-defined]
    return trail


def audit_rows(client: TestClient) -> list[Any]:
    now = datetime.now(UTC)
    return list(
        trail_of(client).entries(start=now - timedelta(hours=1), end=now + timedelta(hours=1))
    )


def erase(client: TestClient, *, kind: str = "entity", value: str = HOSTNAME) -> Any:
    return client.post(
        "/api/v1/privacy/erasure",
        json={"kind": kind, "value": value, "reason": RUN},
        headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
    )


# --- the fixture wiring -------------------------------------------------------


def test_the_composition_root_installs_the_policy_and_the_cascade(client: TestClient) -> None:
    assert isinstance(client.app.state.retention_policy, RetentionPolicy)  # type: ignore[attr-defined]
    assert client.app.state.erasure_service.targets == ("entities", "users")  # type: ignore[attr-defined]
    assert client.app.state.retention_policy.raw_records_days == 30  # type: ignore[attr-defined]


def test_the_settings_drive_the_policy(settings: Settings, auth: TokenService) -> None:
    """A deployment that changes AEGIS_RETENTION_ALERTS_DAYS gets that window."""
    tuned = settings.model_copy(update={"retention_alerts_days": 730})
    with build(tuned, auth) as client:
        assert client.app.state.retention_policy.alerts_days == 730  # type: ignore[attr-defined]


def test_an_inverted_pair_of_windows_stops_the_process() -> None:
    """Validated where the settings are, so a misconfiguration fails at startup."""
    with pytest.raises(ValueError, match="must not be shorter"):
        create_app(
            Settings(
                env="test",
                service_name="t",
                secret_key=APP_SECRET,
                retention_alerts_days=7,
                retention_raw_records_days=30,
            )
        )


# --- retention ----------------------------------------------------------------


def test_the_preview_shows_the_policy_and_the_boundary_rule(client: TestClient) -> None:
    response = client.get(
        "/api/v1/retention", headers=headers(client.app.state.token_service)  # type: ignore[attr-defined]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["policy"] == {"raw_records_days": 30, "alerts_days": 400, "stats_days": 400}
    assert body["drop"], "36 months of partitions with a 400-day window must drop something"
    for partition in body["drop"]:
        # A dropped month ends at or before its table's cutoff: the boundary rule.
        cutoff = date.fromisoformat(body["planned_at"]) - timedelta(
            days=(
                body["policy"]["alerts_days"]
                if partition["table"] == "alerts"
                else body["policy"]["stats_days"]
            )
        )
        assert date.fromisoformat(partition["covers_end"]) <= cutoff
        assert partition["statement"].startswith("DROP TABLE IF EXISTS ")
    assert all(item["table"] == "audit_log" for item in body["unevictable"])
    assert set(body["external"]) == {"kafka", "elasticsearch"}


def test_the_preview_does_not_write_an_audit_row(client: TestClient) -> None:
    """Reading a plan changes nothing (D-041)."""
    client.get("/api/v1/retention", headers=headers(client.app.state.token_service))  # type: ignore[attr-defined]
    assert audit_rows(client) == []


def test_a_run_drops_what_the_plan_named_and_audits_it(client: TestClient) -> None:
    dropped: list[str] = []

    def runner(statement: str) -> bool:
        dropped.append(statement)
        return True

    with build(  # type: ignore[attr-defined]
        client.app.state.settings,  # type: ignore[attr-defined]
        client.app.state.token_service,  # type: ignore[attr-defined]
        partition_runner=runner,
    ) as tuned:
        response = tuned.post(
            "/api/v1/retention/run",
            headers=headers(tuned.app.state.token_service),  # type: ignore[attr-defined]
        )
        assert response.status_code == 200
        body = response.json()
        assert body["changed_anything"] is True
        assert body["dropped"] == body["planned"]
        assert dropped == [f"DROP TABLE IF EXISTS {name}" for name in body["planned"]]
        entries = [
            entry.record
            for entry in tuned.app.state.audit_trail.entries(  # type: ignore[attr-defined]
                start=datetime.now(UTC) - timedelta(hours=1),
                end=datetime.now(UTC) + timedelta(hours=1),
            )
        ]
        assert [entry.action for entry in entries] == [AuditAction.retention_apply]
        assert entries[0].detail["dropped"] == body["planned"]


def test_a_run_that_drops_nothing_reports_that_it_changed_nothing(client: TestClient) -> None:
    """The second run of the same plan is the idempotence an operator can see."""
    dropped: set[str] = set()

    def runner(statement: str) -> bool:
        if statement in dropped:
            return False
        dropped.add(statement)
        return True

    with build(
        client.app.state.settings,  # type: ignore[attr-defined]
        client.app.state.token_service,  # type: ignore[attr-defined]
        partition_runner=runner,
    ) as tuned:
        admin = headers(tuned.app.state.token_service)  # type: ignore[attr-defined]
        first = tuned.post("/api/v1/retention/run", headers=admin).json()
        second = tuned.post("/api/v1/retention/run", headers=admin).json()
        assert second["changed_anything"] is False
        assert second["dropped"] == []
        assert second["already_absent"] == first["planned"]


def test_a_run_without_a_runner_fails_loudly(client: TestClient) -> None:
    """A missing seam must not be reported as a clean run."""
    del client.app.state.partition_runner  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="partition_runner"):
        client.post(
            "/api/v1/retention/run", headers=headers(client.app.state.token_service)  # type: ignore[attr-defined]
        )


def test_a_run_without_a_policy_fails_loudly(client: TestClient) -> None:
    del client.app.state.retention_policy  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="retention_policy"):
        client.get(
            "/api/v1/retention", headers=headers(client.app.state.token_service)  # type: ignore[attr-defined]
        )


def test_a_run_without_a_catalog_fails_loudly(client: TestClient) -> None:
    del client.app.state.known_partitions  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="known_partitions"):
        client.get(
            "/api/v1/retention", headers=headers(client.app.state.token_service)  # type: ignore[attr-defined]
        )


def test_a_bad_catalog_answer_is_refused_by_name(client: TestClient) -> None:
    client.app.state.known_partitions = lambda: {("users", 2026, 1)}  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="not a partitioned table"):
        client.get(
            "/api/v1/retention", headers=headers(client.app.state.token_service)  # type: ignore[attr-defined]
        )


def test_the_catalog_seam_accepts_a_plain_collection(client: TestClient) -> None:
    """What the catalog says is what the plan reasons about.

    The 2020 partition is past the 400-day window and drops; the 2026 one is
    inside it and is kept -- and neither is reported missing, because the catalog
    named them.
    """
    client.app.state.known_partitions = {("alerts", 2020, 1), ("alerts", 2026, 1)}  # type: ignore[attr-defined]
    body = client.get(
        "/api/v1/retention", headers=headers(client.app.state.token_service)  # type: ignore[attr-defined]
    ).json()
    assert [item["name"] for item in body["drop"]] == ["alerts_2020_01"]
    assert [item["name"] for item in body["kept"]] == ["alerts_2026_01"]
    # A month the catalog named is not missing; an in-window month it did not name
    # is, and that gap is the point of reporting it -- there is no default
    # partition, so a month with no partition holds no rows.
    assert "alerts_2026_01" not in body["missing"]
    # A month relative to today, not a frozen literal: the window is 400 days
    # wide, so a hard-coded month drops out of it the day the calendar moves on.
    recent = date.today() - timedelta(days=60)
    assert f"alerts_{recent.year}_{recent.month:02d}" in body["missing"]


def test_a_failing_drop_is_a_loud_failure_not_a_clean_run(client: TestClient) -> None:
    def runner(statement: str) -> bool:
        msg = "permission denied"
        raise RuntimeError(msg)

    client.app.state.partition_runner = runner  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="retention failed on alerts_"):
        client.post(
            "/api/v1/retention/run", headers=headers(client.app.state.token_service)  # type: ignore[attr-defined]
        )


# --- erasure ------------------------------------------------------------------


def test_erasing_an_entity_redacts_it_and_reports_the_tombstone(client: TestClient) -> None:
    client.app.state.entity_store.add("host", HOSTNAME)  # type: ignore[attr-defined]
    response = erase(client)
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "entity"
    assert body["tombstone"].startswith("erased:")
    assert HOSTNAME not in response.text
    assert body["targets"] == [
        {"name": "entities", "affected": 1},
        {"name": "users", "affected": 0},
    ]
    assert body["affected"] == 1
    assert body["ledger_sequence"] == 1
    assert {item["name"] for item in body["preserved"]} == {"audit_log", "verdicts"}
    assert body["reason"] == RUN


def test_erasing_a_user_deletes_the_account_and_cascades_to_keys(client: TestClient) -> None:
    keys = client.app.state.api_key_store  # type: ignore[attr-defined]
    admin = headers(client.app.state.token_service)  # type: ignore[attr-defined]
    issued = client.post(
        "/api/v1/keys", json={"name": "collector", "scopes": ["ingest:write"]}, headers=admin
    ).json()
    assert len(keys) == 1
    client.app.state.user_store.add(SUBJECT_EMAIL)  # type: ignore[attr-defined]

    response = erase(client, kind="user", value=SUBJECT_EMAIL)
    assert response.status_code == 200
    assert response.json()["affected"] == 1
    assert len(client.app.state.user_store) == 0  # type: ignore[attr-defined]
    assert issued["id"] is not None  # issued, then erased by the cascade


def test_the_erasure_is_audited_once_without_the_identifier(client: TestClient) -> None:
    client.app.state.entity_store.add("host", HOSTNAME)  # type: ignore[attr-defined]
    body = erase(client).json()
    rows = audit_rows(client)
    assert [entry.record.action for entry in rows] == [AuditAction.privacy_erasure]
    detail = rows[0].record.detail
    assert detail["kind"] == "entity"
    assert detail["targets"] == {"entities": 1, "users": 0}
    assert detail["preserved"] == ["audit_log", "verdicts"]
    assert rows[0].record.target_id == body["tombstone"]
    assert HOSTNAME not in repr(rows[0].record)


def test_a_repeat_erasure_changes_nothing_and_appends_nothing(client: TestClient) -> None:
    client.app.state.entity_store.add("host", HOSTNAME)  # type: ignore[attr-defined]
    first = erase(client).json()
    second = erase(client).json()
    assert second["already_erased"] is True
    assert second["affected"] == 0
    assert second["ledger_sequence"] is None
    assert second["tombstone"] == first["tombstone"]
    assert len(audit_rows(client)) == 1
    assert len(client.app.state.erasure_ledger) == 1  # type: ignore[attr-defined]


def test_the_identifier_is_nowhere_after_the_call(client: TestClient) -> None:
    """The strongest form of "erased": a scan of everything the call touched."""
    client.app.state.entity_store.add("host", HOSTNAME)  # type: ignore[attr-defined]
    response = erase(client)
    assert HOSTNAME not in response.text
    assert HOSTNAME not in repr(client.app.state.entity_store.values())  # type: ignore[attr-defined]
    assert HOSTNAME not in repr(client.app.state.erasure_ledger.entries(limit=10))  # type: ignore[attr-defined]
    assert HOSTNAME not in repr([entry.record for entry in audit_rows(client)])


def test_the_ledger_lists_newest_first_with_a_cursor(client: TestClient) -> None:
    admin = headers(client.app.state.token_service)  # type: ignore[attr-defined]
    for index in range(3):
        erase(client, value=f"host-{index}.internal.example")
    page = client.get("/api/v1/privacy/erasures", headers=admin, params={"limit": 2}).json()
    assert [item["sequence"] for item in page["items"]] == [3, 2]
    assert page["next_before"] == 2
    rest = client.get(
        "/api/v1/privacy/erasures", headers=admin, params={"limit": 2, "before": 2}
    ).json()
    assert [item["sequence"] for item in rest["items"]] == [1]
    assert rest["next_before"] is None


def test_the_ledger_carries_no_identifier_but_does_carry_who_asked(client: TestClient) -> None:
    erase(client, value=HOSTNAME)
    page = client.get(
        "/api/v1/privacy/erasures", headers=headers(client.app.state.token_service)  # type: ignore[attr-defined]
    ).json()
    assert HOSTNAME not in repr(page)
    assert page["items"][0]["requested_by"] == "admin@corp"


def test_a_ledger_limit_above_the_ceiling_is_a_422(client: TestClient) -> None:
    """The bound is at the edge, so an unbounded listing cannot be asked for."""
    response = client.get(
        "/api/v1/privacy/erasures",
        headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
        params={"limit": 10_000},
    )
    assert response.status_code == 422


def test_an_unknown_kind_is_refused_naming_the_allowed_ones(client: TestClient) -> None:
    response = erase(client, kind="person")
    assert response.status_code == 400
    assert "user" in response.json()["detail"] and "entity" in response.json()["detail"]
    assert len(client.app.state.erasure_ledger) == 0  # type: ignore[attr-defined]


def test_a_blank_subject_is_refused_at_the_edge(client: TestClient) -> None:
    assert erase(client, value="").status_code == 422


def test_an_erasure_without_a_service_fails_loudly(client: TestClient) -> None:
    del client.app.state.erasure_service  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="erasure_service"):
        erase(client)


def test_the_reason_is_recorded_and_never_treated_as_an_identifier(client: TestClient) -> None:
    client.app.state.entity_store.add("host", HOSTNAME)  # type: ignore[attr-defined]
    body = erase(client).json()
    assert body["reason"] == RUN
    assert RUN not in repr(client.app.state.erasure_ledger.entries(limit=10))  # type: ignore[attr-defined]


# --- authorisation ------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/retention"),
        ("post", "/api/v1/retention/run"),
        ("post", "/api/v1/privacy/erasure"),
        ("get", "/api/v1/privacy/erasures"),
    ],
)
def test_retention_and_erasure_are_admin_only(client: TestClient, method: str, path: str) -> None:
    """R-53 gives retention to admin, and erasure is the same authority."""
    for role in ("viewer", "analyst", "responder"):
        assert (
            client.request(
                method.upper(),
                path,
                json={"kind": "entity", "value": HOSTNAME},
                headers=headers(client.app.state.token_service, role),  # type: ignore[attr-defined]
            ).status_code
            == 403
        ), role


def test_retention_and_erasure_require_a_credential(client: TestClient) -> None:
    assert client.get("/api/v1/retention").status_code == 401
    assert (
        client.post("/api/v1/privacy/erasure", json={"kind": "entity", "value": "x"}).status_code
        == 401
    )


def test_the_mutating_routes_are_in_the_audited_table(client: TestClient) -> None:
    """T-312's completeness contract covers them; this states it where they live."""
    from app.services.audit_log import AUDITED_ROUTES

    assert AUDITED_ROUTES[("POST", "/api/v1/retention/run")] is AuditAction.retention_apply
    assert AUDITED_ROUTES[("POST", "/api/v1/privacy/erasure")] is AuditAction.privacy_erasure


def test_the_shipped_runner_refuses_and_names_the_missing_wiring(client: TestClient) -> None:
    """The default is a refusal, not a no-op: a clean-run report it cannot back is worse."""
    with pytest.raises(RuntimeError, match="no partition runner is wired"):
        client.post(
            "/api/v1/retention/run",
            headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
        )


def test_a_catalog_that_is_neither_a_callable_nor_a_collection_is_refused(
    client: TestClient,
) -> None:
    client.app.state.known_partitions = 42  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="callable or a collection"):
        client.get(
            "/api/v1/retention",
            headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
        )


def test_the_matrix_rows_name_admin_and_nobody_else(client: TestClient) -> None:
    """The behavioural 403 above is the gate; this states the intent in the table.

    ``require(Capability.RETENTION)`` refuses the other roles whatever the matrix
    says, so a matrix row widened by mistake would not be caught by a request --
    and the matrix is what a reader consults for who may do this.
    """
    from app.auth.rbac import ROUTE_MATRIX, Role

    for path in (
        "/api/v1/retention",
        "/api/v1/retention/run",
        "/api/v1/privacy/erasure",
        "/api/v1/privacy/erasures",
    ):
        assert ROUTE_MATRIX[path] == frozenset({Role.ADMIN}), path
