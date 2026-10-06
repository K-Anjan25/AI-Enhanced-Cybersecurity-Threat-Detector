"""T-404: the alert-detail read model behind the triage screen (FR-51).

The screen has four zones and every one of them has a rule that is easy to get
wrong in a way that still looks plausible:

* an explanation that failed must render as R-70's explicit marker with a reason,
  never as an empty panel and never as a reason invented from something else;
* evidence past FR-05's retention must say when it expired, and evidence that is
  *partly* unreadable must say that too rather than rendering a shorter trail;
* the family hint must count only *prior* alerts, and must distinguish "nobody has
  reviewed this entity" from "analysts reviewed it and agreed";
* the lookup itself is keyed on ``(id, created_at)``, because D-030 makes a bare
  id ambiguous across partitions.

Nothing here trusts the service's own summary of what it did: the tests read the
serialised response, count rows in the ledger, and assert on the JSON a client
would receive. Alerts are addressed by the id the store assigned them, never by a
literal, so a test cannot pass by accident against a different row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.auth.rbac import Role
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.db.models import Alert
from app.main import create_app
from app.schemas.query import MAX_PAGE_SIZE
from app.services.alert_detail import (
    FAMILY_HISTORY_DAYS,
    RELATED_LIMIT,
    RELATED_WINDOW_MINUTES,
    decode_evidence,
    decode_explanation,
    detail_of,
)
from app.services.retention import RetentionPolicy
from app.services.verdict_service import InMemoryVerdictLedger, record_verdict
from fastapi.testclient import TestClient

SECRET = "d" * 48
#: The partition key of the alert under test (D-030).
AT = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)
ENTITY = 7
FAMILY = "Reconnaissance"


def headers(
    auth: TokenService, role: str | Role = Role.ANALYST, subject: str = "a@corp"
) -> dict[str, str]:
    """An Authorization header for one role."""
    pair = auth.issue(subject, str(role))
    return {"Authorization": f"Bearer {pair.access_token}"}


def path_of(row: Alert) -> str:
    """The detail path for one stored alert."""
    return f"/api/v1/alerts/{row.id}"


def partition_key(created_at: datetime) -> dict[str, str]:
    """The query string that addresses the alert's partition.

    Passed as ``params`` rather than pasted into the URL: ``+00:00`` in a raw
    query string decodes as a space, and the endpoint would refuse what looks
    like a valid timestamp.
    """
    return {"created_at": created_at.isoformat()}


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    built = create_app(settings)
    built.state.token_service = auth
    return TestClient(built)


@pytest.fixture
def ledger(client: TestClient) -> InMemoryVerdictLedger:
    """The ledger the verdict routes read, installed before any request."""
    store = InMemoryVerdictLedger()
    client.app.state.verdict_ledger = store  # type: ignore[attr-defined]
    return store


def seed(
    client: TestClient,
    *,
    created_at: datetime = AT,
    entity_id: int = ENTITY,
    family: str = FAMILY,
    severity: str = "critical",
    score: float = 0.96,
    occurrence_count: int = 1,
    explanation: dict[str, Any] | None = None,
    window_ref: dict[str, Any] | None = None,
    case: str | None = None,
) -> Alert:
    """Store one alert row, as the correlator's writer would, and return it."""
    store = client.app.state.alert_store  # type: ignore[attr-defined]
    values: dict[str, object] = {
        "entity_id": entity_id,
        "family": family,
        "severity": severity,
        "score": score,
        "model_flow_id": "flownet@1.4.2",
        "model_log_id": None,
        "window_ref": (
            window_ref
            if window_ref is not None
            else {
                "store": "stream",
                "id": "win-1",
                "trace_id": "trace-1",
                "grouped": False,
                "evidence": [
                    {
                        "id": "win-1",
                        "modality": "flow",
                        "score": score,
                        "at": created_at.isoformat(),
                        "model": "flownet@1.4.2",
                    },
                ],
            }
        ),
        "explanation": (
            explanation
            if explanation is not None
            else {
                "families": [family],
                "partial_evidence": False,
                "reasons": ["dst_port_count 1,204 vs baseline 12"],
            }
        ),
        "status": "open",
        "first_seen": created_at - timedelta(minutes=5),
        "last_seen": created_at,
        "occurrence_count": occurrence_count,
    }
    # The store keys a case on its id, so two alerts that differ only in their
    # verdict history need distinct cases; the default derives one from the row's
    # own identity, which is what most tests want.
    return store.save(
        case or f"case-{entity_id}-{family}-{created_at.isoformat()}", values, created_at=created_at
    )


def detail(
    client: TestClient,
    auth: TokenService,
    row: Alert,
    *,
    role: str | Role = Role.ANALYST,
    created_at: datetime | None = None,
) -> Any:
    """Read one alert's detail payload, failing loudly if it was not served."""
    stamp = created_at if created_at is not None else row.created_at
    response = client.get(path_of(row), params=partition_key(stamp), headers=headers(auth, role))
    assert response.status_code == 200, response.text
    return response.json()


# --- R-70: the explanation contract ----------------------------------------


def test_a_scored_alert_returns_its_reasons(client: TestClient, auth: TokenService) -> None:
    row = seed(client)

    explanation = detail(client, auth, row)["explanation"]

    assert explanation["unavailable"] is False
    assert explanation["reasons"] == ["dst_port_count 1,204 vs baseline 12"]
    assert explanation["partial_evidence"] is False


def test_a_failed_explanation_renders_the_marker_with_its_reason(
    client: TestClient, auth: TokenService
) -> None:
    """R-70: the alert is raised anyway, and the screen says why it has no reasons."""
    row = seed(
        client,
        explanation={
            "families": [FAMILY],
            "partial_evidence": True,
            "explanation_unavailable": True,
            "detail": "occlusion timed out",
            "unavailable_modalities": ["log"],
        },
    )

    payload = detail(client, auth, row)

    assert payload["explanation"]["unavailable"] is True
    assert payload["explanation"]["reasons"] == []
    assert payload["explanation"]["detail"] == "occlusion timed out"
    assert payload["explanation"]["unavailable_modalities"] == ["log"]
    assert payload["explanation"]["partial_evidence"] is True


def test_a_blank_explanation_is_unavailable_and_says_so(
    client: TestClient, auth: TokenService
) -> None:
    """A row written without an explanation must not render as an empty success."""
    row = seed(client, explanation={})

    payload = detail(client, auth, row)

    assert payload["explanation"]["unavailable"] is True
    assert "no occurrence carried an explanation" in payload["explanation"]["detail"]


def test_a_partial_case_keeps_its_reasons_and_names_the_missing_modality(
    client: TestClient, auth: TokenService
) -> None:
    row = seed(
        client,
        explanation={
            "families": [FAMILY],
            "partial_evidence": True,
            "reasons": ["flow_duration 0.02s vs baseline 1.8s"],
            "unavailable_modalities": ["log"],
        },
    )

    explanation = detail(client, auth, row)["explanation"]

    assert explanation["reasons"] == ["flow_duration 0.02s vs baseline 1.8s"]
    assert explanation["unavailable"] is False
    assert explanation["unavailable_modalities"] == ["log"]
    # §8.1: a case with reasons and a missing modality is *partial*, and saying so
    # is what stops it reading as complete.
    assert explanation["partial_evidence"] is True


def test_decoding_never_invents_a_reason() -> None:
    """Unit-level: no input yields a reason R-70 did not carry."""
    for payload in (None, {}, {"unavailable": True}, {"reasons": []}, {"reasons": ["  ", ""]}):
        decoded = decode_explanation(payload)  # type: ignore[arg-type]
        assert decoded.reasons == []
        assert decoded.unavailable is True
        assert decoded.detail


# --- §4.3 zone 3: evidence, its trail and its expiry -----------------------


def test_evidence_carries_the_window_and_its_trace(client: TestClient, auth: TokenService) -> None:
    row = seed(client)

    evidence = detail(client, auth, row)["evidence"]

    assert evidence["window_id"] == "win-1"
    assert evidence["trace_id"] == "trace-1"
    assert evidence["grouped"] is False
    assert [occurrence["id"] for occurrence in evidence["occurrences"]] == ["win-1"]


def test_evidence_dates_its_own_expiry_from_the_retention_policy(
    client: TestClient, auth: TokenService
) -> None:
    """§4.3's "evidence expired at <date>" is computed, not guessed by the client."""
    recent = datetime.now(UTC) - timedelta(hours=1)
    row = seed(client, created_at=recent)

    evidence = detail(client, auth, row)["evidence"]

    policy = client.app.state.retention_policy  # type: ignore[attr-defined]
    assert evidence["retention_days"] == policy.raw_records_days
    occurrence = evidence["occurrences"][0]
    assert datetime.fromisoformat(occurrence["at"]) == recent
    assert datetime.fromisoformat(occurrence["expires_at"]) == recent + timedelta(
        days=policy.raw_records_days
    )
    assert occurrence["expired"] is False
    assert evidence["expired"] is False


def test_evidence_inside_a_retention_window_that_has_passed_is_expired(
    client: TestClient, auth: TokenService
) -> None:
    """A seven-month-old alert's raw records are gone, and the panel says when."""
    row = seed(client)  # AT is well outside a 30-day retention window.

    evidence = detail(client, auth, row)["evidence"]

    policy = client.app.state.retention_policy  # type: ignore[attr-defined]
    assert evidence["expired"] is True
    assert evidence["occurrences"][0]["expired"] is True
    assert datetime.fromisoformat(evidence["occurrences"][0]["expires_at"]) == AT + timedelta(
        days=policy.raw_records_days
    )


def test_evidence_past_retention_is_expired_with_its_date() -> None:
    """A window older than the policy is expired, and carries when it expired."""
    policy = RetentionPolicy()
    old = AT - timedelta(days=policy.raw_records_days + 1)

    evidence = decode_evidence(
        {
            "id": "win-1",
            "evidence": [{"id": "win-1", "modality": "flow", "score": 0.9, "at": old.isoformat()}],
        },
        now=AT,
        policy=policy,
    )

    assert evidence.expired is True
    assert evidence.occurrences[0].expired is True
    assert evidence.occurrences[0].expires_at == old + timedelta(days=policy.raw_records_days)


def test_a_partly_expired_trail_is_not_called_expired() -> None:
    """One occurrence left is partial evidence, not an expired panel."""
    policy = RetentionPolicy()
    fresh = AT - timedelta(days=1)
    old = AT - timedelta(days=policy.raw_records_days + 1)

    evidence = decode_evidence(
        {
            "evidence": [
                {"id": "a", "modality": "flow", "score": 0.9, "at": old.isoformat()},
                {"id": "b", "modality": "log", "score": 0.7, "at": fresh.isoformat()},
            ]
        },
        now=AT,
        policy=policy,
    )

    assert evidence.expired is False
    assert [occurrence.expired for occurrence in evidence.occurrences] == [True, False]


def test_an_unreadable_trail_entry_is_counted_rather_than_dropped() -> None:
    """A silent skip renders as a shorter trail that looks complete."""
    evidence = decode_evidence(
        {
            "evidence": [
                {"id": "a", "modality": "flow", "score": 0.9, "at": AT.isoformat()},
                {"id": "b", "modality": "flow"},
                "not-an-object",
            ]
        },
        now=AT,
        policy=RetentionPolicy(),
    )

    assert len(evidence.occurrences) == 1
    assert evidence.unreadable == 2
    assert evidence.note is not None
    assert "2" in evidence.note


def test_a_boolean_or_out_of_range_score_is_not_a_score() -> None:
    """JSON booleans are the hazard: ``true`` is not a score of 1.0.

    Python would happily compare it (``True == 1``), so an entry carrying one has
    to be rejected explicitly rather than rendered as a perfect score.
    """
    evidence = decode_evidence(
        {
            "evidence": [
                {"id": "a", "modality": "flow", "score": True, "at": AT.isoformat()},
                {"id": "b", "modality": "flow", "score": 1.5, "at": AT.isoformat()},
                {"id": "c", "modality": "flow", "score": -0.2, "at": AT.isoformat()},
            ]
        },
        now=AT,
        policy=RetentionPolicy(),
    )

    assert evidence.occurrences == []
    assert evidence.unreadable == 3


def test_a_naive_evidence_instant_is_unreadable() -> None:
    """Same rule as the partition key: a naive timestamp is not an instant.

    Assuming UTC here would date the expiry from an instant the writer never
    recorded, and the panel's "evidence expired at <date>" would be wrong by the
    viewer's offset.
    """
    evidence = decode_evidence(
        {"evidence": [{"id": "a", "modality": "flow", "score": 0.9, "at": "2026-03-15T10:00:00"}]},
        now=AT,
        policy=RetentionPolicy(),
    )

    assert evidence.occurrences == []
    assert evidence.unreadable == 1


def test_an_empty_trail_inside_a_recorded_window_is_a_stated_gap() -> None:
    """A window with no occurrences is a different row shape from no window at all.

    ``window_ref`` present but empty is what a case written by an older build
    looks like, and it must carry the same stated gap rather than an empty list
    that renders as a panel with nothing in it.
    """
    for window_ref in ({}, {"id": "win-1"}, {"id": "win-1", "evidence": []}):
        evidence = decode_evidence(window_ref, now=AT, policy=RetentionPolicy())
        assert evidence.occurrences == []
        assert evidence.note == "no evidence trail was recorded for this alert"
        assert evidence.expired is False


def test_no_trail_at_all_is_a_stated_gap() -> None:
    evidence = decode_evidence(None, now=AT, policy=RetentionPolicy())

    assert evidence.occurrences == []
    assert evidence.note == "no evidence trail was recorded for this alert"
    # Not "expired": there is nothing to have expired, and saying so would be a
    # different claim from "the records behind this alert are gone".
    assert evidence.expired is False


# --- §4.3 zone 4: the context and the family hint --------------------------


def test_family_history_counts_only_alerts_before_this_one(
    client: TestClient, auth: TokenService, ledger: InMemoryVerdictLedger
) -> None:
    """The hint is about decisions already made, so the alert on screen is excluded."""
    alert = seed(client)
    earlier = seed(client, created_at=AT - timedelta(days=2))
    seed(client, created_at=AT - timedelta(days=1))
    # ...and one after it, which must not appear either.
    seed(client, created_at=AT + timedelta(hours=1))
    record_verdict(
        ledger,
        alert_id=earlier.id,
        alert_created_at=earlier.created_at,
        verdict="false_positive",
        actor="alice@corp",
        at=AT,
    )

    history = detail(client, auth, alert)["family_history"]

    assert history["family"] == FAMILY
    assert history["window_days"] == FAMILY_HISTORY_DAYS
    assert history["prior_alerts"] == 2
    assert history["labelled"] == 1
    assert history["false_positive"] == 1


def test_the_hint_separates_unreviewed_from_agreed(
    client: TestClient, auth: TokenService, ledger: InMemoryVerdictLedger
) -> None:
    """Two false positives out of three reviewed is a different claim from two of two."""
    alert = seed(client)
    for index, verdict in enumerate(("false_positive", "false_positive", "true_positive"), start=1):
        row = seed(client, created_at=AT - timedelta(hours=index))
        record_verdict(
            ledger,
            alert_id=row.id,
            alert_created_at=row.created_at,
            verdict=verdict,
            actor="alice@corp",
            at=AT,
        )
    seed(client, created_at=AT - timedelta(hours=9))

    history = detail(client, auth, alert)["family_history"]

    assert history["prior_alerts"] == 4
    assert history["labelled"] == 3
    assert history["false_positive"] == 2
    assert history["true_positive"] == 1


def test_only_the_current_verdict_of_a_prior_alert_is_counted(
    client: TestClient, auth: TokenService, ledger: InMemoryVerdictLedger
) -> None:
    """A reconsidered alert counts once, at its latest verdict."""
    alert = seed(client)
    row = seed(client, created_at=AT - timedelta(days=1))
    record_verdict(
        ledger,
        alert_id=row.id,
        alert_created_at=row.created_at,
        verdict="true_positive",
        actor="a",
        at=AT,
    )
    record_verdict(
        ledger,
        alert_id=row.id,
        alert_created_at=row.created_at,
        verdict="benign",
        actor="a",
        at=AT,
    )

    history = detail(client, auth, alert)["family_history"]

    assert history["prior_alerts"] == 1
    assert history["labelled"] == 1
    assert history["benign"] == 1
    assert history["true_positive"] == 0


def test_history_ignores_alerts_that_are_not_this_entity_or_family(
    client: TestClient, auth: TokenService
) -> None:
    alert = seed(client)
    seed(client, created_at=AT - timedelta(days=1), entity_id=99)
    seed(client, created_at=AT - timedelta(days=1), family="Exfiltration")

    assert detail(client, auth, alert)["family_history"]["prior_alerts"] == 0


def test_an_alert_is_never_its_own_history(client: TestClient, auth: TokenService) -> None:
    """The read model, not the query window, decides what "prior" means.

    The rows handed to `detail_of` are the caller's to fetch, so the rule is
    asserted with a row the store would not have served: same instant, later id.
    Dropping the strictly-less filter would count the alert's twin -- and in a
    store whose bounds were inclusive, the alert itself.
    """
    alert = seed(client, case="the-alert")
    twin = seed(client, created_at=AT, case="a-twin-at-the-same-instant")
    assert twin.id > alert.id  # the tie the filter breaks, in list order

    payload = detail_of(
        alert,
        ledger=InMemoryVerdictLedger(),
        related_rows=[],
        family_rows=[twin],
        now=AT,
        policy=RetentionPolicy(),
    )

    assert payload.family_history.prior_alerts == 0


def test_a_row_earlier_at_the_same_instant_is_history(
    client: TestClient, auth: TokenService
) -> None:
    """Two alerts at one instant are ordered by id, exactly as the queue orders them."""
    earlier = seed(client, created_at=AT, case="the-earlier-row")
    alert = seed(client, created_at=AT, case="the-alert")
    assert earlier.id < alert.id

    payload = detail_of(
        alert,
        ledger=InMemoryVerdictLedger(),
        related_rows=[],
        family_rows=[earlier],
        now=AT,
        policy=RetentionPolicy(),
    )

    assert payload.family_history.prior_alerts == 1


def test_history_looks_back_no_further_than_its_window(
    client: TestClient, auth: TokenService
) -> None:
    alert = seed(client)
    seed(client, created_at=AT - timedelta(days=FAMILY_HISTORY_DAYS + 1))

    assert detail(client, auth, alert)["family_history"]["prior_alerts"] == 0


# --- §4.3 zone 3: related alerts -------------------------------------------


def test_related_alerts_are_the_same_entity_close_in_time(
    client: TestClient, auth: TokenService
) -> None:
    alert = seed(client)
    near = seed(client, created_at=AT - timedelta(minutes=30))
    seed(client, created_at=AT - timedelta(minutes=RELATED_WINDOW_MINUTES + 5))
    seed(client, created_at=AT + timedelta(minutes=10), entity_id=99)

    related = detail(client, auth, alert)["related"]

    assert related["window_minutes"] == RELATED_WINDOW_MINUTES
    assert [item["id"] for item in related["items"]] == [near.id]
    assert related["truncated"] is False


def test_related_alerts_never_include_the_alert_itself(
    client: TestClient, auth: TokenService
) -> None:
    alert = seed(client)

    assert detail(client, auth, alert)["related"]["items"] == []


def test_too_many_related_alerts_are_truncated_and_said_to_be(
    client: TestClient, auth: TokenService
) -> None:
    alert = seed(client)
    for index in range(RELATED_LIMIT + 3):
        seed(client, created_at=AT - timedelta(minutes=index + 1))

    related = detail(client, auth, alert)["related"]

    assert related["truncated"] is True
    assert len(related["items"]) <= RELATED_LIMIT + 1


# --- addressing, roles and the payload itself ------------------------------


def test_the_alert_is_addressed_by_id_and_partition_key(
    client: TestClient, auth: TokenService
) -> None:
    """D-030: the same id in another month is a different alert."""
    alert = seed(client)

    same_id_other_month = client.get(
        path_of(alert),
        params=partition_key(AT - timedelta(days=31)),
        headers=headers(auth),
    )

    assert same_id_other_month.status_code == 404


def test_a_naive_timestamp_is_refused(client: TestClient, auth: TokenService) -> None:
    alert = seed(client)

    response = client.get(
        path_of(alert),
        params={"created_at": "2026-03-15T10:00:00"},
        headers=headers(auth),
    )

    assert response.status_code == 400
    assert "timezone" in response.json()["detail"]


def test_a_missing_created_at_is_refused(client: TestClient, auth: TokenService) -> None:
    alert = seed(client)

    assert client.get(path_of(alert), headers=headers(auth)).status_code == 422


def test_an_unknown_alert_is_a_404(client: TestClient, auth: TokenService) -> None:
    response = client.get("/api/v1/alerts/999999", params=partition_key(AT), headers=headers(auth))

    assert response.status_code == 404


def test_reading_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/alerts/1", params=partition_key(AT))

    assert response.status_code == 401


@pytest.mark.parametrize("role", ["viewer", "analyst", "responder", "admin"])
def test_every_role_that_may_read_alerts_may_read_the_detail(
    client: TestClient, auth: TokenService, role: str
) -> None:
    row = seed(client)

    assert detail(client, auth, row, role=role)["alert"]["id"] == row.id


def test_the_detail_carries_the_alert_row_models_and_verdicts(
    client: TestClient, auth: TokenService, ledger: InMemoryVerdictLedger
) -> None:
    row = seed(client, occurrence_count=4)
    record_verdict(
        ledger,
        alert_id=row.id,
        alert_created_at=row.created_at,
        verdict="true_positive",
        actor="alice@corp",
        at=AT + timedelta(minutes=3),
    )

    payload = detail(client, auth, row)

    assert payload["alert"]["id"] == row.id
    assert payload["alert"]["occurrence_count"] == 4
    assert payload["alert"]["severity"] == "critical"
    assert payload["models"] == {"flow": "flownet@1.4.2", "log": None}
    assert payload["verdict"]["current"]["verdict"] == "true_positive"
    assert len(payload["verdict"]["history"]) == 1


def test_an_unjudged_alert_has_no_current_verdict(client: TestClient, auth: TokenService) -> None:
    """The empty state is None: an unjudged alert must not read as benign."""
    payload = detail(client, auth, seed(client))

    assert payload["verdict"]["current"] is None
    assert payload["verdict"]["history"] == []


def test_the_payload_never_carries_a_stack_trace(client: TestClient, auth: TokenService) -> None:
    """R-58: the detail is operator-facing prose, whatever the row held."""
    row = seed(
        client,
        explanation={"explanation_unavailable": True, "detail": "occlusion timed out"},
        window_ref={"evidence": [{"id": "x", "modality": "flow"}]},
    )

    body = client.get(
        path_of(row), params=partition_key(row.created_at), headers=headers(auth)
    ).text

    assert "Traceback" not in body
    assert "app/services" not in body


def test_the_detail_is_matrix_classified_for_every_role_that_may_read_alerts() -> None:
    """The matrix row is documentation and CI input, not the runtime gate.

    ``require(Capability.READ)`` is what authorises the request, so a row that
    drifted would keep serving viewers while telling the next reader (and the
    completeness check) something false. This pins the decision the row records:
    reading one alert is reading, and every role holds ``READ``.
    """
    from app.auth.rbac import ROLE_CAPABILITIES, ROUTE_MATRIX, Capability, Role

    readers = {role for role in Role if Capability.READ in ROLE_CAPABILITIES[role]}
    assert ROUTE_MATRIX["/api/v1/alerts/{alert_id}"] == frozenset(readers)


def test_the_family_history_window_is_inside_the_documented_span_limit() -> None:
    """R-34 bounds any query over the partitioned table; this window must fit."""
    from app.db.repository import MAX_QUERY_SPAN_DAYS

    assert FAMILY_HISTORY_DAYS <= MAX_QUERY_SPAN_DAYS
    assert MAX_PAGE_SIZE >= RELATED_LIMIT
