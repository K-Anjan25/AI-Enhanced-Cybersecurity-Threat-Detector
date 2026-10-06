"""T-309: analyst verdicts -- immutable records, superseded in order (FR-16, FR-18).

The acceptance criterion is that verdicts are immutable once written and that a
second verdict supersedes the first **with history retained**. So the tests below
do not ask the service what it did and believe it: they count records in the
ledger, assert that the old record still reads as it did, and assert the chain
``supersedes`` links in order. An implementation that returns a fresh-looking
object while overwriting the stored one passes the weak test and fails these.

FR-18's other half -- the weekly threshold recomputation from this feedback -- is
not here. Persisting the feedback is the input to that job; the job itself
consumes a window of verdicts and is not part of this task.

Two rules shape the storage. An alert is addressed by ``(id, created_at)``
because D-030 makes a bare id ambiguous across partitions, and R-34 forbids
touching the partitioned table without the time bound -- so the same id under a
different ``created_at`` is a different alert here, and that is tested rather
than assumed. The empty state is ``None``, not a default verdict: an alert nobody
has judged must not read as ``benign``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest
from app.auth.rbac import ROLE_CAPABILITIES, ROUTE_MATRIX, Capability, Role
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.db.models import Verdict
from app.main import create_app
from app.schemas.verdict import MAX_NOTE_LENGTH
from app.services.verdict_service import (
    AlertVerdictUpdate,
    InMemoryVerdictLedger,
    UnknownVerdict,
    VerdictAction,
    VerdictLedger,
    VerdictOutcome,
    VerdictRecord,
    alert_verdict_update,
    record_verdict,
)
from fastapi.testclient import TestClient

#: The alert's partition key: required to address it at all (D-030, R-34).
AT = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)
#: When the analyst decided -- distinct from AT, so a route that conflates the
#: two (`verdict_at = alert.created_at`) is caught.
WHEN = datetime(2026, 3, 15, 10, 5, 0, tzinfo=UTC)
ALERT = 42
ANALYST = "alice@example.com"
OTHER = "bob@example.com"

SECRET = "v" * 48
VERDICT_PATH = "/api/v1/alerts/{alert_id}/verdict"
HISTORY_PATH = "/api/v1/alerts/{alert_id}/verdicts"


def record(
    ledger: VerdictLedger,
    *,
    verdict: str | Verdict = Verdict.true_positive,
    actor: str = ANALYST,
    at: datetime = WHEN,
    note: str | None = None,
    alert_id: int = ALERT,
    created_at: datetime = AT,
) -> VerdictOutcome:
    """Record one verdict with the test's defaults, overridable per test."""
    return record_verdict(
        ledger,
        alert_id=alert_id,
        alert_created_at=created_at,
        verdict=verdict,
        actor=actor,
        at=at,
        note=note,
    )


# --- the acceptance criterion: immutability, supersession, retention ----------


def test_a_first_verdict_is_recorded_and_becomes_current() -> None:
    ledger = InMemoryVerdictLedger()
    outcome = record(ledger)

    assert outcome.action is VerdictAction.recorded
    assert outcome.superseded is None
    assert ledger.current(ALERT, AT) is outcome.record
    assert outcome.record.verdict is Verdict.true_positive
    assert outcome.record.actor == ANALYST
    assert outcome.record.at == WHEN


def test_the_first_record_supersedes_nothing() -> None:
    ledger = InMemoryVerdictLedger()
    assert record(ledger).record.supersedes is None


def test_a_second_verdict_supersedes_without_erasing_the_first() -> None:
    ledger = InMemoryVerdictLedger()
    first = record(ledger, verdict=Verdict.true_positive).record
    second = record(ledger, verdict=Verdict.false_positive, at=WHEN + timedelta(minutes=1))

    assert second.action is VerdictAction.recorded
    assert second.superseded is first
    assert second.record.supersedes == first.id

    history = ledger.history(ALERT, AT)
    assert [entry.id for entry in history] == [first.id, second.record.id]
    # The first record is not a draft that was edited: it reads exactly as it did.
    assert history[0] == first
    assert history[0].verdict is Verdict.true_positive
    assert history[0].supersedes is None


def test_the_history_reads_as_a_supersede_chain() -> None:
    ledger = InMemoryVerdictLedger()
    record(ledger)
    record(ledger, verdict=Verdict.false_positive, at=WHEN + timedelta(minutes=1))
    record(ledger, verdict=Verdict.benign, at=WHEN + timedelta(minutes=2))

    chain = ledger.history(ALERT, AT)
    assert [entry.supersedes for entry in chain] == [None, chain[0].id, chain[1].id]
    assert [entry.verdict for entry in chain] == [
        Verdict.true_positive,
        Verdict.false_positive,
        Verdict.benign,
    ]


def test_verdict_ids_are_positional_within_the_alert() -> None:
    """Ids come from the history, not from a process counter (D-036)."""
    ledger = InMemoryVerdictLedger()
    assert record(ledger).record.id == "42-v1"
    assert record(ledger, verdict=Verdict.benign).record.id == "42-v2"
    assert record(ledger, alert_id=7).record.id == "7-v1"


def test_the_store_offers_no_way_to_change_history() -> None:
    """The interface is the invariant: there is no update and no delete."""
    public = {name for name in dir(VerdictLedger) if not name.startswith("_")}
    assert public == {"append", "current", "history"}
    assert not hasattr(InMemoryVerdictLedger(), "update")
    assert not hasattr(InMemoryVerdictLedger(), "delete")


def test_a_stored_record_is_frozen() -> None:
    ledger = InMemoryVerdictLedger()
    stored = record(ledger).record
    with pytest.raises(FrozenInstanceError):
        stored.verdict = Verdict.benign  # type: ignore[misc]


def test_history_returns_a_snapshot_not_a_live_view() -> None:
    ledger = InMemoryVerdictLedger()
    record(ledger)
    before = ledger.history(ALERT, AT)
    record(ledger, verdict=Verdict.benign)
    assert len(before) == 1
    assert len(ledger.history(ALERT, AT)) == 2


# --- a repeat is not a supersession -------------------------------------------


def test_repeating_the_current_verdict_is_not_a_new_row() -> None:
    """A client retry must not manufacture a reconsideration."""
    ledger = InMemoryVerdictLedger()
    first = record(ledger)
    repeat = record(ledger)

    assert repeat.action is VerdictAction.unchanged
    assert repeat.record is first.record
    assert repeat.superseded is None
    assert len(ledger.history(ALERT, AT)) == 1


def test_a_repeat_is_unchanged_even_with_a_different_note() -> None:
    """The note is not the verdict; re-sending one does not create a record."""
    ledger = InMemoryVerdictLedger()
    record(ledger, note="first look")
    repeat = record(ledger, note="second look")
    assert repeat.action is VerdictAction.unchanged
    assert repeat.record.note == "first look"
    assert len(ledger) == 1


def test_a_different_verdict_from_the_same_analyst_supersedes() -> None:
    ledger = InMemoryVerdictLedger()
    record(ledger, verdict=Verdict.true_positive)
    second = record(ledger, verdict=Verdict.false_positive)
    assert second.action is VerdictAction.recorded
    assert second.superseded is not None
    assert len(ledger.history(ALERT, AT)) == 2


def test_agreement_from_another_analyst_is_recorded() -> None:
    """Same verdict, different person: that is a second opinion worth keeping."""
    ledger = InMemoryVerdictLedger()
    record(ledger, actor=ANALYST)
    second = record(ledger, actor=OTHER)

    assert second.action is VerdictAction.recorded
    assert second.superseded is not None
    assert [entry.actor for entry in ledger.history(ALERT, AT)] == [ANALYST, OTHER]


def test_a_repeat_from_the_analyst_who_owns_the_current_verdict_is_unchanged() -> None:
    ledger = InMemoryVerdictLedger()
    record(ledger, actor=ANALYST)
    record(ledger, verdict=Verdict.benign, actor=OTHER)
    third = record(ledger, verdict=Verdict.benign, actor=OTHER)

    assert third.action is VerdictAction.unchanged
    assert len(ledger.history(ALERT, AT)) == 2


# --- the input is validated, and a refusal writes nothing ---------------------


def test_an_unknown_verdict_is_refused_by_name() -> None:
    ledger = InMemoryVerdictLedger()
    with pytest.raises(UnknownVerdict, match="benign"):
        record(ledger, verdict="maybe")
    assert len(ledger) == 0


def test_every_fr16_verdict_is_accepted() -> None:
    ledger = InMemoryVerdictLedger()
    for index, verdict in enumerate(Verdict):
        record(ledger, verdict=verdict, at=WHEN + timedelta(minutes=index))
    assert [entry.verdict for entry in ledger.history(ALERT, AT)] == list(Verdict)


def test_a_naive_decision_time_is_refused() -> None:
    with pytest.raises(ValueError, match="at must be timezone-aware"):
        record(InMemoryVerdictLedger(), at=datetime(2026, 3, 15, 10, 5))


def test_a_naive_partition_key_is_refused() -> None:
    with pytest.raises(ValueError, match="alert_created_at must be timezone-aware"):
        record(InMemoryVerdictLedger(), created_at=datetime(2026, 3, 15, 10, 0))


def test_an_unattributed_verdict_is_refused() -> None:
    with pytest.raises(ValueError, match="name the analyst"):
        record(InMemoryVerdictLedger(), actor="   ")


def test_a_note_is_stripped_and_emptiness_becomes_none() -> None:
    ledger = InMemoryVerdictLedger()
    padded = record(ledger, note="  looked at the raw flows  ").record
    assert padded.note == "looked at the raw flows"

    # A different verdict, so this is a new record rather than a repeat.
    blank = record(ledger, verdict=Verdict.benign, note="   ").record
    assert blank.note is None


def test_an_over_long_note_is_refused() -> None:
    with pytest.raises(ValueError, match=str(MAX_NOTE_LENGTH)):
        record(InMemoryVerdictLedger(), note="x" * (MAX_NOTE_LENGTH + 1))


def test_a_record_needs_an_id_and_a_real_alert() -> None:
    with pytest.raises(ValueError, match="needs an id"):
        VerdictRecord(
            id=" ",
            alert_id=ALERT,
            alert_created_at=AT,
            verdict=Verdict.benign,
            actor=ANALYST,
            at=WHEN,
            note=None,
            supersedes=None,
        )
    with pytest.raises(ValueError, match="positive row id"):
        VerdictRecord(
            id="0-v1",
            alert_id=0,
            alert_created_at=AT,
            verdict=Verdict.benign,
            actor=ANALYST,
            at=WHEN,
            note=None,
            supersedes=None,
        )


# --- D-030: the alert is the (id, created_at) pair ----------------------------


def test_the_same_id_in_another_partition_is_a_different_alert() -> None:
    ledger = InMemoryVerdictLedger()
    record(ledger, verdict=Verdict.true_positive)
    record(
        ledger,
        verdict=Verdict.false_positive,
        created_at=AT + timedelta(microseconds=1),
    )
    assert len(ledger.history(ALERT, AT)) == 1
    assert ledger.history(ALERT, AT)[0].verdict is Verdict.true_positive


def test_a_partition_key_is_an_instant_not_a_spelling() -> None:
    """``10:00Z`` and ``12:00+02:00`` are the same alert, as Postgres sees it."""
    other_spelling = datetime.fromisoformat("2026-03-15T12:00:00+02:00")
    assert other_spelling == AT  # the premise, stated so a tz change fails loudly

    ledger = InMemoryVerdictLedger()
    record(ledger, verdict=Verdict.true_positive)
    outcome = record_verdict(
        ledger,
        alert_id=ALERT,
        alert_created_at=other_spelling,
        verdict=Verdict.false_positive,
        actor=ANALYST,
        at=WHEN,
    )
    assert outcome.superseded is not None
    assert len(ledger.history(ALERT, other_spelling)) == 2


# --- the alert-row write ------------------------------------------------------


def test_the_row_update_carries_the_partition_key_and_the_actor() -> None:
    ledger = InMemoryVerdictLedger()
    update = alert_verdict_update(record(ledger, note="x"))
    assert isinstance(update, AlertVerdictUpdate)
    assert update == AlertVerdictUpdate(
        alert_id=ALERT,
        created_at=AT,
        verdict="true_positive",
        verdict_at=WHEN,
        actor=ANALYST,
    )


def test_an_unchanged_verdict_produces_no_write() -> None:
    """Issuing one would move verdict_at forward on a mere re-send."""
    ledger = InMemoryVerdictLedger()
    record(ledger)
    assert alert_verdict_update(record(ledger)) is None


# --- the HTTP surface ---------------------------------------------------------


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    built = create_app(settings)
    built.state.token_service = auth
    return TestClient(built)


def headers(
    auth: TokenService, role: str | Role = Role.ANALYST, subject: str = ANALYST
) -> dict[str, str]:
    """An Authorization header for one role and subject."""
    pair = auth.issue(subject, str(role))
    return {"Authorization": f"Bearer {pair.access_token}"}


def body(**overrides: object) -> dict[str, object]:
    """A valid verdict request, with overrides applied."""
    payload: dict[str, object] = {
        "verdict": "true_positive",
        "created_at": "2026-03-15T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_the_roles_that_may_post_are_the_roles_that_hold_verdict() -> None:
    holders = {role for role in Role if Capability.VERDICT in ROLE_CAPABILITIES[role]}
    assert holders == {Role.ANALYST, Role.RESPONDER, Role.ADMIN}
    assert ROUTE_MATRIX[VERDICT_PATH] == holders
    assert Role.VIEWER not in holders


@pytest.mark.parametrize("role", list(Role))
def test_the_matrix_and_the_route_agree_on_who_may_post(
    client: TestClient, auth: TokenService, role: Role
) -> None:
    """The live route and the CI matrix must say the same thing."""
    allowed = role in ROUTE_MATRIX[VERDICT_PATH]
    response = client.post("/api/v1/alerts/7/verdict", json=body(), headers=headers(auth, role))
    assert (response.status_code == 200) is allowed, response.text


def test_a_viewer_is_refused_with_the_role_named_and_no_capability_echo(
    client: TestClient, auth: TokenService
) -> None:
    response = client.post(
        "/api/v1/alerts/7/verdict", json=body(), headers=headers(auth, Role.VIEWER)
    )
    assert response.status_code == 403
    assert "viewer" in response.json()["detail"]
    assert "verdict" not in response.json()["detail"].lower()


def test_an_unauthenticated_verdict_is_401_with_a_challenge(client: TestClient) -> None:
    response = client.post("/api/v1/alerts/7/verdict", json=body())
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_the_route_records_the_token_subject_not_a_placeholder(
    client: TestClient, auth: TokenService
) -> None:
    posted = client.post(
        "/api/v1/alerts/7/verdict", json=body(), headers=headers(auth, subject="alice@corp")
    )
    assert posted.status_code == 200
    assert posted.json()["record"]["actor"] == "alice@corp"
    assert posted.json()["action"] == "recorded"


def test_the_alert_state_is_the_pair_from_the_body(client: TestClient, auth: TokenService) -> None:
    """An alert is addressed by (id, created_at); the id alone is ambiguous."""
    client.post(
        "/api/v1/alerts/7/verdict",
        json=body(),
        headers=headers(auth),
    )
    other = client.get(
        "/api/v1/alerts/7/verdicts",
        params={"created_at": "2026-03-15T11:00:00Z"},
        headers=headers(auth, Role.VIEWER, subject="view@corp"),
    )
    assert other.json() == {
        "alert_id": 7,
        "created_at": "2026-03-15T11:00:00Z",
        "current": None,
        "items": [],
    }


def test_an_unknown_verdict_is_a_400_that_names_the_values(
    client: TestClient, auth: TokenService
) -> None:
    response = client.post(
        "/api/v1/alerts/7/verdict", json=body(verdict="certainly-not"), headers=headers(auth)
    )
    assert response.status_code == 400
    assert "false_positive" in response.json()["detail"]


def test_a_naive_created_at_is_a_400(client: TestClient, auth: TokenService) -> None:
    response = client.post(
        "/api/v1/alerts/7/verdict",
        json=body(created_at="2026-03-15T10:00:00"),
        headers=headers(auth),
    )
    assert response.status_code == 400
    assert "timezone" in response.json()["detail"]


def test_an_over_long_note_is_refused_before_the_service_sees_it(
    client: TestClient, auth: TokenService
) -> None:
    response = client.post(
        "/api/v1/alerts/7/verdict",
        json=body(note="x" * (MAX_NOTE_LENGTH + 1)),
        headers=headers(auth),
    )
    assert response.status_code == 422


def test_the_history_endpoint_returns_the_chain_with_the_current_last(
    client: TestClient, auth: TokenService
) -> None:
    first = client.post("/api/v1/alerts/9/verdict", json=body(), headers=headers(auth))
    second = client.post(
        "/api/v1/alerts/9/verdict",
        json=body(verdict="false_positive"),
        headers=headers(auth),
    )
    assert second.json()["record"]["supersedes"] == first.json()["record"]["id"]

    history = client.get(
        "/api/v1/alerts/9/verdicts",
        params={"created_at": "2026-03-15T10:00:00Z"},
        headers=headers(auth, Role.VIEWER, subject="view@corp"),
    )
    assert history.status_code == 200
    payload = history.json()
    assert [entry["verdict"] for entry in payload["items"]] == [
        "true_positive",
        "false_positive",
    ]
    assert payload["current"]["id"] == payload["items"][-1]["id"]


def test_the_history_endpoint_needs_the_partition_key(
    client: TestClient, auth: TokenService
) -> None:
    """A missing created_at is a client error, not a scan of every partition."""
    response = client.get("/api/v1/alerts/9/verdicts", headers=headers(auth, Role.VIEWER))
    assert response.status_code == 422


def test_repeating_through_the_api_does_not_pad_the_history(
    client: TestClient, auth: TokenService
) -> None:
    client.post("/api/v1/alerts/9/verdict", json=body(), headers=headers(auth))
    repeat = client.post("/api/v1/alerts/9/verdict", json=body(), headers=headers(auth))
    assert repeat.json()["action"] == "unchanged"

    history = client.get(
        "/api/v1/alerts/9/verdicts",
        params={"created_at": "2026-03-15T10:00:00Z"},
        headers=headers(auth, Role.VIEWER),
    )
    assert len(history.json()["items"]) == 1


def test_the_route_reads_the_ledger_from_app_state(client: TestClient, auth: TokenService) -> None:
    """The process-wide ledger is replaceable, so the persistent one can be wired."""
    ledger = InMemoryVerdictLedger()
    client.app.state.verdict_ledger = ledger  # type: ignore[attr-defined]
    client.post("/api/v1/alerts/11/verdict", json=body(), headers=headers(auth))
    assert len(ledger) == 1
    assert ledger.current(11, datetime(2026, 3, 15, 10, 0, tzinfo=UTC)) is not None


def test_an_analyst_and_a_viewer_see_the_same_history(
    client: TestClient, auth: TokenService
) -> None:
    client.post("/api/v1/alerts/12/verdict", json=body(), headers=headers(auth, Role.ANALYST))
    as_viewer = client.get(
        "/api/v1/alerts/12/verdicts",
        params={"created_at": "2026-03-15T10:00:00Z"},
        headers=headers(auth, Role.VIEWER, subject="view@corp"),
    )
    as_analyst = client.get(
        "/api/v1/alerts/12/verdicts",
        params={"created_at": "2026-03-15T10:00:00Z"},
        headers=headers(auth, Role.ANALYST),
    )
    assert as_viewer.json() == as_analyst.json()
    assert as_viewer.json()["current"]["verdict"] == "true_positive"
