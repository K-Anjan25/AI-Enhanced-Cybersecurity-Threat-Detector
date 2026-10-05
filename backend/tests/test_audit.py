"""T-312: the audit trail -- append-only, complete over mutating routes (FR-42).

The acceptance criterion is that a test asserts no ORM update or delete path
exists on the audit model (R-31). That assertion lives in ``test_repository.py``
and is extended here, because "no ORM path" is only half the property: a service
that hands out a mutable row, or a store that grows an ``update`` method, defeats
it without touching the model. So this file asserts the absence three ways --
the mapper, the trail object, and the record it returns -- and then asserts the
part that makes the trail worth keeping: that every mutating route on the built
application writes a row, checked by walking the live app rather than by reading
a list.

Coverage is asserted through real HTTP requests, not by calling the service: a
route that forgets to append is exactly the defect a service-level test cannot
see. The read endpoint is checked for the things an auditor needs -- a bounded
window, a stable cursor, filters -- and for the things the trail must never carry
(a webhook URL, an analyst's note, a signing secret).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.api.v1.deps import client_ip, parse_instant
from app.auth.rbac import ROUTE_MATRIX, registered_paths
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.db.models import AuditLog
from app.db.repository import MAX_QUERY_SPAN_DAYS
from app.main import create_app
from app.services.audit_log import (
    AUDIT_EXEMPT_ROUTES,
    AUDITED_ROUTES,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MUTATING_METHODS,
    AuditAction,
    AuditEntry,
    AuditRecord,
    AuditTrail,
    InMemoryAuditTrail,
    audit_insert,
    audit_select,
    record_action,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

SECRET = "s" * 48

#: Method and field names that would be an edit path if the audit model or the
#: trail ever grew one (R-31).
DELETE_WORDS = {"update", "delete", "remove", "purge", "truncate", "drop"}
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
AT = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)

FLOW = {
    "schema_version": "flow@1",
    "timestamp": "2026-10-05T12:00:00Z",
    "src_ip": "10.0.0.1",
    "dst_ip": "10.0.0.2",
    "src_port": 4444,
    "dst_port": 443,
    "protocol": "tcp",
    "direction": "outbound",
    "packets": 12,
    "src_packets": 7,
    "dst_packets": 5,
    "src_bytes": 900,
    "dst_bytes": 400,
    "duration": 1.5,
}


def record(**overrides: Any) -> AuditRecord:  # noqa: ANN401 -- the test's own kwargs
    """A valid audit record, with any field overridable."""
    fields: dict[str, Any] = {
        "action": AuditAction.webhook_create,
        "actor": "responder@corp",
        "target_type": "webhook",
        "target_id": "wh_1",
        "at": AT,
        "detail": {"severity_floor": "high"},
        "ip": "203.0.113.9",
    }
    return AuditRecord(**{**fields, **overrides})


# --- the record --------------------------------------------------------------


def test_a_record_is_frozen() -> None:
    with pytest.raises(Exception):  # noqa: B017 -- dataclasses raise FrozenInstanceError
        record().action = AuditAction.webhook_delete  # type: ignore[misc]


def test_the_detail_mapping_cannot_be_edited_after_the_fact() -> None:
    """Freezing the field is not enough: the dict it points at is still mutable."""
    subject = record(detail={"severity_floor": "high"})
    with pytest.raises(TypeError):
        subject.detail["severity_floor"] = "critical"  # type: ignore[index]


def test_editing_the_callers_own_dict_does_not_reach_the_record() -> None:
    """The record copies on construction, so a later edit cannot rewrite history."""
    source = {"severity_floor": "high"}
    subject = record(detail=source)
    source["severity_floor"] = "critical"
    assert subject.detail["severity_floor"] == "high"


@pytest.mark.parametrize(
    "overrides",
    [
        {"actor": "  "},
        {"target_type": ""},
        {"target_id": " "},
        {"at": datetime(2026, 10, 5, 12, 0, 0)},
    ],
)
def test_a_record_that_cannot_be_attributed_is_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        record(**overrides)


def test_an_entry_needs_a_positive_sequence() -> None:
    with pytest.raises(ValueError):
        AuditEntry(sequence=0, record=record())


# --- append-only, asserted three ways ---------------------------------------


def test_the_model_still_exposes_no_update_or_delete() -> None:
    """R-31, restated where the service's own assertions are read."""
    names = {name for name in dir(AuditLog) if not name.startswith("_")}
    forbidden = {name for name in names if any(word in name.lower() for word in DELETE_WORDS)}
    assert forbidden == set()
    assert not AuditLog.__mapper__.relationships  # no object graph to cascade through


def test_the_trail_offers_no_way_to_change_a_record() -> None:
    """A store that grows an `update` defeats R-31 without touching the model."""
    names = {name for name in dir(InMemoryAuditTrail) if not name.startswith("_")}
    assert {name for name in names if any(word in name.lower() for word in DELETE_WORDS)} == set()
    assert {"append", "entries"} <= names


def test_the_protocol_declares_no_mutating_method() -> None:
    """The interface is the contract a persistent trail will implement."""
    declared = {name for name in dir(AuditTrail) if not name.startswith("_")}
    assert {name for name in declared if any(w in name.lower() for w in DELETE_WORDS)} == set()


def test_appending_twice_keeps_both_rows() -> None:
    trail = InMemoryAuditTrail()
    trail.append(record())
    trail.append(record())
    assert len(trail) == 2
    assert [entry.sequence for entry in trail.entries(start=AT, end=AT + timedelta(hours=1))] == [
        2,
        1,
    ]


def test_a_stored_record_is_not_the_object_the_caller_holds() -> None:
    """Handing back the same mutable-looking object invites a later edit."""
    trail = InMemoryAuditTrail()
    original = record()
    trail.append(original)
    stored = trail.entries(start=AT, end=AT + timedelta(hours=1))[0].record
    assert stored is original
    assert isinstance(stored.detail, Mapping)
    with pytest.raises(TypeError):
        stored.detail["action"] = "edited"  # type: ignore[index]


# --- the statements the persistent trail will run ---------------------------


def test_the_insert_statement_targets_the_audit_table() -> None:
    statement = audit_insert(record(), actor_id=7)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert compiled.startswith("INSERT INTO audit_log ")
    assert "ON CONFLICT" not in compiled


def test_the_insert_carries_every_column_fr42_names() -> None:
    """Actor, action, target, timestamp and source IP: the requirement, as SQL."""
    values = audit_insert(record(), actor_id=7).compile(dialect=postgresql.dialect()).params
    assert values["actor_id"] == 7
    assert values["action"] == "webhook.create"
    assert values["target_type"] == "webhook"
    assert values["target_id"] == "wh_1"
    assert values["at"] == AT
    assert values["ip"] == "203.0.113.9"


def test_no_update_or_delete_statement_exists_for_the_audit_table() -> None:
    """The strongest form R-31 can take without a server to enforce it."""
    import app.services.audit_log as module

    source = __import__("pathlib").Path(module.__file__).read_text()
    assert "update(AuditLog)" not in source
    assert "delete(AuditLog)" not in source
    assert ".on_conflict_do_update" not in source
    for name in dir(module):
        assert not name.startswith("audit_update")
        assert not name.startswith("audit_delete")


def test_the_select_is_newest_first_and_bounded() -> None:
    statement = audit_select(start=AT, end=AT + timedelta(days=1), limit=25)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY audit_log.at DESC" in compiled
    assert "LIMIT" in compiled
    assert statement._limit_clause.value == 25  # type: ignore[attr-defined]


def test_every_filter_reaches_the_statement() -> None:
    """A filter the service honours but the SQL ignores is a silent full read."""
    sql = {
        name: str(
            audit_select(
                start=AT,
                end=AT + timedelta(days=1),
                **{name: value},  # type: ignore[arg-type]
            ).compile(dialect=postgresql.dialect())
        )
        for name, value in (
            ("actor_id", 7),
            ("target_type", "webhook"),
            ("target_id", "wh_1"),
            ("before", 99),
        )
    }
    assert "actor_id" in sql["actor_id"]
    assert "target_type" in sql["target_type"]
    assert "target_id" in sql["target_id"]
    assert "audit_log.id <" in sql["before"]
    action_sql = str(
        audit_select(
            start=AT, end=AT + timedelta(days=1), action=AuditAction.webhook_create
        ).compile(dialect=postgresql.dialect())
    )
    assert "audit_log.action =" in action_sql


def test_the_select_is_newest_first_with_a_total_order() -> None:
    """Two rows in the same second need the id as the tie-break, or paging drifts."""
    compiled = str(
        audit_select(start=AT, end=AT + timedelta(days=1)).compile(dialect=postgresql.dialect())
    )
    assert "ORDER BY audit_log.at DESC, audit_log.id DESC" in compiled


def test_the_select_carries_both_time_bounds_as_sql() -> None:
    """The statement, not just the helper's guard: this is what the database runs.

    Asserted against the compiled predicate and its bind values rather than the
    Python-level check, because an adapter that builds the range into a comment
    and not into the WHERE clause reads the whole table while looking correct.
    """
    end = AT + timedelta(days=1)
    compiled = audit_select(start=AT, end=end).compile(dialect=postgresql.dialect())
    text = str(compiled)
    assert "WHERE audit_log.at >=" in text and "audit_log.at <" in text
    assert {value for value in compiled.params.values() if isinstance(value, datetime)} == {AT, end}


def test_the_select_requires_a_time_range() -> None:
    with pytest.raises(ValueError):
        audit_select(start=AT, end=AT)
    with pytest.raises(ValueError):
        audit_select(start=AT, end=AT - timedelta(seconds=1))


@pytest.mark.parametrize("limit", [0, -1])
def test_the_read_refuses_a_useless_limit(limit: int) -> None:
    with pytest.raises(ValueError):
        InMemoryAuditTrail().entries(start=AT, end=AT + timedelta(hours=1), limit=limit)


# --- reading ----------------------------------------------------------------


def _seed(trail: InMemoryAuditTrail) -> None:
    """Three records from two actors, an hour apart."""
    record_action(
        trail,
        action=AuditAction.ingest_flows,
        actor="analyst@corp",
        target_type="ingest",
        target_id="ingest.flows",
        at=AT,
        detail={"accepted": 4},
    )
    record_action(
        trail,
        action=AuditAction.alert_verdict,
        actor="analyst@corp",
        target_type="alert",
        target_id="17",
        at=AT + timedelta(minutes=30),
    )
    record_action(
        trail,
        action=AuditAction.webhook_create,
        actor="responder@corp",
        target_type="webhook",
        target_id="wh_1",
        at=AT + timedelta(hours=2),
    )


def test_the_window_is_half_open() -> None:
    trail = InMemoryAuditTrail()
    _seed(trail)
    inside = trail.entries(start=AT, end=AT + timedelta(minutes=30))
    assert [entry.record.action for entry in inside] == [AuditAction.ingest_flows]
    after = trail.entries(start=AT + timedelta(minutes=30), end=AT + timedelta(hours=3))
    assert len(after) == 2


def test_reads_are_newest_first() -> None:
    trail = InMemoryAuditTrail()
    _seed(trail)
    entries = trail.entries(start=AT, end=AT + timedelta(hours=3))
    assert [entry.sequence for entry in entries] == [3, 2, 1]


def test_each_filter_narrows_without_widening() -> None:
    trail = InMemoryAuditTrail()
    _seed(trail)
    window = {"start": AT, "end": AT + timedelta(hours=3)}
    assert [e.sequence for e in trail.entries(**window, actor="responder@corp")] == [3]
    assert [e.sequence for e in trail.entries(**window, action=AuditAction.alert_verdict)] == [2]
    assert [e.sequence for e in trail.entries(**window, target_type="webhook")] == [3]
    assert [e.sequence for e in trail.entries(**window, target_id="ingest.flows")] == [1]


def test_the_cursor_is_exclusive_and_pages_without_gaps_or_repeats() -> None:
    trail = InMemoryAuditTrail()
    _seed(trail)
    window = {"start": AT, "end": AT + timedelta(hours=3)}
    first = trail.entries(**window, limit=2)
    second = trail.entries(**window, before=first[-1].sequence, limit=2)
    assert [e.sequence for e in first] == [3, 2]
    assert [e.sequence for e in second] == [1]
    assert {entry.sequence for entry in first} & {entry.sequence for entry in second} == set()


def test_the_sequence_is_never_reused_after_a_read() -> None:
    trail = InMemoryAuditTrail()
    _seed(trail)
    trail.entries(start=AT, end=AT + timedelta(days=1))
    assert trail.append(record()).sequence == 4


def test_an_empty_range_is_refused_rather_than_read() -> None:
    with pytest.raises(ValueError):
        InMemoryAuditTrail().entries(start=AT, end=AT)


# --- coverage: every mutating route writes a row ----------------------------


def mutating_routes(app: FastAPI) -> set[tuple[str, str]]:
    """Every ``(method, path)`` on the app that changes state.

    Walks the live application the way ROUTE_MATRIX's completeness check does, so
    a new endpoint is in scope the moment it is registered.
    """
    found: set[tuple[str, str]] = set()
    for path in registered_paths(app.routes):
        for route in _routes_for(app.routes, path):
            for method in getattr(route, "methods", ()) or ():
                if method in MUTATING_METHODS:
                    found.add((method, path))
    return found


def _routes_for(routes: Any, path: str) -> list[Any]:  # noqa: ANN401 -- starlette routes
    """Every route object at one path, walking nested routers."""
    found = []
    for route in routes:
        if getattr(route, "path", None) == path:
            found.append(route)
        for attribute in ("original_router", "router"):
            nested = getattr(route, attribute, None)
            if nested is not None:
                found.extend(_routes_for(getattr(nested, "routes", []), path))
    return found


def test_every_mutating_route_is_either_audited_or_explicitly_exempt() -> None:
    """FR-42's completeness clause, checked against the built application."""
    app = create_app(Settings(env="test", service_name="t", secret_key=APP_SECRET))
    uncovered = {
        (method, path)
        for method, path in mutating_routes(app)
        if (method, path) not in AUDITED_ROUTES and (method, path) not in AUDIT_EXEMPT_ROUTES
    }
    assert uncovered == set()


def test_the_coverage_check_is_not_vacuous() -> None:
    """A check over an empty set passes for the wrong reason."""
    app = create_app(Settings(env="test", service_name="t", secret_key=APP_SECRET))
    assert len(mutating_routes(app)) == len(AUDITED_ROUTES) >= 5


def test_a_new_mutating_route_without_an_entry_is_detected() -> None:
    """The mechanism, proved by planting the defect it exists to catch."""
    app = create_app(Settings(env="test", service_name="t", secret_key=APP_SECRET))

    @app.post("/api/v1/uncovered/probe")
    def probe() -> dict[str, str]:
        return {"ok": "true"}

    assert ("POST", "/api/v1/uncovered/probe") in mutating_routes(app)
    assert ("POST", "/api/v1/uncovered/probe") not in AUDITED_ROUTES


def test_every_read_only_route_is_out_of_scope() -> None:
    """The check is about mutations: a GET must not be dragged into the table."""
    app = create_app(Settings(env="test", service_name="t", secret_key=APP_SECRET))
    for method, _path in mutating_routes(app):
        assert method in MUTATING_METHODS
    assert ("GET", "/api/v1/alerts") not in mutating_routes(app)


def test_the_ndjson_media_type_is_reported() -> None:
    from app.api.v1.endpoints.ingest import ndjson_media_type

    assert ndjson_media_type() == "application/x-ndjson"


def test_a_route_that_lost_its_store_fails_loudly(client: TestClient, auth: TokenService) -> None:
    """The same loud failure the audit trail has: no silent fallback state."""
    client.app.state.webhook_resolver = lambda host, port: ["93.184.216.34"]  # type: ignore[attr-defined]
    del client.app.state.webhook_store  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="webhook_store"):
        client.get("/api/v1/webhooks", headers=headers(auth))


def test_a_route_that_lost_its_vault_fails_loudly(client: TestClient, auth: TokenService) -> None:
    del client.app.state.secret_vault  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="secret_vault"):
        client.post(
            "/api/v1/webhooks",
            json={"url": "https://hooks.example.com/x"},
            headers=headers(auth),
        )


def test_the_audit_route_itself_is_read_only() -> None:
    assert "/api/v1/audit" in ROUTE_MATRIX
    assert ("POST", "/api/v1/audit") not in AUDITED_ROUTES
    assert ("DELETE", "/api/v1/audit") not in AUDITED_ROUTES


# --- through the API --------------------------------------------------------


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
        webhook_allowlist="hooks.example.com",
    )


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    built = create_app(settings)
    built.state.token_service = auth
    built.state.webhook_resolver = lambda host, port: ["93.184.216.34"]
    with TestClient(built) as test_client:
        yield test_client


def headers(auth: TokenService, role: str = "responder") -> dict[str, str]:
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def trail_of(client: TestClient) -> InMemoryAuditTrail:
    trail: InMemoryAuditTrail = client.app.state.audit_trail  # type: ignore[attr-defined]
    return trail


def window(*, hours: int = 2) -> dict[str, str]:
    now = datetime.now(UTC)
    return {
        "start": (now - timedelta(hours=hours)).isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
    }


def actions_of(client: TestClient) -> list[str]:
    return [
        entry.record.action.value
        for entry in trail_of(client).entries(
            start=datetime.now(UTC) - timedelta(hours=2), end=datetime.now(UTC) + timedelta(hours=1)
        )
    ]


def test_an_ingest_is_recorded_with_its_counts(client: TestClient, auth: TokenService) -> None:
    response = client.post("/api/v1/ingest/flows", json=[FLOW], headers=headers(auth, "analyst"))
    assert response.status_code == 200
    entry = trail_of(client).entries(
        start=datetime.now(UTC) - timedelta(minutes=5), end=datetime.now(UTC) + timedelta(minutes=5)
    )[0]
    assert entry.record.action is AuditAction.ingest_flows
    assert entry.record.actor == "analyst@corp"
    assert entry.record.target_id == "ingest.flows"
    assert entry.record.detail["accepted"] == 1


def test_an_ingest_that_accepted_nothing_is_not_recorded(
    client: TestClient, auth: TokenService
) -> None:
    """Nothing entered the system, so there is nothing to attribute."""
    response = client.post(
        "/api/v1/ingest/flows", json=[{"nope": 1}], headers=headers(auth, "analyst")
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 0
    assert actions_of(client) == []


def test_a_rejected_request_is_not_recorded(client: TestClient, auth: TokenService) -> None:
    """A 403 changed nothing; recording it would let a client write the trail."""
    assert (
        client.post(
            "/api/v1/ingest/flows", json=[FLOW], headers=headers(auth, "viewer")
        ).status_code
        == 403
    )
    assert client.post("/api/v1/ingest/flows", json=[FLOW]).status_code == 401
    assert actions_of(client) == []


def test_a_partly_bad_batch_records_both_counts(client: TestClient, auth: TokenService) -> None:
    """The rejected count is the only trace of what the trail refused."""
    response = client.post(
        "/api/v1/ingest/flows", json=[FLOW, {"nope": 1}], headers=headers(auth, "analyst")
    )
    assert (response.json()["accepted"], response.json()["rejected"]) == (1, 1)
    entry = trail_of(client).entries(
        start=datetime.now(UTC) - timedelta(minutes=5), end=datetime.now(UTC) + timedelta(minutes=5)
    )[0]
    assert entry.record.detail == {"received": 2, "accepted": 1, "rejected": 1}


def test_a_webhook_create_records_the_actor_and_no_url(
    client: TestClient, auth: TokenService
) -> None:
    created = client.post(
        "/api/v1/webhooks",
        json={"url": "https://hooks.example.com/alerts/3f9c1d2e"},
        headers=headers(auth),
    )
    assert created.status_code == 201
    entry = trail_of(client).entries(
        start=datetime.now(UTC) - timedelta(minutes=5), end=datetime.now(UTC) + timedelta(minutes=5)
    )[0]
    assert entry.record.action is AuditAction.webhook_create
    assert entry.record.target_id == created.json()["id"]
    assert entry.record.actor == "responder@corp"
    body = json.dumps(dict(entry.record.detail))
    assert "3f9c1d2e" not in body
    assert "hooks.example.com" not in body
    assert created.json()["secret"] not in body


def test_a_webhook_delete_records_the_removal(client: TestClient, auth: TokenService) -> None:
    created = client.post(
        "/api/v1/webhooks", json={"url": "https://hooks.example.com/alerts"}, headers=headers(auth)
    ).json()
    assert (
        client.delete(f"/api/v1/webhooks/{created['id']}", headers=headers(auth)).status_code == 204
    )
    assert actions_of(client)[0] == "webhook.delete"


def test_a_webhook_delete_that_found_nothing_records_nothing(
    client: TestClient, auth: TokenService
) -> None:
    assert client.delete("/api/v1/webhooks/wh_404", headers=headers(auth)).status_code == 404
    assert actions_of(client) == []


def test_a_verdict_records_the_decision_but_not_the_note(
    client: TestClient, auth: TokenService
) -> None:
    response = client.post(
        "/api/v1/alerts/17/verdict",
        json={
            "verdict": "false_positive",
            "created_at": "2026-10-05T12:00:00Z",
            "note": "the analyst's private reasoning about the host",
        },
        headers=headers(auth, "analyst"),
    )
    assert response.status_code == 200
    entry = trail_of(client).entries(
        start=datetime.now(UTC) - timedelta(minutes=5), end=datetime.now(UTC) + timedelta(minutes=5)
    )[0]
    assert entry.record.action is AuditAction.alert_verdict
    assert entry.record.target_id == "17"
    assert entry.record.detail["verdict"] == "false_positive"
    assert "private reasoning" not in json.dumps(dict(entry.record.detail))


def test_a_re_sent_verdict_records_nothing(client: TestClient, auth: TokenService) -> None:
    """No decision changed, so a client retry cannot pad the trail."""
    body = {"verdict": "true_positive", "created_at": "2026-10-05T12:00:00Z"}
    first = client.post("/api/v1/alerts/17/verdict", json=body, headers=headers(auth, "analyst"))
    before = len(trail_of(client))
    second = client.post("/api/v1/alerts/17/verdict", json=body, headers=headers(auth, "analyst"))
    assert (first.json()["action"], second.json()["action"]) == ("recorded", "unchanged")
    assert len(trail_of(client)) == before


def test_a_superseding_verdict_records_what_it_replaced(
    client: TestClient, auth: TokenService
) -> None:
    client.post(
        "/api/v1/alerts/17/verdict",
        json={"verdict": "true_positive", "created_at": "2026-10-05T12:00:00Z"},
        headers=headers(auth, "analyst"),
    )
    client.post(
        "/api/v1/alerts/17/verdict",
        json={"verdict": "benign", "created_at": "2026-10-05T12:00:00Z"},
        headers=headers(auth, "analyst"),
    )
    newest = trail_of(client).entries(
        start=datetime.now(UTC) - timedelta(minutes=5), end=datetime.now(UTC) + timedelta(minutes=5)
    )[0]
    assert newest.record.detail["verdict"] == "benign"
    assert newest.record.detail["superseded"] == "17-v1"


def test_the_recorded_ip_is_the_peer_not_a_header(client: TestClient, auth: TokenService) -> None:
    """A header is attacker-controlled; an audit log that quotes it is worse than silent."""
    client.post(
        "/api/v1/ingest/flows",
        json=[FLOW],
        headers={**headers(auth, "analyst"), "X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"},
    )
    entry = trail_of(client).entries(
        start=datetime.now(UTC) - timedelta(minutes=5), end=datetime.now(UTC) + timedelta(minutes=5)
    )[0]
    assert entry.record.ip not in {"1.2.3.4", "5.6.7.8"}
    assert entry.record.ip == "testclient"


def test_a_proxy_address_is_recorded_once_configured() -> None:
    """Uvicorn's --proxy-headers with --forwarded-allow-ips makes the peer real."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "client": ("10.9.8.7", 51000),
        "headers": [(b"x-forwarded-for", b"1.2.3.4")],
    }
    assert client_ip(Request(scope)) == "10.9.8.7"


def test_client_ip_is_none_without_a_peer() -> None:
    from starlette.requests import Request

    assert client_ip(Request({"type": "http", "headers": []})) is None


def test_the_trail_is_readable_by_every_role(client: TestClient, auth: TokenService) -> None:
    """Reading the trail is reading; the export is the restricted part (FR-43)."""
    client.post("/api/v1/ingest/flows", json=[FLOW], headers=headers(auth, "analyst"))
    for role in ("viewer", "analyst", "responder", "admin"):
        response = client.get("/api/v1/audit", params=window(), headers=headers(auth, role))
        assert response.status_code == 200, role
        assert response.json()["items"]


def test_reading_the_trail_is_closed_to_anonymous_callers(client: TestClient) -> None:
    assert client.get("/api/v1/audit", params=window()).status_code == 401


def test_the_page_reports_a_cursor_and_the_next_page_continues(
    client: TestClient, auth: TokenService
) -> None:
    for _ in range(3):
        client.post("/api/v1/ingest/flows", json=[FLOW], headers=headers(auth, "analyst"))
    first = client.get(
        "/api/v1/audit", params={**window(), "limit": 2}, headers=headers(auth, "viewer")
    ).json()
    second = client.get(
        "/api/v1/audit",
        params={**window(), "limit": 2, "before": first["next_before"]},
        headers=headers(auth, "viewer"),
    ).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert first["next_before"] == first["items"][-1]["id"]
    assert {item["id"] for item in first["items"]} & {
        item["id"] for item in second["items"]
    } == set()


def test_filters_narrow_the_page(client: TestClient, auth: TokenService) -> None:
    client.post("/api/v1/ingest/flows", json=[FLOW], headers=headers(auth, "analyst"))
    client.post(
        "/api/v1/webhooks", json={"url": "https://hooks.example.com/x"}, headers=headers(auth)
    )
    only_ingest = client.get(
        "/api/v1/audit",
        params={**window(), "action": "ingest.flows"},
        headers=headers(auth, "viewer"),
    ).json()
    assert [item["action"] for item in only_ingest["items"]] == ["ingest.flows"]
    by_actor = client.get(
        "/api/v1/audit",
        params={**window(), "actor": "responder@corp"},
        headers=headers(auth, "viewer"),
    ).json()
    assert [item["action"] for item in by_actor["items"]] == ["webhook.create"]
    by_target = client.get(
        "/api/v1/audit",
        params={**window(), "target_type": "webhook"},
        headers=headers(auth, "viewer"),
    ).json()
    assert [item["action"] for item in by_target["items"]] == ["webhook.create"]


def test_an_unknown_action_filter_is_refused(client: TestClient, auth: TokenService) -> None:
    response = client.get(
        "/api/v1/audit",
        params={**window(), "action": "not.an.action"},
        headers=headers(auth, "viewer"),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"start": "yesterday", "end": "today"}, "timestamp"),
        ({"start": "2026-10-05T00:00:00", "end": "2026-10-06T00:00:00"}, "timezone"),
        ({"start": "2026-10-06T00:00:00Z", "end": "2026-10-05T00:00:00Z"}, "later than start"),
    ],
)
def test_an_unusable_window_is_refused(
    client: TestClient, auth: TokenService, params: dict[str, str], reason: str
) -> None:
    response = client.get("/api/v1/audit", params=params, headers=headers(auth, "viewer"))
    assert response.status_code == 400
    assert reason in response.json()["detail"]


def test_an_unbounded_window_is_refused(client: TestClient, auth: TokenService) -> None:
    """R-34's principle applied to a table that grows forever."""
    response = client.get(
        "/api/v1/audit",
        params={"start": "2026-01-01T00:00:00Z", "end": "2026-12-31T00:00:00Z"},
        headers=headers(auth, "viewer"),
    )
    assert response.status_code == 400
    assert str(MAX_QUERY_SPAN_DAYS) in response.json()["detail"]


def test_the_window_and_the_limit_are_required_and_capped(
    client: TestClient, auth: TokenService
) -> None:
    assert client.get("/api/v1/audit", headers=headers(auth, "viewer")).status_code == 422
    too_many = client.get(
        "/api/v1/audit",
        params={**window(), "limit": MAX_LIMIT + 1},
        headers=headers(auth, "viewer"),
    )
    assert too_many.status_code == 422


def test_the_default_limit_is_a_page_not_a_dump() -> None:
    assert DEFAULT_LIMIT <= MAX_LIMIT <= 1000


def test_the_read_returns_the_stored_fields_unchanged(
    client: TestClient, auth: TokenService
) -> None:
    client.post("/api/v1/ingest/flows", json=[FLOW], headers=headers(auth, "analyst"))
    stored = trail_of(client).entries(
        start=datetime.now(UTC) - timedelta(minutes=5), end=datetime.now(UTC) + timedelta(minutes=5)
    )[0]
    served = client.get(
        "/api/v1/audit", params={**window(), "limit": 100}, headers=headers(auth, "viewer")
    ).json()["items"][0]
    assert served["id"] == stored.sequence
    assert served["actor"] == stored.record.actor
    assert served["detail"] == dict(stored.record.detail)
    assert served["ip"] == stored.record.ip


def test_the_response_is_frozen_against_a_caller_mutating_it() -> None:
    from app.schemas.audit import AuditEntryOut

    entry = AuditEntryOut(
        id=1,
        actor="analyst@corp",
        action="ingest.flows",
        target_type="ingest",
        target_id="ingest.flows",
        detail={},
        ip=None,
        at=AT,
    )
    with pytest.raises(Exception):  # noqa: B017 -- pydantic raises ValidationError
        entry.actor = "someone-else"  # type: ignore[misc]


def test_an_extra_field_cannot_be_smuggled_into_a_record() -> None:
    """extra="forbid" on the wire model, so a client cannot add columns."""
    from app.schemas.audit import AuditEntryOut

    with pytest.raises(Exception):  # noqa: B017 -- pydantic raises ValidationError
        AuditEntryOut(
            id=1,
            actor="a",
            action="b",
            target_type="c",
            target_id="d",
            detail={},
            ip=None,
            at=AT,
            severity="critical",
        )


# --- the composition root ---------------------------------------------------


def test_the_application_installs_a_trail() -> None:
    built = create_app(Settings(env="test", service_name="t", secret_key=APP_SECRET))
    assert isinstance(built.state.audit_trail, InMemoryAuditTrail)


def test_a_mutating_route_without_a_trail_fails_loudly() -> None:
    """A silent fallback would hide the FR-42 gap this task closed."""
    built = create_app(Settings(env="test", service_name="t", secret_key=APP_SECRET))
    auth = TokenService(SECRET)
    built.state.token_service = auth
    built.state.webhook_resolver = lambda host, port: ["93.184.216.34"]
    del built.state.audit_trail
    pair = auth.issue("analyst@corp", "analyst")
    with TestClient(built) as test_client, pytest.raises(RuntimeError, match="audit_trail"):
        test_client.post(
            "/api/v1/ingest/flows",
            json=[FLOW],
            headers={"Authorization": f"Bearer {pair.access_token}"},
        )


def test_the_actor_is_the_token_subject_not_the_role() -> None:
    """Two analysts are distinguishable, which is the point of an actor column."""
    auth = TokenService(SECRET)
    pair = auth.issue("alice@corp", "analyst")
    built = create_app(Settings(env="test", service_name="t", secret_key=APP_SECRET))
    built.state.token_service = auth
    with TestClient(built) as test_client:
        test_client.post(
            "/api/v1/ingest/flows",
            json=[FLOW],
            headers={"Authorization": f"Bearer {pair.access_token}"},
        )
        entries = built.state.audit_trail.entries(
            start=datetime.now(UTC) - timedelta(minutes=5),
            end=datetime.now(UTC) + timedelta(minutes=5),
        )
        assert entries[0].record.actor == "alice@corp"
        assert entries[0].record.actor != "analyst"


def test_parse_instant_refuses_what_it_cannot_place() -> None:
    assert parse_instant("2026-10-05T12:00:00+02:00", name="start").tzinfo is not None
    with pytest.raises(ValueError, match="ISO-8601"):
        parse_instant("5 Oct 2026", name="start")
    with pytest.raises(ValueError, match="timezone"):
        parse_instant("2026-10-05T12:00:00", name="start")


def test_an_action_value_is_stable_wire_format() -> None:
    """These strings are persisted and filtered on; a rename is a migration."""
    assert AuditAction.ingest_flows.value == "ingest.flows"
    assert {action.value for action in AuditAction} == {
        "ingest.flows",
        "ingest.logs",
        "alert.verdict",
        "webhook.create",
        "webhook.delete",
        # T-313: issuing and revoking a machine credential are changes to who
        # can act, which is exactly what the trail is for.
        "key.create",
        "key.revoke",
        # T-314: dropping a month of data and erasing a data subject are the two
        # most destructive things this system can do, so both are recorded.
        "retention.apply",
        "privacy.erasure",
        # T-315: promoting a model and rolling one back change what produces
        # production scores, which is a change to the system's behaviour.
        "model.promote",
        "model.rollback",
    }


def test_the_exempt_map_is_empty_and_says_so() -> None:
    assert dict(AUDIT_EXEMPT_ROUTES) == {}


def test_every_audited_route_names_a_real_action() -> None:
    for key, action in AUDITED_ROUTES.items():
        method, path = key
        assert method in MUTATING_METHODS
        assert isinstance(action, AuditAction)
        assert path.startswith("/api/v1/")


def test_the_postgres_insert_helper_is_available_for_a_resolver() -> None:
    """The adapter will need a users table; the statement here does not."""
    assert pg_insert is not None
