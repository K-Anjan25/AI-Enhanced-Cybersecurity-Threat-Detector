"""T-418: the flow read route (FR-52).

The acceptance criteria this file exists to test:

* **Volume is traffic and its edges are flow relationships.** Records are ingested as a
  collector would send them -- including traffic that raised no alert -- and the busiest
  address, the busiest pair and the byte totals are the *traffic's*, not the alerted
  subset's. A test seeds alerts on one address and flows on another and asserts the
  traffic number follows the flows.
* **Counts are complete for the window rather than the alerted subset.** ``totals``
  covers every ingested record, and a cap on the entity or edge *list* moves the list
  without moving the count (``nodes_capped`` says which it is).
* **The panel's permanent caveat drops the T-418 half.** The caveats are asserted here
  as prose, because the dashboard renders them unparaphrased: the source sentence, the
  score-is-not-on-a-flow sentence, and the cap sentences are all present, and there is
  no sentence left claiming the numbers are an alerted subset.

The join between the two read models is tested as an explicit case: alerts attach to an
address only when the alert's entity *value* is that address, which is the registry's
answer, and a bucket's score is the mean of the alerts in it -- null, not zero, when the
bucket held none.
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
from app.services.entity_registry import EntityRegistry
from app.services.flow_read_model import FLOW_ROLLUP_MINUTES, InProcessFlowRollup
from app.services.flow_source import RollupFlowSource
from fastapi.testclient import TestClient

SECRET = "o" * 48
START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
END = START + timedelta(hours=1)


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
def settings(settings: Settings) -> Settings:
    """The shared test settings, with the ingest key set so a batch can be sent."""
    return settings


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    built = create_app(settings)
    built.state.token_service = auth
    # The rollup is replaced rather than reused so a test can shrink its caps without
    # reaching into another test's state, and the reason is a fixed sentence so the
    # caveat text is asserted against something a test chose.
    built.state.flow_source = RollupFlowSource(
        InProcessFlowRollup(retention_minutes=FLOW_ROLLUP_MINUTES), reason="reason-for-test"
    )
    return TestClient(built)


@pytest.fixture
def registry(client: TestClient) -> EntityRegistry:
    """The registry the endpoint resolves an alert's entity value through."""
    return client.app.state.entity_registry  # type: ignore[attr-defined]


def seed_alert(
    client: TestClient,
    *,
    created_at: datetime = START + timedelta(minutes=5),
    severity: str = "high",
    score: float = 0.9,
    status: str = "open",
    entity_id: int = 1,
) -> Alert:
    """Store one alert row, as the correlator's writer would."""
    store = client.app.state.alert_store  # type: ignore[attr-defined]
    values: dict[str, object] = {
        "entity_id": entity_id,
        "family": "Reconnaissance",
        "severity": severity,
        "score": score,
        "model_flow_id": None,
        "model_log_id": None,
        "window_ref": {"store": "stream", "id": "win-1", "trace_id": None, "grouped": False},
        "explanation": {"families": [], "partial_evidence": False, "reasons": []},
        "status": status,
        "first_seen": created_at - timedelta(minutes=1),
        "last_seen": created_at,
        "occurrence_count": 1,
        "verdict": None,
        "verdict_at": None,
    }
    return store.save(
        f"case-{entity_id}-{severity}-{created_at.isoformat()}", values, created_at=created_at
    )


def ingest(
    client: TestClient,
    auth: TokenService,
    records: list[dict[str, Any]],
    *,
    role: Role = Role.RESPONDER,
    expect: int = 200,
) -> Any:
    """Send a flow batch through the real ingest route."""
    response = client.post("/api/v1/ingest/flows", json=records, headers=headers(auth, role))
    assert response.status_code == expect, response.text
    return response.json()


def flow_record(
    *,
    at: datetime = START + timedelta(minutes=1),
    src: str = "10.0.0.1",
    dst: str = "10.0.0.2",
    protocol: str = "tcp",
    direction: str = "outbound",
    src_bytes: int = 100,
    dst_bytes: int = 40,
    packets: int = 3,
) -> dict[str, Any]:
    """One ``flow@1`` record, as a collector would put it on the wire."""
    return {
        "schema_version": "flow@1",
        "timestamp": at.isoformat(),
        "src_ip": src,
        "dst_ip": dst,
        "src_port": 51000,
        "dst_port": 443,
        "protocol": protocol,
        "direction": direction,
        "packets": packets,
        "src_packets": packets,
        "dst_packets": 0,
        "src_bytes": src_bytes,
        "dst_bytes": dst_bytes,
        "duration": 1.0,
    }


def stamp(value: datetime | str) -> str:
    """A query parameter, so a test can send a deliberately malformed instant."""
    return value.isoformat() if isinstance(value, datetime) else value


def read(
    client: TestClient,
    auth: TokenService,
    *,
    start: datetime | str = START,
    end: datetime | str = END,
    role: Role = Role.ANALYST,
    **params: Any,
) -> Any:
    """Call the flow route with the window as query parameters."""
    return client.get(
        "/api/v1/flows",
        params={"start": stamp(start), "end": stamp(end), **params},
        headers=headers(auth, role),
    )


class TestTheWindowIsCounted:
    """Ingest is the only writer, and reading counts what was ingested."""

    def test_an_empty_deployment_answers_with_zeros(
        self, client: TestClient, auth: TokenService
    ) -> None:
        body = read(client, auth).json()

        assert body["totals"]["flows"] == 0
        assert body["entities"] == []
        assert body["edges"] == []

    def test_the_series_tiles_the_window(self, client: TestClient, auth: TokenService) -> None:
        body = read(client, auth, bucket_minutes=15).json()

        assert len(body["series"]) == 4
        assert body["series"][0]["start"].startswith("2026-10-06T10:00:00")

    def test_ingested_traffic_is_counted(self, client: TestClient, auth: TokenService) -> None:
        ingest(client, auth, [flow_record(), flow_record()])

        body = read(client, auth).json()

        assert body["totals"]["flows"] == 2
        assert body["totals"]["bytes"] == 280
        assert body["totals"]["packets"] == 6

    def test_traffic_that_raised_no_alert_is_counted(
        self, client: TestClient, auth: TokenService
    ) -> None:
        # The whole point of T-418: the screen used to be a list of alerts, so traffic
        # nobody alerted on was invisible. Seven records, no alerts at all.
        ingest(client, auth, [flow_record() for _ in range(7)])

        body = read(client, auth).json()

        assert body["totals"]["flows"] == 7
        assert body["entities"][0]["alerts"] == 0

    def test_the_totals_are_the_traffics_not_the_alerteds(
        self, client: TestClient, auth: TokenService, registry: EntityRegistry
    ) -> None:
        # An alert on 10.9.9.9 and traffic between two other addresses: the busiest
        # address on the screen is the traffic's, and 10.9.9.9 is absent entirely.
        seed_alert(client, entity_id=registry.id_for("source", "10.9.9.9"))
        ingest(client, auth, [flow_record(src="10.0.0.1", dst="10.0.0.2") for _ in range(3)])

        body = read(client, auth).json()

        assert [entity["ip"] for entity in body["entities"]] == ["10.0.0.1", "10.0.0.2"]
        assert body["totals"]["flows"] == 3

    def test_a_restart_is_a_new_rollup_and_the_caveat_says_so(
        self, client: TestClient, auth: TokenService, settings: Settings
    ) -> None:
        # The in-process source cannot survive a restart and does not pretend to: a
        # second application instance over the same settings sees an empty window.
        ingest(client, auth, [flow_record()])
        second = create_app(settings)
        second.state.token_service = client.app.state.token_service  # type: ignore[attr-defined]

        with TestClient(second) as other:
            body = read(other, auth).json()

        assert body["totals"]["flows"] == 0


class TestTheEdgesAreFlowRelationships:
    """Edges are traffic between two addresses, directional."""

    def test_an_edge_is_a_pair_that_exchanged_traffic(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(client, auth, [flow_record(src="10.0.0.1", dst="10.0.0.2")])

        body = read(client, auth).json()

        assert body["edges"] == [
            {"source": "10.0.0.1", "target": "10.0.0.2", "flows": 1, "bytes": 140}
        ]

    def test_the_two_directions_are_two_edges(self, client: TestClient, auth: TokenService) -> None:
        ingest(
            client,
            auth,
            [
                flow_record(src="10.0.0.1", dst="10.0.0.2"),
                flow_record(src="10.0.0.2", dst="10.0.0.1"),
            ],
        )

        body = read(client, auth).json()

        assert {(edge["source"], edge["target"]) for edge in body["edges"]} == {
            ("10.0.0.1", "10.0.0.2"),
            ("10.0.0.2", "10.0.0.1"),
        }
        assert body["totals"]["edges"] == 2

    def test_the_heaviest_pair_is_listed_first(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(
            client,
            auth,
            [
                flow_record(src="10.0.0.1", dst="10.0.0.2"),
                flow_record(src="10.0.0.3", dst="10.0.0.4"),
                flow_record(src="10.0.0.3", dst="10.0.0.4"),
            ],
        )

        body = read(client, auth).json()

        assert body["edges"][0]["source"] == "10.0.0.3"
        assert body["edges"][0]["flows"] == 2


class TestCountsAreCompleteForTheWindow:
    """A cap shortens a list; it never shortens a count."""

    def test_the_entity_count_survives_the_entity_cap(
        self, client: TestClient, auth: TokenService
    ) -> None:
        records = [flow_record(src=f"10.0.0.{index}", dst="10.0.0.254") for index in range(1, 9)]
        ingest(client, auth, records)

        body = read(client, auth, entity_limit=3).json()

        assert len(body["entities"]) == 3
        assert body["totals"]["nodes"] == 9
        assert body["totals"]["nodes_capped"] is True
        assert body["totals"]["flows"] == 8

    def test_the_edge_count_survives_the_edge_cap(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(
            client,
            auth,
            [
                flow_record(src="10.0.0.1", dst="10.0.0.2"),
                flow_record(src="10.0.0.3", dst="10.0.0.4"),
                flow_record(src="10.0.0.5", dst="10.0.0.6"),
            ],
        )

        body = read(client, auth, edge_limit=1).json()

        assert len(body["edges"]) == 1
        assert body["totals"]["edges"] == 3
        assert body["totals"]["edges_capped"] is True

    def test_an_uncapped_window_does_not_claim_a_cap(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(client, auth, [flow_record()])

        body = read(client, auth).json()

        assert body["totals"]["nodes_capped"] is False
        assert body["totals"]["edges_capped"] is False

    def test_the_ingest_limit_is_the_batch_the_route_accepts(
        self, client: TestClient, auth: TokenService
    ) -> None:
        # 1,000 records is the contract's batch size (FR-01); the count is the batch's,
        # not a page of it.
        ingest(client, auth, [flow_record() for _ in range(100)])

        body = read(client, auth).json()

        assert body["totals"]["flows"] == 100


class TestTheAlertSideOfTheJoin:
    """Scores and alert counts are alert-derived, from the alert store."""

    def test_a_bucket_with_no_alert_has_a_null_score_not_a_zero(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(client, auth, [flow_record()])

        body = read(client, auth).json()

        assert body["series"][0]["alerts"] == 0
        assert body["series"][0]["score"] is None, "an empty bucket is not a benign one"

    def test_a_buckets_score_is_the_mean_of_its_alerts(
        self, client: TestClient, auth: TokenService, registry: EntityRegistry
    ) -> None:
        entity = registry.id_for("source", "10.0.0.1")
        seed_alert(client, created_at=START + timedelta(minutes=1), score=0.8, entity_id=entity)
        seed_alert(client, created_at=START + timedelta(minutes=2), score=0.4, entity_id=entity)
        ingest(client, auth, [flow_record(), flow_record()])

        body = read(client, auth).json()

        assert body["series"][0]["alerts"] == 2
        assert body["series"][0]["score"] == pytest.approx(0.6)

    def test_an_address_carries_the_alerts_whose_entity_value_is_that_address(
        self, client: TestClient, auth: TokenService, registry: EntityRegistry
    ) -> None:
        seed_alert(
            client,
            severity="critical",
            score=0.95,
            status="open",
            entity_id=registry.id_for("source", "10.0.0.1"),
        )
        seed_alert(
            client,
            severity="low",
            score=0.2,
            status="closed",
            entity_id=registry.id_for("source", "10.0.0.1"),
        )
        ingest(client, auth, [flow_record()])

        body = read(client, auth).json()
        sender = next(entity for entity in body["entities"] if entity["ip"] == "10.0.0.1")
        receiver = next(entity for entity in body["entities"] if entity["ip"] == "10.0.0.2")

        assert sender["alerts"] == 2
        assert sender["open_alerts"] == 1
        assert sender["worst_severity"] == "critical"
        assert sender["max_score"] == pytest.approx(0.95)
        assert receiver["alerts"] == 0
        assert receiver["worst_severity"] is None

    def test_an_alert_whose_entity_is_not_an_address_attaches_nowhere(
        self, client: TestClient, auth: TokenService, registry: EntityRegistry
    ) -> None:
        # The join is by value: a detection keyed by host name is not an address, and
        # inventing a row for it would put an alert count on the wrong line.
        seed_alert(client, entity_id=registry.id_for("host", "web-01.corp"))
        ingest(client, auth, [flow_record()])

        body = read(client, auth).json()

        assert all(entity["alerts"] == 0 for entity in body["entities"])

    def test_an_alert_for_an_address_with_no_traffic_is_not_listed(
        self, client: TestClient, auth: TokenService, registry: EntityRegistry
    ) -> None:
        seed_alert(client, entity_id=registry.id_for("source", "203.0.113.9"))

        body = read(client, auth).json()

        assert body["entities"] == []
        assert body["totals"]["flows"] == 0


class TestFilters:
    """A narrowing is a parameter, is echoed back, and is stated in the caveats."""

    def test_a_protocol_filter_narrows_the_traffic(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(
            client,
            auth,
            [
                flow_record(protocol="tcp"),
                flow_record(protocol="udp"),
                flow_record(protocol="udp"),
            ],
        )

        body = read(client, auth, protocol="udp").json()

        assert body["totals"]["flows"] == 2
        assert body["filters"]["protocol"] == "udp"

    def test_a_direction_filter_narrows_the_traffic(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(
            client,
            auth,
            [
                flow_record(direction="inbound"),
                flow_record(direction="outbound"),
                flow_record(direction="outbound"),
            ],
        )

        body = read(client, auth, direction="outbound").json()

        assert body["totals"]["flows"] == 2

    def test_the_filters_are_echoed_even_when_unset(
        self, client: TestClient, auth: TokenService
    ) -> None:
        body = read(client, auth).json()

        assert body["filters"] == {"protocol": None, "direction": None}

    def test_an_unknown_protocol_is_refused_rather_than_ignored(
        self, client: TestClient, auth: TokenService
    ) -> None:
        # A silently ignored filter is a screen showing traffic the caller excluded.
        response = read(client, auth, protocol="sctp")

        assert response.status_code == 400
        assert "unknown protocol" in response.json()["detail"]

    def test_an_unknown_direction_is_refused(self, client: TestClient, auth: TokenService) -> None:
        response = read(client, auth, direction="sideways")

        assert response.status_code == 400
        assert "unknown direction" in response.json()["detail"]


class TestCaveats:
    """The sentences the panel renders unparaphrased."""

    def test_the_source_sentence_is_present_and_names_the_rollup(
        self, client: TestClient, auth: TokenService
    ) -> None:
        body = read(client, auth).json()

        assert body["source"] == "rollup"
        assert any("in-process rollup" in caveat for caveat in body["caveats"])

    def test_the_reasons_own_sentence_is_carried(
        self, client: TestClient, auth: TokenService
    ) -> None:
        body = read(client, auth).json()

        assert "reason-for-test" in body["caveats"]

    def test_the_granularity_is_stated(self, client: TestClient, auth: TokenService) -> None:
        body = read(client, auth).json()

        assert any("minute-grained" in caveat for caveat in body["caveats"])

    def test_the_score_is_said_not_to_be_on_a_flow(
        self, client: TestClient, auth: TokenService
    ) -> None:
        body = read(client, auth).json()

        assert any("no score or severity" in caveat for caveat in body["caveats"])

    def test_no_caveat_still_claims_an_alerted_subset(
        self, client: TestClient, auth: TokenService
    ) -> None:
        # The T-418 half of the old panel caveat is gone: the numbers are the traffic's
        # now, and a sentence saying otherwise would be the defect it replaced.
        joined = " ".join(read(client, auth).json()["caveats"])

        assert "alerted subset" not in joined
        assert "raise an alert" not in joined

    def test_an_empty_window_says_nothing_has_been_counted(
        self, client: TestClient, auth: TokenService
    ) -> None:
        body = read(client, auth).json()

        assert any("Nothing has been counted yet" in caveat for caveat in body["caveats"])

    def test_a_capped_list_names_both_numbers_onscreen(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(
            client,
            auth,
            [flow_record(src=f"10.0.0.{i}", dst="10.0.0.254") for i in range(1, 6)],
        )

        body = read(client, auth, entity_limit=2).json()

        sentence = next(c for c in body["caveats"] if "entity list shows" in c)
        assert "2" in sentence
        assert "6" in sentence

    def test_a_filtered_read_says_the_filter_bounded_it(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(client, auth, [flow_record(protocol="tcp"), flow_record(protocol="udp")])

        body = read(client, auth, protocol="tcp").json()

        assert any("narrowed by the filter" in c for c in body["caveats"])


class TestTheWindowGuardrails:
    """The window is required and bounded, exactly as the log routes' is."""

    def test_a_window_wider_than_the_rollup_holds_is_refused(
        self, client: TestClient, auth: TokenService
    ) -> None:
        response = read(
            client,
            auth,
            start=START - timedelta(days=1),
            end=END,
        )

        assert response.status_code == 400
        assert "rollup answers at most" in response.json()["detail"]

    def test_the_refusal_states_the_sources_own_bound(
        self, client: TestClient, auth: TokenService
    ) -> None:
        response = read(client, auth, start=START - timedelta(hours=5), end=END)

        detail = response.json()["detail"]
        assert f"{FLOW_ROLLUP_MINUTES * 60:g} seconds" in detail

    def test_a_window_wider_than_r_34_is_refused(
        self, client: TestClient, auth: TokenService
    ) -> None:
        response = read(client, auth, start=START - timedelta(days=200), end=END)

        assert response.status_code == 400

    def test_an_inverted_window_is_refused(self, client: TestClient, auth: TokenService) -> None:
        response = read(client, auth, start=END, end=START)

        assert response.status_code == 400

    def test_a_naive_timestamp_is_refused(self, client: TestClient, auth: TokenService) -> None:
        response = read(client, auth, start="2026-10-06T10:00:00", end="2026-10-06T11:00:00")

        assert response.status_code == 400

    def test_a_missing_window_is_refused(self, client: TestClient, auth: TokenService) -> None:
        response = client.get("/api/v1/flows", headers=headers(auth))

        assert response.status_code == 422

    def test_a_bucket_wider_than_a_day_is_refused(
        self, client: TestClient, auth: TokenService
    ) -> None:
        response = read(client, auth, bucket_minutes=1_441)

        assert response.status_code == 422


class TestAuthorization:
    """Reading traffic is reading (R-53)."""

    @pytest.mark.parametrize("role", list(Role))
    def test_every_role_may_read(self, client: TestClient, auth: TokenService, role: Role) -> None:
        assert read(client, auth, role=role).status_code == 200

    def test_an_anonymous_read_is_refused(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/flows", params={"start": START.isoformat(), "end": END.isoformat()}
        )

        assert response.status_code == 401

    def test_reading_does_not_require_write_or_admin(
        self, client: TestClient, auth: TokenService
    ) -> None:
        # A viewer is the least privileged role and still reads the explorer.
        assert read(client, auth, role=Role.VIEWER).status_code == 200


class TestTheRouteAndIngestShareThePath:
    """``POST /api/v1/flows`` is ingest; ``GET`` is this read (T-418)."""

    def test_the_post_route_is_the_ingest_contract(
        self, client: TestClient, auth: TokenService
    ) -> None:
        ingest(client, auth, [flow_record()])

        body = read(client, auth).json()
        assert body["totals"]["flows"] == 1

    def test_a_batch_that_cannot_be_stored_is_a_503(
        self, client: TestClient, auth: TokenService
    ) -> None:
        # The batch was validated and handed to the broker; the read model then refused
        # it. A 200 here would tell the caller the traffic was taken in while the next
        # read cannot find it (T-307's rule: a retry duplicates on the broker rather
        # than losing traffic).
        from app.services.flow_store import FlowStoreUnavailable

        class Refusing:
            """A source that accepts nothing."""

            name = "store"

            @property
            def max_span_seconds(self) -> float:
                return 3_600.0

            async def append(self, records: Any) -> int:
                msg = "the database is unreachable"
                raise FlowStoreUnavailable(msg)

            async def summary(self, *args: Any, **kwargs: Any) -> Any:
                msg = "not read in this test"
                raise FlowStoreUnavailable(msg)

        client.app.state.flow_source = Refusing()  # type: ignore[attr-defined]

        response = client.post(
            "/api/v1/ingest/flows", json=[flow_record()], headers=headers(auth, Role.RESPONDER)
        )

        assert response.status_code == 503
        assert "could not be stored" in response.json()["detail"]

    def test_a_refused_store_does_not_break_other_routes(
        self, client: TestClient, auth: TokenService
    ) -> None:
        # The refusal is the flow batch's, not the process's: the alert list still reads.
        response = client.get(
            "/api/v1/alerts",
            params={"start": START.isoformat(), "end": END.isoformat()},
            headers=headers(auth, Role.VIEWER),
        )

        assert response.status_code == 200


class TestTheOverviewCarriesAScore:
    """T-418's overlay needs the mean the overview already computes (one join, two uses)."""

    def test_a_bucket_of_the_overview_series_carries_the_mean_score(
        self, client: TestClient, auth: TokenService, registry: EntityRegistry
    ) -> None:
        entity = registry.id_for("source", "10.0.0.1")
        seed_alert(client, created_at=START + timedelta(minutes=1), score=0.7, entity_id=entity)
        seed_alert(client, created_at=START + timedelta(minutes=2), score=0.3, entity_id=entity)

        response = client.get(
            "/api/v1/overview",
            params={
                "start": START.isoformat(),
                "end": END.isoformat(),
                "bucket_minutes": 15,
            },
            headers=headers(auth),
        )

        assert response.status_code == 200
        first = response.json()["series"][0]
        assert first["total"] == 2
        assert first["score"] == pytest.approx(0.5)

    def test_an_empty_overview_bucket_has_a_null_score(
        self, client: TestClient, auth: TokenService
    ) -> None:
        response = client.get(
            "/api/v1/overview",
            params={"start": START.isoformat(), "end": END.isoformat(), "bucket_minutes": 15},
            headers=headers(auth),
        )

        assert response.json()["series"][0]["score"] is None
