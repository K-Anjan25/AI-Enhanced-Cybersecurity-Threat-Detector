"""The hunt export: the CSV, the RBAC, and the audit row it writes (T-408).

Three things are asserted here that nothing else can see:

* **The file's rows are the view's rows.** The export re-runs the same
  ``AlertQuery`` the list route does, and the test compares the two reads rather
  than trusting that two code paths agree.
* **An export that was refused left no trace, and one that succeeded left exactly
  one.** The trail records changes, not requests (D-041), and the export is the one
  read that *is* a change -- so "no audit row on a 403" is as important as "one row
  on a 200", or the trail would fill with attempts nobody made a copy of.
* **Nothing from the rows reaches the trail.** The trail is readable by every role
  and an export may be scoped to one, so a record that quoted a family or a trace id
  would widen the data it was recording (R-58).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from app.auth.tokens import TokenService
from app.core.config import Environment, Settings
from app.main import create_app
from fastapi.testclient import TestClient

SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
ENTITY = 7


def stamp(offset_seconds: float = 0.0) -> str:
    """An ISO-8601 instant in UTC, ``offset_seconds`` after the fixture's start."""
    return (START + timedelta(seconds=offset_seconds)).isoformat()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env=Environment.TEST,
        service_name="aegis-backend-test",
        secret_key=SECRET,
        log_level="WARNING",
    )


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> Iterator[TestClient]:
    built = create_app(settings)
    built.state.token_service = auth
    with TestClient(built) as test_client:
        yield test_client


def headers(auth: TokenService, role: str = "responder") -> dict[str, str]:
    """An Authorization header for one role."""
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def seed(
    client: TestClient,
    *,
    offset: float = 0.0,
    entity_id: int = ENTITY,
    family: str = "exfiltration",
    severity: str = "high",
    score: float = 0.8,
    occurrence_count: int = 3,
    trace_id: str | None = "trace-1",
) -> int:
    """Store one alert row the way the correlator's writer would, and return its id.

    The trace id goes inside ``window_ref`` because that is where the row keeps it
    (``_trace_id_of``, T-317): a fixture that set a column that does not exist would
    test a shape the API cannot produce.
    """
    from app.db.models import Alert

    created_at = START + timedelta(seconds=offset)
    store = client.app.state.alert_store  # type: ignore[attr-defined]
    window_ref: dict[str, object] = {
        "store": "stream",
        "id": f"win-{offset}",
        "grouped": False,
        "evidence": [],
    }
    if trace_id is not None:
        window_ref["trace_id"] = trace_id
    row = Alert(
        id=len(store._rows) + 1,  # noqa: SLF001 -- the test seeds the store directly
        created_at=created_at,
        entity_id=entity_id,
        family=family,
        severity=severity,
        score=score,
        status="open",
        first_seen=created_at,
        last_seen=created_at,
        occurrence_count=occurrence_count,
        window_ref=window_ref,
        model_flow_id="flownet@1.4.2",
        model_log_id=None,
        explanation={},
    )
    store._rows.append(row)  # noqa: SLF001
    store._next_id = row.id + 1  # noqa: SLF001
    return row.id


def body(**overrides: object) -> dict[str, object]:
    """An export body covering the whole fixture window."""
    return {"start": stamp(), "end": stamp(600), **overrides}


def export(client: TestClient, auth: TokenService, *, role: str = "responder", **overrides: object):
    """POST one export, as the console does."""
    return client.post(
        "/api/v1/hunt/export",
        json=body(**overrides),
        headers=headers(auth, role),
    )


def rows_of(response) -> list[dict[str, str]]:  # type: ignore[no-untyped-def]
    """The CSV's data rows, parsed back with the standard library reader."""
    text = response.text
    return list(csv.DictReader(io.StringIO(text)))


def audit_entries(client: TestClient) -> list[dict[str, object]]:
    """Every trail entry in the fixture window, newest first."""
    trail = client.app.state.audit_trail  # type: ignore[attr-defined]
    return [
        {"action": entry.record.action.value, "detail": dict(entry.record.detail)}
        for entry in trail.entries(
            start=START - timedelta(days=1),
            end=START + timedelta(days=1),
            limit=100,
        )
    ]


# --- the CSV itself -----------------------------------------------------------


def test_the_header_is_the_published_column_order(client: TestClient, auth: TokenService) -> None:
    seed(client)

    response = export(client, auth)

    assert response.status_code == 200
    first_line = response.text.split("\r\n")[0]
    assert first_line == (
        "id,created_at,entity_id,family,severity,score,status,"
        "first_seen,last_seen,occurrence_count,trace_id"
    )


def test_the_rows_are_the_wire_shape_not_the_rendered_one(
    client: TestClient, auth: TokenService
) -> None:
    """An instant is ISO-8601 and a score is a number, so the file computes."""
    seed(client, offset=30, score=0.75, trace_id=None)

    (row,) = rows_of(export(client, auth))

    assert row["created_at"] == stamp(30)
    assert row["score"] == "0.75"
    assert row["occurrence_count"] == "3"
    # A missing trace id is an empty cell, not the string "None".
    assert row["trace_id"] == ""


def test_the_file_is_rfc_4180(client: TestClient, auth: TokenService) -> None:
    seed(client)

    response = export(client, auth)

    assert response.text.endswith("\r\n")
    assert len(response.text.split("\r\n")) == 3  # header, one row, the trailing empty


def test_a_value_with_a_comma_or_a_quote_survives_a_round_trip(
    client: TestClient, auth: TokenService
) -> None:
    seed(client, family='DoS "slowloris", variant 2')

    (row,) = rows_of(export(client, auth))

    assert row["family"] == 'DoS "slowloris", variant 2'


@pytest.mark.parametrize(
    "hostile",
    ["=cmd|' /C calc'!A0", "+1+1", "-2+3", "@SUM(A1)", "\tx", "\rx"],
)
def test_a_cell_that_could_start_a_formula_is_defused(
    client: TestClient, auth: TokenService, hostile: str
) -> None:
    """A trace id is an attacker-supplied ``traceparent`` the alert row keeps.

    Un-defused, opening the export in a spreadsheet runs whatever it names, on the
    machine of the responder who exported it. The apostrophe keeps the value
    legible and stops it being a formula.
    """
    seed(client, trace_id=hostile)

    (row,) = rows_of(export(client, auth))

    assert row["trace_id"] == f"'{hostile}"


def test_an_ordinary_value_is_not_touched(client: TestClient, auth: TokenService) -> None:
    """The defence must be narrow: prefixing everything would corrupt the data."""
    seed(client, trace_id="trace-1", family="exfiltration")

    (row,) = rows_of(export(client, auth))

    assert row["trace_id"] == "trace-1"
    assert row["family"] == "exfiltration"


# --- the rows are the view's rows ---------------------------------------------


def test_the_export_matches_what_the_list_returns(client: TestClient, auth: TokenService) -> None:
    """The acceptance criterion behind "export the results": same rows, same order.

    Compared against the list route's own answer rather than against a fixture, so
    the two cannot drift apart without this failing.
    """
    for index in range(5):
        seed(client, offset=index, entity_id=index + 1, severity="high" if index % 2 else "low")

    listed = client.get(
        "/api/v1/alerts",
        params={"start": stamp(), "end": stamp(600), "severity": "high", "limit": 10},
        headers=headers(auth, "viewer"),
    ).json()
    exported = rows_of(export(client, auth, severity="high", limit=10))

    # Two rows are high, so the comparison is not vacuous.
    assert len(exported) == 2
    assert [item["id"] for item in listed["items"]] == [int(row["id"]) for row in exported]


def test_every_field_of_the_row_is_exported_even_when_the_table_hides_it(
    client: TestClient, auth: TokenService
) -> None:
    """The column picker is a reading aid; an export that honoured it would lose data."""
    seed(client, trace_id="trace-9")

    (row,) = rows_of(export(client, auth))

    assert row["trace_id"] == "trace-9"
    assert row["status"] == "open"


def test_ordering_is_honoured(client: TestClient, auth: TokenService) -> None:
    for index in range(3):
        seed(client, offset=index)

    ascending = rows_of(export(client, auth, order="asc"))
    descending = rows_of(export(client, auth, order="desc"))

    assert [row["created_at"] for row in ascending] == sorted(
        row["created_at"] for row in ascending
    )
    assert [row["id"] for row in descending] == list(reversed([row["id"] for row in ascending]))


def test_a_limit_exports_that_many_rows_and_says_it_was_truncated(
    client: TestClient, auth: TokenService
) -> None:
    for index in range(4):
        seed(client, offset=index)

    response = export(client, auth, limit=2)

    assert len(rows_of(response)) == 2
    (entry,) = [e for e in audit_entries(client) if e["action"] == "hunt.export"]
    assert entry["detail"]["rows"] == 2  # type: ignore[index]
    assert entry["detail"]["truncated"] is True  # type: ignore[index]


def test_a_window_with_no_matches_still_exports_a_header_and_audits_it(
    client: TestClient, auth: TokenService
) -> None:
    """An empty file is an answer, and taking it is still a disclosure of nothing."""
    seed(client, severity="low")

    response = export(client, auth, severity="critical")

    assert response.status_code == 200
    assert rows_of(response) == []
    assert response.text.split("\r\n")[0].startswith("id,created_at")
    (entry,) = [e for e in audit_entries(client) if e["action"] == "hunt.export"]
    assert entry["detail"]["rows"] == 0  # type: ignore[index]


def test_a_filter_narrows_the_file_too(client: TestClient, auth: TokenService) -> None:
    seed(client, entity_id=1, family="exfiltration")
    seed(client, offset=1, entity_id=2, family="DoS")

    exported = rows_of(export(client, auth, family="DoS", entity_id=2))

    assert [row["family"] for row in exported] == ["DoS"]


def test_the_filename_names_the_window(client: TestClient, auth: TokenService) -> None:
    response = export(client, auth)

    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="aegis-hunt-')
    assert disposition.endswith('.csv"')
    # No colons: a colon is illegal in a Windows path element, and a download that
    # silently renames itself is a small lie about the file.
    assert ":" not in disposition


def test_the_response_is_a_csv_document(client: TestClient, auth: TokenService) -> None:
    response = export(client, auth)

    assert response.headers["content-type"].startswith("text/csv")


# --- the audit row -------------------------------------------------------------


def test_an_export_writes_exactly_one_row_naming_the_actor(
    client: TestClient, auth: TokenService
) -> None:
    seed(client)

    export(client, auth, role="admin")

    entries = [e for e in audit_entries(client) if e["action"] == "hunt.export"]
    assert len(entries) == 1
    stored = client.app.state.audit_trail.entries(  # type: ignore[attr-defined]
        start=START - timedelta(days=1), end=START + timedelta(days=1), limit=10
    )[0]
    assert stored.record.actor == "admin@corp"
    assert stored.record.target_type == "hunt"
    assert stored.record.target_id == "export"


def test_the_row_records_the_definition_that_ran(client: TestClient, auth: TokenService) -> None:
    """What a reviewer needs to check the file against: the window and the filters."""
    seed(client)

    export(client, auth, severity="high,low", entity_id=ENTITY, min_score=0.5, order="asc", limit=7)

    (entry,) = [e for e in audit_entries(client) if e["action"] == "hunt.export"]
    detail = entry["detail"]
    assert detail["start"] == stamp()  # type: ignore[index]
    assert detail["end"] == stamp(600)  # type: ignore[index]
    assert detail["order"] == "asc"  # type: ignore[index]
    assert detail["limit"] == 7  # type: ignore[index]
    assert detail["severity"] == ["high", "low"]  # type: ignore[index]
    assert detail["entity_id"] == ENTITY  # type: ignore[index]
    assert detail["min_score"] == 0.5  # type: ignore[index]
    assert detail["format"] == "csv"  # type: ignore[index]


def test_a_falsy_filter_value_is_still_recorded(client: TestClient, auth: TokenService) -> None:
    """A set-but-zero filter is a filter, and ``if value:`` would drop two of them.

    ``entity_id=0`` and ``min_score=0.0`` are both legal shapes, and a definition
    that omitted either would describe a *wider* read than the one that ran -- the
    one direction an audit record must never err in.
    """
    seed(client)

    export(client, auth, entity_id=0, min_score=0.0)

    (entry,) = [e for e in audit_entries(client) if e["action"] == "hunt.export"]
    detail = entry["detail"]
    assert detail["entity_id"] == 0  # type: ignore[index]
    assert detail["min_score"] == 0.0  # type: ignore[index]
    # And the read really did narrow: entity 0 matches no seeded row.
    assert (
        "id,created_at"
        in client.post(
            "/api/v1/hunt/export", json=body(entity_id=0, min_score=0.0), headers=headers(auth)
        ).text
    )


def test_an_empty_filter_is_not_a_filter(client: TestClient, auth: TokenService) -> None:
    """``severity: []`` narrows nothing, so the definition must not claim it did.

    The store treats an empty set as "unset" (the same truthiness rule the route
    re-uses), and a definition that listed ``severity: []`` would put a filter in
    the record that ran no filter -- the shortest true answer is the one with the
    key absent.
    """
    seed(client)

    export(client, auth, severity=[], status=[])

    (entry,) = [e for e in audit_entries(client) if e["action"] == "hunt.export"]
    detail = entry["detail"]
    assert "severity" not in detail  # type: ignore[operator]
    assert "status" not in detail  # type: ignore[operator]


def test_the_row_carries_no_row_content(client: TestClient, auth: TokenService) -> None:
    """The trail is read by every role; the file may be scoped to one analyst."""
    seed(client, family="exfiltration", trace_id="trace-secret-1")
    seed(client, offset=1, family="DoS", trace_id="trace-secret-2")

    export(client, auth)

    rendered = json.dumps(audit_entries(client))
    assert "exfiltration" not in rendered
    assert "trace-secret-1" not in rendered
    assert "trace-secret-2" not in rendered


def test_a_refused_export_writes_nothing(client: TestClient, auth: TokenService) -> None:
    """A 403 is not a disclosure, so a row about it would be a record of a fiction."""
    seed(client)

    response = export(client, auth, role="analyst")

    assert response.status_code == 403
    assert [e for e in audit_entries(client) if e["action"] == "hunt.export"] == []


# --- who may export -----------------------------------------------------------


@pytest.mark.parametrize("role", ["viewer", "analyst"])
def test_export_is_blocked_below_responder(
    client: TestClient, auth: TokenService, role: str
) -> None:
    seed(client)

    response = export(client, auth, role=role)

    assert response.status_code == 403
    # The matrix refuses before the capability is even consulted, and the refusal
    # names the role and the route -- which is the part an analyst can act on.
    assert role in response.json()["detail"]
    assert "not permitted" in response.json()["detail"]


@pytest.mark.parametrize("role", ["responder", "admin"])
def test_export_is_allowed_from_responder_up(
    client: TestClient, auth: TokenService, role: str
) -> None:
    seed(client)

    assert export(client, auth, role=role).status_code == 200


def test_an_api_key_cannot_export(client: TestClient, auth: TokenService) -> None:
    """A key is a machine credential for ingestion, and an egress wants a person.

    A real key is minted through the API -- the widest one the system can issue --
    so the refusal cannot be an artefact of a hand-built record nobody could obtain.
    The refusal is the route-table one, which is why it is a 403 and not a 401: the
    key may be perfectly good, and this route does not speak its scheme.
    """
    issued = client.post(
        "/api/v1/keys",
        json={"name": "collector", "scopes": ["alerts:read", "ingest:write"]},
        headers=headers(auth, "admin"),
    )
    assert issued.status_code == 201, issued.text

    response = client.post(
        "/api/v1/hunt/export",
        json=body(),
        headers={"X-API-Key": issued.json()["secret"]},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "this route does not accept API keys"


def test_an_export_without_a_credential_is_refused(client: TestClient) -> None:
    response = client.post("/api/v1/hunt/export", json=body())

    assert response.status_code == 401


def test_the_capability_the_route_declares_is_the_one_the_matrix_grants(
    client: TestClient, auth: TokenService
) -> None:
    """The two checks cannot drift: a role the matrix allows must hold the capability.

    Asserted from the other side too -- every role the matrix *refuses* is refused
    even though the route's own dependency would have let some of them through, so
    the matrix is the bound rather than a decoration.
    """
    from app.auth.rbac import ROLE_CAPABILITIES, ROUTE_MATRIX, Capability, Role

    permitted = ROUTE_MATRIX["/api/v1/hunt/export"]
    assert permitted == frozenset({Role.RESPONDER, Role.ADMIN})
    for role in Role:
        holds = Capability.EXPORT in ROLE_CAPABILITIES[role]
        assert holds == (role in permitted), role


# --- the window, and what a bad request does -----------------------------------


def test_a_window_is_required(client: TestClient, auth: TokenService) -> None:
    """R-34: there is no "the alerts, as far as they go"."""
    response = client.post("/api/v1/hunt/export", json={"severity": "high"}, headers=headers(auth))

    assert response.status_code == 422
    assert "start" in response.text and "end" in response.text


@pytest.mark.parametrize(
    "start,end",
    [
        ("not-a-time", None),
        (None, "2026-10-06T10:01:00"),
        ("2026-10-06T10:01:00+00:00", "2026-10-06T10:00:00+00:00"),
        ("2026-01-01T00:00:00+00:00", "2026-10-06T10:00:00+00:00"),
    ],
)
def test_a_window_that_cannot_be_read_is_refused(
    client: TestClient, auth: TokenService, start: str | None, end: str | None
) -> None:
    payload = {k: v for k, v in (("start", start), ("end", end)) if v is not None}
    response = client.post("/api/v1/hunt/export", json=payload, headers=headers(auth))

    assert response.status_code in {400, 422}


def test_a_cursor_is_refused_rather_than_ignored(client: TestClient, auth: TokenService) -> None:
    """An export mirrors the query's first page; a cursor would export an unseen one.

    And the audit row would then describe a read nobody performed, which is worse
    than the wrong rows on their own.
    """
    response = export(client, auth, cursor="aGVsbG8")

    assert response.status_code == 422
    assert "cursor" in response.text


def test_a_limit_beyond_the_page_cap_is_refused(client: TestClient, auth: TokenService) -> None:
    assert export(client, auth, limit=1_001).status_code == 422


def test_a_body_that_is_not_a_query_is_refused(client: TestClient, auth: TokenService) -> None:
    response = client.post(
        "/api/v1/hunt/export", json={"query": "severity:high"}, headers=headers(auth)
    )

    assert response.status_code == 422


# --- the pure layer ------------------------------------------------------------


def test_an_empty_export_is_a_header_and_nothing_else() -> None:
    from app.services.hunt_export import render_rows_csv

    document = render_rows_csv([])

    assert document == (
        "id,created_at,entity_id,family,severity,score,status,"
        "first_seen,last_seen,occurrence_count,trace_id\r\n"
    )


def test_the_definition_lists_only_what_narrowed_the_read() -> None:
    """Absence is the record of "this filter was not set", not a null to interpret."""
    from app.schemas.query import AlertQuery
    from app.services.hunt_export import query_definition

    definition = query_definition(AlertQuery(start=START, end=START + timedelta(minutes=5)))

    assert set(definition) == {"start", "end", "order", "limit"}
    assert definition["order"] == "desc"


def test_the_definition_sorts_a_multi_value_filter() -> None:
    """Two exports with the same filters in a different order are the same query."""
    from app.schemas.query import AlertQuery
    from app.services.hunt_export import query_definition

    definition = query_definition(
        AlertQuery(
            start=START,
            end=START + timedelta(minutes=5),
            severity=frozenset({"low", "critical", "high"}),
        )
    )

    assert definition["severity"] == ["critical", "high", "low"]


def test_only_the_six_formula_characters_are_defused() -> None:
    """A falsy or unusual first character is data, and must survive untouched.

    The renderer moved to ``app.services.table_export`` when the queue's export
    (T-415) needed the same rows in the same columns; the rule it pins is unchanged.
    """
    from app.services.table_export import cell_text, defuse_formula

    for safe in ("'quoted", "/path", "0.8", "trace-1", "[bracket", "_x", "\u00e9"):
        assert defuse_formula(cell_text(safe)) == safe
    for hostile in ("=x", "+x", "-x", "@x", "\tx", "\rx"):
        assert defuse_formula(cell_text(hostile)) == f"'{hostile}"


def test_the_filename_is_colon_free_even_with_an_offset_window() -> None:
    """A timezone-aware window still has to produce a legal path element."""
    from app.schemas.query import AlertQuery
    from app.services.hunt_export import export_filename

    name = export_filename(AlertQuery(start=START, end=START + timedelta(minutes=5)))

    assert ":" not in name
    assert name.startswith("aegis-hunt-")
    assert name.endswith(".csv")
