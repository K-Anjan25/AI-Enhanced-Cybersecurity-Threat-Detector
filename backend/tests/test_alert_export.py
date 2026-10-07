"""The alert batch export: the CSV, the PDF report, the RBAC and the audit row (T-415).

The acceptance criterion is one sentence -- *the exported rows match the filtered
view exactly, including the filter definition* -- and it has two halves that need
different evidence:

* **the rows match the view.** The export re-runs the same ``AlertQuery`` the queue
  reads with, so the test compares the file against ``GET /api/v1/alerts`` for the
  same filter rather than trusting that two code paths agree. A filter that the file
  ignored would still produce a plausible-looking CSV, which is exactly why it is
  compared and not spot-checked.
* **the definition is in the export.** The CSV keeps T-408's decision (rows only;
  the definition goes to the append-only trail, because a preamble would break every
  parser), and the PDF prints it, because a report read by a person without its
  window is not a report. Both halves are asserted, and both are asserted against
  the *same* mapping the audit row carries.

The PDF has no parser in this repository's dependency set, so the tests read the
bytes this module writes: the header and trailer, the page count, the strings in
the content stream and the escaping of a value that contains the format's own
delimiters. That is a test of the file this code produces rather than of a library's
idea of it.
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
from app.schemas.hunt import HUNT_CSV_COLUMNS
from app.schemas.query import AlertQuery
from app.services.alert_export import (
    _COLUMN_WEIGHTS,  # noqa: PLC2701 -- the weights are the layout's contract
    render_rows_pdf,
)
from fastapi.testclient import TestClient

SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
GENERATED = datetime(2026, 10, 6, 11, 0, tzinfo=UTC)
ENTITY = 7
#: A W3C traceparent: the one attacker-supplied field in the row (T-317), and the
#: reason the CSV defuses a leading formula character and the PDF escapes brackets.
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


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
    status: str = "open",
    score: float = 0.8,
    occurrence_count: int = 3,
    trace_id: str | None = TRACEPARENT,
) -> int:
    """Store one alert row the way the correlator's writer would, and return its id."""
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
        status=status,
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


def export(
    client: TestClient,
    auth: TokenService,
    *,
    role: str = "responder",
    path: str = "/api/v1/alerts/export",
    **overrides: object,
):
    """POST one export, as the queue does."""
    return client.post(path, json=body(**overrides), headers=headers(auth, role))


def rows_of(response) -> list[dict[str, str]]:  # type: ignore[no-untyped-def]
    """The CSV's data rows, parsed back with the standard library reader."""
    return list(csv.DictReader(io.StringIO(response.text)))


def audit_entries(client: TestClient) -> list[dict[str, object]]:
    """Every trail entry in the fixture window, newest first.

    Read through the trail's own query rather than its storage: the route writes
    through ``record_action``, and a test that reached into the store would be
    asserting on the one thing the route does not have to do.
    """
    trail = client.app.state.audit_trail  # type: ignore[attr-defined]
    return [
        {
            "action": entry.record.action.value,
            "actor": entry.record.actor,
            "target_type": entry.record.target_type,
            "target_id": entry.record.target_id,
            "detail": dict(entry.record.detail),
        }
        for entry in trail.entries(
            start=START - timedelta(days=1),
            end=START + timedelta(days=1),
            limit=100,
        )
    ]


def query(**overrides: object) -> AlertQuery:
    """The store query a body would build, for the unit-level assertions."""
    return AlertQuery(start=START, end=START + timedelta(seconds=600), **overrides)


# ── the rows are the view's rows ───────────────────────────────────────────────


def test_the_export_matches_what_the_queue_returns(client: TestClient, auth: TokenService) -> None:
    """The acceptance criterion, compared rather than spot-checked."""
    for offset in (0.0, 60.0, 120.0):
        seed(client, offset=offset)

    page = client.get(
        "/api/v1/alerts",
        params={"start": stamp(), "end": stamp(600), "limit": 100},
        headers=headers(auth),
    )
    exported = rows_of(export(client, auth))

    assert [row["id"] for row in exported] == [str(item["id"]) for item in page.json()["items"]]


def test_a_filter_narrows_the_file_the_same_way_it_narrows_the_queue(
    client: TestClient, auth: TokenService
) -> None:
    open_id = seed(client, offset=0.0, status="open")
    seed(client, offset=60.0, status="closed")

    page = client.get(
        "/api/v1/alerts",
        params={"start": stamp(), "end": stamp(600), "status": "open"},
        headers=headers(auth),
    )
    exported = rows_of(export(client, auth, status="open"))

    assert (
        [row["id"] for row in exported]
        == [str(open_id)]
        == [str(item["id"]) for item in page.json()["items"]]
    )


def test_ordering_is_honoured_in_the_file(client: TestClient, auth: TokenService) -> None:
    seed(client, offset=0.0)
    seed(client, offset=60.0)

    exported = rows_of(export(client, auth, order="asc"))

    assert [row["id"] for row in exported] == ["1", "2"]


def test_a_limit_exports_that_many_rows_and_says_it_was_truncated(
    client: TestClient, auth: TokenService
) -> None:
    for offset in (0.0, 60.0, 120.0):
        seed(client, offset=offset)

    response = export(client, auth, limit=2)

    assert len(rows_of(response)) == 2
    assert audit_entries(client)[-1]["detail"]["truncated"] is True  # type: ignore[index]


def test_an_empty_window_still_exports_a_header_and_audits_it(
    client: TestClient, auth: TokenService
) -> None:
    response = export(client, auth)

    assert response.status_code == 200
    assert rows_of(response) == []
    assert audit_entries(client)[-1]["detail"]["rows"] == 0  # type: ignore[index]


def test_the_response_is_a_csv_document(client: TestClient, auth: TokenService) -> None:
    seed(client)

    response = export(client, auth)

    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.splitlines()[0].split(",") == list(HUNT_CSV_COLUMNS)


def test_the_filename_names_the_window_and_the_format(
    client: TestClient, auth: TokenService
) -> None:
    response = export(client, auth)

    # Colon-free, so the name survives a Windows filesystem (T-408's rule), and the
    # suffix is the format's own wire value.
    assert (
        "aegis-alerts-2026-10-06T10-00-00+00-00-to-2026-10-06T10-10-00+00-00.csv"
        in response.headers["content-disposition"]
    )


def test_the_row_count_is_a_header_the_client_does_not_have_to_parse(
    client: TestClient, auth: TokenService
) -> None:
    """The dashboard reports the count without re-reading the document."""
    for offset in (0.0, 60.0):
        seed(client, offset=offset)

    csv_response = export(client, auth)
    pdf_response = export(client, auth, format="pdf")

    assert csv_response.headers["x-export-rows"] == "2"
    assert pdf_response.headers["x-export-rows"] == "2"
    assert csv_response.headers["x-export-truncated"] == "false"
    # The same number the trail records, so the screen and the audit row agree.
    assert audit_entries(client)[-1]["detail"]["rows"] == 2  # type: ignore[index]


def test_the_truncation_is_stated_to_the_client_as_well_as_the_trail(
    client: TestClient, auth: TokenService
) -> None:
    for offset in (0.0, 60.0, 120.0):
        seed(client, offset=offset)

    response = export(client, auth, limit=2)

    assert response.headers["x-export-rows"] == "2"
    assert response.headers["x-export-truncated"] == "true"


def test_a_formula_in_a_field_is_defused_in_the_file(
    client: TestClient, auth: TokenService
) -> None:
    seed(client, family="=cmd|' /C calc'!A0")

    row = rows_of(export(client, auth))[0]

    assert row["family"] == "'=cmd|' /C calc'!A0"


# ── the PDF report ─────────────────────────────────────────────────────────────


def test_the_report_is_a_pdf_document(client: TestClient, auth: TokenService) -> None:
    seed(client)

    response = export(client, auth, format="pdf")

    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-1.4")
    assert response.content.rstrip().endswith(b"%%EOF")
    assert b"xref" in response.content and b"trailer" in response.content
    assert "aegis-alerts-" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.pdf"')


def test_the_report_prints_the_filter_definition(client: TestClient, auth: TokenService) -> None:
    """The half of the acceptance criterion the CSV leaves to the trail."""
    seed(client)

    content = export(client, auth, format="pdf", status="open", family="exfiltration").content

    assert b"Filter:" in content
    assert b"status=open" in content or b"status=['open']" in content
    assert b"family=" in content


def test_the_report_prints_the_rows(client: TestClient, auth: TokenService) -> None:
    seed(client, family="Reconnaissance")

    content = export(client, auth, format="pdf").content

    assert b"created_at" in content  # the column header
    assert b"(Reconnaissance)" in content
    assert TRACEPARENT.encode() in content
    assert b"Aegis alert export" in content


def test_a_short_batch_is_one_page(client: TestClient, auth: TokenService) -> None:
    seed(client)

    content = export(client, auth, format="pdf").content

    assert b"/Count 1" in content
    assert content.count(b"/Type /Page ") == 1


def test_a_long_batch_paginates_and_names_the_page(client: TestClient, auth: TokenService) -> None:
    for index in range(45):
        seed(client, offset=float(index), entity_id=index + 1)

    content = export(client, auth, format="pdf", limit=1000).content

    assert b"/Count 2" in content
    assert content.count(b"/Type /Page ") == 2
    assert b"Aegis alert export - page 2 of 2" in content


def test_a_truncated_report_says_so_on_the_page(client: TestClient, auth: TokenService) -> None:
    for index in range(3):
        seed(client, offset=float(index))

    content = export(client, auth, format="pdf", limit=2).content

    assert b"the first page of a longer result" in content


def test_an_empty_batch_is_a_page_that_says_zero(client: TestClient, auth: TokenService) -> None:
    content = export(client, auth, format="pdf").content

    assert b"/Count 1" in content
    assert b"0 rows" in content


def test_the_pdf_error_the_format_has_is_escaped(client: TestClient, auth: TokenService) -> None:
    """A value carrying the format's own delimiters must not end the string."""
    seed(client, trace_id="00-(injected)-01")

    content = export(client, auth, format="pdf").content

    assert rb"(00-\(injected\)-01)" in content
    assert b"(00-(injected)-01)" not in content


def test_a_character_outside_the_core_font_is_stated_not_dropped(
    client: TestClient, auth: TokenService
) -> None:
    seed(client, family="Reconnaissance\u2014sweep")

    content = export(client, auth, format="pdf").content

    # The em dash is outside WinAnsi's printable set for this writer's ASCII range,
    # so it is rendered as `?` rather than silently vanishing.
    assert b"(Reconnaissance?sweep)" in content


def test_the_report_is_deterministic_for_a_fixed_instant() -> None:
    from app.schemas.query import AlertRow

    row = AlertRow(
        id=1,
        created_at=START,
        entity_id=ENTITY,
        family="exfiltration",
        severity="high",
        score=0.8,
        status="open",
        first_seen=START,
        last_seen=START,
        occurrence_count=3,
        trace_id=TRACEPARENT,
    )

    first = render_rows_pdf([row], query(), generated_at=GENERATED)
    second = render_rows_pdf([row], query(), generated_at=GENERATED)

    assert first == second


def test_instants_are_rendered_to_the_second() -> None:
    from app.schemas.query import AlertRow

    row = AlertRow(
        id=1,
        created_at=START.replace(microsecond=123_456),
        entity_id=ENTITY,
        family="exfiltration",
        severity="high",
        score=0.8,
        status="open",
        first_seen=START,
        last_seen=START,
        occurrence_count=3,
        trace_id=None,
    )

    content = render_rows_pdf([row], query(), generated_at=GENERATED)

    assert b"(2026-10-06T10:00:00+00:00)" in content
    assert b".123456" not in content


def test_the_layout_covers_every_published_column() -> None:
    """A column the report has no width for would be drawn at zero width."""
    assert set(_COLUMN_WEIGHTS) == set(HUNT_CSV_COLUMNS)
    assert abs(sum(_COLUMN_WEIGHTS.values()) - 1.0) < 1e-9


def test_a_column_that_does_not_fit_is_clipped_with_a_marker(
    client: TestClient, auth: TokenService
) -> None:
    seed(client, family="f" * 200)

    content = export(client, auth, format="pdf").content

    assert b"..." in content
    assert b"f" * 200 not in content


# ── who may take a copy, and what the trail says ───────────────────────────────


def test_an_export_writes_exactly_one_row_naming_the_actor(
    client: TestClient, auth: TokenService
) -> None:
    seed(client)

    export(client, auth)

    entries = audit_entries(client)
    assert len(entries) == 1
    assert entries[0]["action"] == "alert.export"
    assert entries[0]["actor"] == "responder@corp"
    assert entries[0]["target_type"] == "alert_batch"


def test_the_row_records_the_definition_that_ran(client: TestClient, auth: TokenService) -> None:
    seed(client)

    export(client, auth, status="open", severity="high", limit=5, format="pdf")

    detail = audit_entries(client)[-1]["detail"]
    assert detail["status"] == ["open"]  # type: ignore[index]
    assert detail["severity"] == ["high"]  # type: ignore[index]
    assert detail["limit"] == 5  # type: ignore[index]
    assert detail["format"] == "pdf"  # type: ignore[index]
    assert detail["start"] == stamp()  # type: ignore[index]


def test_the_row_carries_no_row_content(client: TestClient, auth: TokenService) -> None:
    """R-58: the trail is readable by every role, the batch may not be."""
    seed(client, family="marker-family", trace_id="marker-trace")

    export(client, auth)

    detail = json.dumps(audit_entries(client)[-1]["detail"])
    assert "marker-family" not in detail
    assert "marker-trace" not in detail


def test_a_refused_export_writes_nothing(client: TestClient, auth: TokenService) -> None:
    seed(client)

    response = export(client, auth, role="analyst")

    assert response.status_code == 403
    assert audit_entries(client) == []


@pytest.mark.parametrize("role", ["viewer", "analyst"])
def test_export_is_blocked_below_responder(
    client: TestClient, auth: TokenService, role: str
) -> None:
    seed(client)

    assert export(client, auth, role=role).status_code == 403


@pytest.mark.parametrize("role", ["responder", "admin"])
def test_export_is_allowed_from_responder_up(
    client: TestClient, auth: TokenService, role: str
) -> None:
    seed(client)

    assert export(client, auth, role=role).status_code == 200


def test_an_export_without_a_credential_is_refused(client: TestClient) -> None:
    response = client.post("/api/v1/alerts/export", json=body())

    assert response.status_code == 401


def test_the_hunt_and_queue_exports_agree_on_who_may_take_a_copy(
    client: TestClient, auth: TokenService
) -> None:
    """Two exports with two role rules would be a way around the stricter one."""
    from app.auth.rbac import ROUTE_MATRIX

    assert ROUTE_MATRIX["/api/v1/alerts/export"] == ROUTE_MATRIX["/api/v1/hunt/export"]


# ── the request is the query, and nothing else ─────────────────────────────────


def test_a_cursor_is_refused_rather_than_ignored(client: TestClient, auth: TokenService) -> None:
    seed(client)

    response = export(client, auth, cursor="anything")

    assert response.status_code == 422


def test_a_window_is_required(client: TestClient, auth: TokenService) -> None:
    response = client.post(
        "/api/v1/alerts/export",
        json={"order": "desc"},
        headers=headers(auth),
    )

    assert response.status_code == 422


def test_a_window_that_cannot_be_read_is_refused(client: TestClient, auth: TokenService) -> None:
    response = export(client, auth, start="2026-10-06T10:00:00", end=stamp(600))

    assert response.status_code == 400


def test_an_unknown_format_is_refused(client: TestClient, auth: TokenService) -> None:
    response = export(client, auth, format="docx")

    assert response.status_code == 422


def test_a_limit_beyond_the_page_cap_is_refused(client: TestClient, auth: TokenService) -> None:
    response = export(client, auth, limit=10_000)

    assert response.status_code == 422
