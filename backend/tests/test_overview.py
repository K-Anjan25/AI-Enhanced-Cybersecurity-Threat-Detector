"""T-416: the overview aggregation endpoint (FR-50).

Three acceptance criteria, and each is a test rather than a note:

* **One request fills the tiles, the series and the entity list.** The response is
  one window's aggregate; the dashboard's own test counts the requests, and this
  file asserts the three panels are in one body and describe the same window.
* **Counts are complete for the window rather than capped at 5,000 rows.** The test
  seeds more rows than the old page walk could read and asserts the tile, the
  series total and the open count are the window's own.
* **Every entity renders its host or user value.** The registry is seeded with a
  host and a user, and the response names them; an id the registry has never seen
  comes back *unnamed* -- ``named: false`` with nulls -- rather than as a field the
  API forgot, because a screen that prints "Entity 42" must be able to say why.

The arithmetic's edge cases (clamping, unknown bands, total ordering, the mean's
coverage) are tested against the pure function as well: they are the rules that
make the numbers add up, and a route test would only observe them through a
serialisation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.auth.rbac import Role
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.db.models import Alert
from app.db.repository import TimeRange, alert_aggregate_statements
from app.main import create_app
from app.services.entity_registry import EntityRegistry
from app.services.overview import (
    BUCKET_MINUTES_MAX,
    ENTITY_LIMIT_MAX,
    FAMILY_LIMIT_MAX,
    Aggregate,
    aggregate,
    bucket_starts,
)
from fastapi.testclient import TestClient

SECRET = "o" * 48
#: The window every test aggregates, unless it says otherwise.
START = datetime(2026, 3, 15, 9, 0, 0, tzinfo=UTC)
END = START + timedelta(hours=2)
AT = START + timedelta(minutes=10)
HOST = "web-01.corp"
USER = "j.doe@corp"


def headers(
    auth: TokenService, role: str | Role = Role.ANALYST, subject: str = "a@corp"
) -> dict[str, str]:
    """An Authorization header for one role."""
    pair = auth.issue(subject, str(role))
    return {"Authorization": f"Bearer {pair.access_token}"}


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    built = create_app(settings)
    built.state.token_service = auth
    return TestClient(built)


@pytest.fixture
def registry(client: TestClient) -> EntityRegistry:
    """The registry the overview resolves entity names through."""
    return client.app.state.entity_registry  # type: ignore[attr-defined]


def seed(
    client: TestClient,
    *,
    created_at: datetime = AT,
    entity_id: int = 1,
    severity: str = "high",
    family: str = "Reconnaissance",
    score: float = 0.9,
    occurrences: int = 1,
    status: str = "open",
    verdict: str | None = None,
    verdict_at: datetime | None = None,
    case: str | None = None,
) -> Alert:
    """Store one alert row, as the correlator's writer would, and return it."""
    store = client.app.state.alert_store  # type: ignore[attr-defined]
    values: dict[str, object] = {
        "entity_id": entity_id,
        "family": family,
        "severity": severity,
        "score": score,
        "model_flow_id": None,
        "model_log_id": None,
        "window_ref": {"store": "stream", "id": "win-1", "trace_id": None, "grouped": False},
        "explanation": {"families": [], "partial_evidence": False, "reasons": []},
        "status": status,
        "first_seen": created_at - timedelta(minutes=1),
        "last_seen": created_at,
        "occurrence_count": occurrences,
        "verdict": verdict,
        "verdict_at": verdict_at,
    }
    return store.save(
        case or f"case-{entity_id}-{severity}-{created_at.isoformat()}-{len(store)}",
        values,
        created_at=created_at,
    )


def read(
    client: TestClient,
    auth: TokenService,
    *,
    start: datetime = START,
    end: datetime = END,
    role: str | Role = Role.ANALYST,
    **params: Any,
) -> Any:
    """Call the overview endpoint with the window as query parameters."""
    return client.get(
        "/api/v1/overview",
        params={"start": start.isoformat(), "end": end.isoformat(), **params},
        headers=headers(auth, role),
    )


def row(
    *,
    created_at: datetime = AT,
    entity_id: int = 1,
    severity: str = "high",
    family: str = "Reconnaissance",
    status: str = "open",
    score: float = 0.9,
    occurrences: int = 1,
    verdict: str | None = None,
    verdict_at: datetime | None = None,
) -> Alert:
    """An :class:`Alert` for the pure arithmetic's tests, never added to a session."""
    return Alert(
        id=entity_id * 1_000 + int(created_at.timestamp()) % 1_000,
        created_at=created_at,
        entity_id=entity_id,
        family=family,
        severity=severity,
        score=score,
        status=status,
        first_seen=created_at,
        last_seen=created_at,
        occurrence_count=occurrences,
        verdict=verdict,
        verdict_at=verdict_at,
    )


def summary_of(rows: list[Alert], **kwargs: Any) -> Aggregate:
    """Aggregate directly, with the window the tests describe."""
    return aggregate(rows, start=START, end=END, **kwargs)


class TestTheArithmetic:
    """The rules that make the panels add up, without a request in the way."""

    def test_every_row_lands_in_a_bucket_even_a_clamped_one(self) -> None:
        # The store filters the window, so a row outside it is a caller's mistake --
        # and the series must still total the rows it was given rather than lose one.
        late = row(created_at=END + timedelta(minutes=30))
        summary = summary_of([row(), late])

        assert summary.total == 2
        assert sum(point.total for point in summary.points) == 2
        assert summary.points[-1].total == 1

    def test_the_series_covers_a_partial_last_bucket(self) -> None:
        # 90 minutes at an hourly bucket is two points, not one and a half.
        starts = bucket_starts(START, START + timedelta(minutes=90), 60)

        assert len(starts) == 2
        assert starts[1] == START + timedelta(hours=1)

    def test_an_unknown_severity_is_counted_rather_than_dropped(self) -> None:
        summary = summary_of([row(severity="high"), row(severity="apocalyptic")])

        assert summary.total == 2
        assert summary.unrecognised == 1
        assert sum(summary.by_severity.values()) + summary.unrecognised == summary.total
        # The unknown row is still in a bucket: a bucket of unknowns is not empty.
        assert sum(point.total for point in summary.points) == 2

    def test_ties_break_by_id_so_two_reads_agree(self) -> None:
        rows = [row(entity_id=9), row(entity_id=3), row(entity_id=5)]

        first = summary_of(rows).entities
        second = summary_of(list(reversed(rows))).entities

        assert [tally.entity_id for tally in first] == [3, 5, 9]
        assert [(t.entity_id, t.alerts) for t in first] == [(t.entity_id, t.alerts) for t in second]

    def test_an_entity_carries_its_worst_band_and_its_open_count(self) -> None:
        summary = summary_of(
            [
                row(entity_id=1, severity="low", score=0.4),
                row(entity_id=1, severity="critical", score=0.97),
                row(entity_id=1, severity="high", status="closed"),
            ]
        )

        tally = summary.entities[0]
        assert (tally.alerts, tally.open_alerts) == (3, 2)
        assert tally.worst_severity == "critical"
        assert tally.max_score == 0.97

    def test_an_entity_carries_the_observations_behind_its_alerts(self) -> None:
        # One alert is one incident: the correlator folds repeats into a single row
        # and keeps the count, so "3 alerts" and "3 observations" are different
        # statements and the list has to be able to make the second one.
        summary = summary_of(
            [
                row(entity_id=1, occurrences=4),
                row(entity_id=1, occurrences=2),
                row(entity_id=2, occurrences=9),
            ]
        )

        tallies = {tally.entity_id: tally for tally in summary.entities}
        assert (tallies[1].alerts, tallies[1].occurrences) == (2, 6)
        assert (tallies[2].alerts, tallies[2].occurrences) == (1, 9)
        # The tiles stay about alerts; occurrences are the entity list's detail.
        assert summary.total == 3

    def test_the_family_mix_names_the_unnamed_and_adds_up(self) -> None:
        summary = summary_of(
            [
                row(family="Reconnaissance"),
                row(family="Reconnaissance"),
                row(family="Exfiltration", severity="critical"),
                row(family="   "),
            ]
        )

        # A tie on count breaks by label, and "(" sorts before letters -- the
        # unnamed row is a label like any other, not a special case with a rank.
        assert [(f.family, f.alerts) for f in summary.families] == [
            ("Reconnaissance", 2),
            ("(unnamed)", 1),
            ("Exfiltration", 1),
        ]
        assert sum(f.alerts for f in summary.families) == summary.total
        assert summary.families[2].worst_severity == "critical"

    def test_a_tie_in_the_mix_breaks_by_family_so_two_reads_agree(self) -> None:
        rows = [row(family="Zeta"), row(family="Alpha")]
        first = summary_of(rows).families
        second = summary_of(list(reversed(rows))).families

        assert [f.family for f in first] == ["Alpha", "Zeta"]
        assert [(f.family, f.alerts) for f in first] == [(f.family, f.alerts) for f in second]

    def test_the_family_list_is_a_top_n_and_says_when_it_is_one(self) -> None:
        rows = [row(family=f"F{index}") for index in range(5)]

        summary = summary_of(rows, family_limit=2)

        assert [f.family for f in summary.families] == ["F0", "F1"]
        assert summary.families_capped is True
        # Again: a capped list, an uncapped count.
        assert summary.total == 5

    def test_the_mean_covers_only_alerts_with_a_verdict_time(self) -> None:
        # Two verdicts with times (60s and 180s) and one without: the mean covers
        # two, and the count that travels with it says so.
        summary = summary_of(
            [
                row(verdict="true_positive", verdict_at=AT + timedelta(seconds=60)),
                row(verdict="false_positive", verdict_at=AT + timedelta(seconds=180)),
                row(verdict="benign"),
                row(),
            ]
        )

        assert summary.mean_time_to_verdict_seconds == 120.0
        assert summary.verdicts_measured == 2
        assert summary.verdicts == {"true_positive": 1, "false_positive": 1, "benign": 1}
        assert summary.unrecorded == 1

    def test_a_verdict_stamped_before_its_alert_is_left_out_of_the_mean(self) -> None:
        summary = summary_of(
            [
                row(verdict="true_positive", verdict_at=AT - timedelta(seconds=30)),
                row(verdict="benign", verdict_at=AT + timedelta(seconds=100)),
            ]
        )

        # A clock that disagrees with itself is not a triage speed: the negative
        # duration is excluded rather than dragging the mean down.
        assert summary.mean_time_to_verdict_seconds == 100.0
        assert summary.verdicts_measured == 1

    def test_no_verdict_leaves_the_mean_unset_rather_than_zero(self) -> None:
        summary = summary_of([row()])

        assert summary.mean_time_to_verdict_seconds is None
        assert summary.verdicts_measured == 0

    def test_the_entity_list_is_a_top_n_and_says_when_it_is_one(self) -> None:
        rows = [row(entity_id=entity, severity="low") for entity in range(1, 6)]
        rows += [row(entity_id=6, severity="low"), row(entity_id=6, severity="low")]

        summary = summary_of(rows, entity_limit=2)

        assert [tally.entity_id for tally in summary.entities] == [6, 1]
        assert summary.entities_capped is True
        # The cap is the list's, never the counts': every row is still counted.
        assert summary.total == 7

    def test_a_list_exactly_as_long_as_the_limit_is_not_a_capped_one(self) -> None:
        # The boundary the flag is about: three entities and a limit of three is a
        # complete list, not "top 3 of more". Off by one here, and a screen tells
        # the operator there is more to see when there is not.
        rows = [row(entity_id=entity, family=f"F{entity}") for entity in range(1, 4)]

        exact = summary_of(rows, entity_limit=3, family_limit=3)
        assert exact.entities_capped is False
        assert exact.families_capped is False
        assert len(exact.entities) == 3
        assert len(exact.families) == 3

        more = summary_of(rows, entity_limit=2, family_limit=2)
        assert more.entities_capped is True
        assert more.families_capped is True
        assert len(more.entities) == 2
        assert len(more.families) == 2

    def test_the_settings_are_clamped_to_the_documented_range(self) -> None:
        summary = summary_of([row()], bucket_minutes=10_000, entity_limit=10_000)

        assert len(summary.points) == 1
        assert BUCKET_MINUTES_MAX == 1_440
        assert ENTITY_LIMIT_MAX == 50


class TestTheEndpoint:
    """The wire contract, over an app whose store the test seeds."""

    def test_one_request_answers_the_tiles_the_series_and_the_entities(
        self, client: TestClient, auth: TokenService, registry: EntityRegistry
    ) -> None:
        host = registry.id_for("host", HOST)
        seed(client, entity_id=host, severity="critical")
        seed(client, entity_id=host, severity="low")

        response = read(client, auth, bucket_minutes=30)

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {
            "window",
            "bucket_minutes",
            "totals",
            "series",
            "entities",
            "entities_capped",
            "families",
            "families_capped",
        }
        assert body["window"]["hours"] == 2.0
        assert body["bucket_minutes"] == 30
        assert len(body["series"]) == 4
        assert body["totals"]["alerts"] == 2
        assert [entity["entity_id"] for entity in body["entities"]] == [host]

    def test_counts_are_the_window_s_own_and_not_capped(
        self, client: TestClient, auth: TokenService
    ) -> None:
        # More rows than the page walk this replaces could ever read: 5,000 was its
        # cap, so 5,050 is the smallest window that tells the two apart.
        for index in range(5_050):
            seed(
                client,
                created_at=AT + timedelta(seconds=index),
                entity_id=index % 7,
                severity="high" if index % 2 == 0 else "low",
                status="open" if index % 3 == 0 else "closed",
            )

        body = read(client, auth).json()

        assert body["totals"]["alerts"] == 5_050
        assert sum(point["total"] for point in body["series"]) == 5_050
        assert body["totals"]["open"] == sum(1 for index in range(5_050) if index % 3 == 0)
        assert body["totals"]["by_severity"]["high"] == 2_525
        # Seven entities, ten asked for: the list is complete and says so. The limit
        # test below proves the cap is a cap on a list and not on a count.
        assert body["entities_capped"] is False
        assert len(body["entities"]) == 7

    def test_every_entity_renders_its_host_or_user_value(
        self, client: TestClient, auth: TokenService, registry: EntityRegistry
    ) -> None:
        host = registry.id_for("host", HOST)
        user = registry.id_for("user", USER)
        seed(client, entity_id=user, created_at=AT)
        seed(client, entity_id=host, created_at=AT + timedelta(minutes=1))
        seed(client, entity_id=host, created_at=AT + timedelta(minutes=2))

        entities = read(client, auth).json()["entities"]

        assert [(e["kind"], e["value"], e["named"]) for e in entities] == [
            ("host", HOST, True),
            ("user", USER, True),
        ]

    def test_an_id_the_registry_never_saw_is_reported_unnamed(
        self, client: TestClient, auth: TokenService
    ) -> None:
        seed(client, entity_id=4_242)

        entity = read(client, auth).json()["entities"][0]

        assert entity["entity_id"] == 4_242
        assert entity["named"] is False
        assert entity["kind"] is None
        assert entity["value"] is None
        # Unnamed is still listed with its counts: an id is a fact, it is just not
        # the fact a screen wants to print.
        assert entity["alerts"] == 1

    def test_the_tally_is_zero_filled_over_the_bands_the_column_defines(
        self, client: TestClient, auth: TokenService
    ) -> None:
        seed(client, severity="medium")

        by_severity = read(client, auth).json()["totals"]["by_severity"]

        assert by_severity == {
            "critical": 0,
            "high": 0,
            "medium": 1,
            "low": 0,
            "info": 0,
        }
        assert read(client, auth).json()["totals"]["unrecognised_severity"] == 0

    def test_entities_are_the_window_s_entities_not_the_store_s(
        self, client: TestClient, auth: TokenService
    ) -> None:
        inside = seed(client, entity_id=1, created_at=AT)
        seed(client, entity_id=2, created_at=END)  # the window is half-open

        body = read(client, auth).json()

        assert body["totals"]["alerts"] == 1
        assert [entity["entity_id"] for entity in body["entities"]] == [1]
        assert inside.entity_id == 1

    def test_the_entity_limit_changes_the_list_but_not_the_counts(
        self, client: TestClient, auth: TokenService
    ) -> None:
        for entity_id in range(1, 5):
            seed(client, entity_id=entity_id, created_at=AT + timedelta(seconds=entity_id))

        body = read(client, auth, entity_limit=2).json()

        assert len(body["entities"]) == 2
        assert body["entities_capped"] is True
        assert body["totals"]["alerts"] == 4

    def test_an_entity_carries_the_observations_the_wire_cannot_recount(
        self, client: TestClient, auth: TokenService
    ) -> None:
        # The client can count rows; it cannot know that the correlator folded four
        # observations into one of them. So the sum is the server's to report.
        seed(client, entity_id=1, occurrences=4, created_at=AT)
        seed(client, entity_id=1, occurrences=6, created_at=AT + timedelta(seconds=1))
        seed(client, entity_id=2, occurrences=2, created_at=AT + timedelta(seconds=2))

        body = read(client, auth).json()

        first = next(entity for entity in body["entities"] if entity["entity_id"] == 1)
        assert (first["alerts"], first["occurrences"]) == (2, 10)
        # The window's alerts are still alerts: 3 rows, not 12 observations.
        assert body["totals"]["alerts"] == 3

    def test_the_mix_reaches_the_wire_with_its_unnamed_row(
        self, client: TestClient, auth: TokenService
    ) -> None:
        seed(client, entity_id=1, family="Lateral movement", created_at=AT)
        seed(client, entity_id=1, family="Lateral movement", created_at=AT + timedelta(seconds=1))
        seed(client, entity_id=2, family=" ", created_at=AT + timedelta(seconds=2))

        body = read(client, auth).json()

        assert [(f["family"], f["alerts"]) for f in body["families"]] == [
            ("Lateral movement", 2),
            ("(unnamed)", 1),
        ]
        assert body["families_capped"] is False
        assert sum(f["alerts"] for f in body["families"]) == body["totals"]["alerts"]

    def test_the_family_limit_changes_the_mix_but_not_the_counts(
        self, client: TestClient, auth: TokenService
    ) -> None:
        for index in range(4):
            seed(
                client,
                entity_id=1,
                family=f"Family {index}",
                created_at=AT + timedelta(seconds=index),
            )

        body = read(client, auth, family_limit=2).json()

        assert len(body["families"]) == 2
        assert body["families_capped"] is True
        assert body["totals"]["alerts"] == 4

    def test_a_window_that_is_naive_or_inverted_is_a_client_error(
        self, client: TestClient, auth: TokenService
    ) -> None:
        naive = read(client, auth, start=datetime(2026, 3, 15, 9, 0, 0))
        inverted = read(client, auth, start=END, end=START)

        assert naive.status_code == 400
        assert "timezone-aware" in naive.json()["detail"]
        assert inverted.status_code == 400
        assert "precede" in inverted.json()["detail"]

    def test_a_window_wider_than_the_scan_limit_is_refused(
        self, client: TestClient, auth: TokenService
    ) -> None:
        response = read(client, auth, start=START, end=START + timedelta(days=120))

        # R-34: an aggregate is a query like any other, and a range that wide is
        # the unbounded scan with a predicate attached.
        assert response.status_code == 400
        assert "day" in response.json()["detail"]

    def test_the_window_bounds_are_required(self, client: TestClient, auth: TokenService) -> None:
        response = client.get("/api/v1/overview", headers=headers(auth))

        assert response.status_code == 422

    def test_a_malformed_resolution_or_limit_is_refused(
        self, client: TestClient, auth: TokenService
    ) -> None:
        assert read(client, auth, bucket_minutes=0).status_code == 422
        assert read(client, auth, bucket_minutes=BUCKET_MINUTES_MAX + 1).status_code == 422
        assert read(client, auth, entity_limit=0).status_code == 422
        assert read(client, auth, entity_limit=ENTITY_LIMIT_MAX + 1).status_code == 422
        assert read(client, auth, family_limit=0).status_code == 422
        assert read(client, auth, family_limit=FAMILY_LIMIT_MAX + 1).status_code == 422

    def test_every_role_that_may_read_an_alert_may_read_the_window(
        self, client: TestClient, auth: TokenService
    ) -> None:
        for role in Role:
            response = read(client, auth, role=role)
            assert response.status_code == 200, (role, response.text)

    def test_an_anonymous_caller_is_refused(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/overview", params={"start": START.isoformat(), "end": END.isoformat()}
        )

        assert response.status_code == 401

    def test_an_empty_window_answers_with_zeroes_rather_than_nothing(
        self, client: TestClient, auth: TokenService
    ) -> None:
        body = read(client, auth).json()

        assert body["totals"]["alerts"] == 0
        assert body["totals"]["mean_time_to_verdict_seconds"] is None
        assert body["entities"] == []
        assert sum(point["total"] for point in body["series"]) == 0


class TestTheSql:
    """The statements a persistent adapter would run (T-416, R-34)."""

    def statements(self) -> dict[str, str]:
        window = TimeRange(start=START, end=END)
        built = alert_aggregate_statements(
            window, bucket_seconds=3_600, entity_limit=10, family_limit=8
        )
        return {
            "totals": str(built.totals.compile()),
            "series": str(built.series.compile()),
            "entities": str(built.entities.compile()),
            "families": str(built.families.compile()),
        }

    def test_none_of_the_statements_is_an_unbounded_scan(self) -> None:
        window = TimeRange(start=START, end=END)
        built = alert_aggregate_statements(
            window, bucket_seconds=3_600, entity_limit=10, family_limit=8
        )

        for statement in (built.totals, built.series, built.entities, built.families):
            assert "created_at" in str(statement.compile())

    def test_only_the_entity_list_is_capped(self) -> None:
        sql = self.statements()

        # A count capped by a LIMIT is the 5,000-row problem again; the top-N list
        # is the one place a cap is the answer rather than a lie.
        assert "LIMIT" not in sql["totals"]
        assert "LIMIT :param_1" not in sql["series"]
        assert "LIMIT" in sql["entities"]
        assert "LIMIT" in sql["families"]

    def test_the_statements_group_and_join_what_they_claim(self) -> None:
        sql = self.statements()

        assert "GROUP BY alerts.severity" in sql["totals"]
        assert "GROUP BY" in sql["series"]
        assert "floor" in sql["series"]
        assert "LEFT OUTER JOIN entities" in sql["entities"]
        assert "entities.kind" in sql["entities"]
        assert "entities.value" in sql["entities"]
        # The observations travel with the entity, summed where the rows are.
        assert "sum(alerts.occurrence_count)" in sql["entities"]
        assert "GROUP BY alerts.family" in sql["families"]
        assert "ORDER BY count(*) DESC" in sql["families"]

    def test_the_builder_refuses_a_setting_that_cannot_be_satisfied(self) -> None:
        window = TimeRange(start=START, end=END)

        with pytest.raises(ValueError, match="bucket_seconds"):
            alert_aggregate_statements(window, bucket_seconds=0, entity_limit=10, family_limit=8)
        with pytest.raises(ValueError, match="entity_limit"):
            alert_aggregate_statements(window, bucket_seconds=60, entity_limit=0, family_limit=8)
        with pytest.raises(ValueError, match="family_limit"):
            alert_aggregate_statements(window, bucket_seconds=60, entity_limit=10, family_limit=0)
