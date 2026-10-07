"""The flow source's sentences (T-418).

The caveats are part of the endpoint's contract: the dashboard renders them unparaphrased
(the T-419 rule), so a sentence asserted here is a sentence a reader sees. Three kinds are
tested:

* **The source's own sentence is always there**, and it differs by source: "survives a
  restart" and "this process's memory" are claims a reader has to have to read the same
  number two ways.
* **Why this source**, from ``flow_rollup_reason`` -- two distinct sentences for the two
  ways a deployment ends up on the rollup, because "you turned it off" and "you never
  configured a database" call for different actions.
* **What this particular read could not do**: an empty window explained by its own cause
  (nothing ingested vs. nothing held that old vs. nothing matched), the filter named when
  one narrowed the numbers, and each cap naming both numbers it stood between.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import LogStoreMode
from app.services.flow_read_model import (
    FLOW_ROLLUP_MINUTES,
    FlowFilters,
    FlowTotals,
    FlowWindow,
    InProcessFlowRollup,
)
from app.services.flow_source import RollupFlowSource, flow_caveats, flow_rollup_reason

START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
WINDOW = FlowWindow(start=START, end=START + timedelta(hours=1))


def totals(**overrides: object) -> FlowTotals:
    """A non-empty window's counts, with whatever a case needs changed."""
    values: dict[str, object] = {
        "flows": 1,
        "bytes": 140,
        "packets": 3,
        "nodes": 2,
        "edges": 1,
        "nodes_capped": False,
        "edges_capped": False,
        "untracked_address_flows": 0,
        "untracked_pair_flows": 0,
    }
    values.update(overrides)
    return FlowTotals(**values)  # type: ignore[arg-type]


def caveats(**overrides: object) -> list[str]:
    """The caveats for one read, with the arguments a case does not care about defaulted."""
    kwargs: dict[str, object] = {
        "source_name": "store",
        "window": WINDOW,
        "totals": totals(),
        "listed_nodes": 1,
        "listed_edges": 1,
    }
    kwargs.update(overrides)
    return flow_caveats(**kwargs)  # type: ignore[arg-type]


class TestTheSourcesOwnSentence:
    """Which source answered is on the screen, in words."""

    def test_a_store_read_says_it_survives_a_restart(self) -> None:
        first = caveats(source_name="store")[0]

        assert "flow store" in first
        assert "survive a restart" in first

    def test_a_store_read_does_not_claim_to_be_a_rollup(self) -> None:
        assert "in-process rollup" not in caveats(source_name="store")[0]

    def test_a_rollup_read_says_it_is_memory(self) -> None:
        first = caveats(source_name="rollup")[0]

        assert "in-process rollup" in first
        assert f"last {FLOW_ROLLUP_MINUTES} minutes" in first
        assert "not a store" in first

    def test_a_rollup_read_says_its_granularity_out_loud(self) -> None:
        # The price of the rollup is that a window edges inside a minute: the sentence
        # has to be on the screen or the totals are a number nobody can interpret.
        sentences = caveats(source_name="rollup")

        assert any("minute-grained" in sentence for sentence in sentences)

    def test_only_a_rollup_read_carries_the_rollup_sentences(self) -> None:
        store_read = " ".join(caveats(source_name="store"))

        assert "minute-grained" not in store_read

    def test_the_reason_is_carried_when_one_is_given(self) -> None:
        sentences = caveats(source_name="rollup", reason="because AEGIS_FLOW_STORE is off")

        assert "because AEGIS_FLOW_STORE is off" in sentences

    def test_a_store_read_ignores_a_reason(self) -> None:
        # A store has nothing to explain, and a stray sentence about why a rollup was
        # answering would be a lie on a screen that is not reading one.
        assert "why" not in " ".join(caveats(source_name="store", reason="why"))


class TestTheScoreSentence:
    """The join is by address, and a reader cannot see that from the numbers."""

    def test_it_is_on_every_read(self) -> None:
        for source in ("store", "rollup"):
            assert any(
                "no score or severity" in sentence for sentence in caveats(source_name=source)
            )

    def test_it_names_the_join_key(self) -> None:
        sentence = next(s for s in caveats() if "no score or severity" in s)

        assert "entity value" in sentence
        assert "source address" in sentence


class TestWhyTheWindowIsEmpty:
    """An empty window says which emptiness it is."""

    def test_nothing_ever_counted_says_so(self) -> None:
        sentences = caveats(source_name="rollup", totals=totals(flows=0), retained_from=None)

        assert any("Nothing has been counted yet" in sentence for sentence in sentences)

    def test_a_known_empty_store_says_so(self) -> None:
        sentences = caveats(totals=totals(flows=0), stored_ever=False)

        assert any("Nothing has been counted yet" in sentence for sentence in sentences)

    def test_a_window_older_than_what_is_held_names_both_instants(self) -> None:
        held_from = START + timedelta(hours=3)
        sentences = caveats(
            source_name="rollup",
            totals=totals(flows=0),
            retained_from=held_from,
            window=FlowWindow(start=START, end=START + timedelta(hours=1)),
        )

        sentence = next(s for s in sentences if "No flow is held at or before" in s)
        assert (START + timedelta(hours=1)).isoformat() in sentence
        assert held_from.isoformat() in sentence

    def test_a_window_inside_what_is_held_and_still_empty_says_nothing_matched(self) -> None:
        sentences = caveats(
            source_name="rollup",
            totals=totals(flows=0),
            retained_from=START - timedelta(hours=1),
        )

        assert any("No accepted flow record falls inside this window" in s for s in sentences)

    def test_a_non_empty_window_is_not_given_a_why_empty_sentence(self) -> None:
        sentences = caveats()

        assert not any("this window is empty" in s for s in sentences)


class TestTheFilterAndCapSentences:
    """A number that was narrowed says what narrowed it; a list that was capped says so."""

    def test_a_filtered_read_names_the_filter(self) -> None:
        sentences = caveats(filters=FlowFilters(protocol="tcp"))

        assert any("narrowed by the filter" in sentence for sentence in sentences)

    def test_an_unfiltered_read_does_not(self) -> None:
        assert not any("narrowed by the filter" in s for s in caveats())

    def test_a_capped_entity_list_names_both_numbers(self) -> None:
        sentences = caveats(
            totals=totals(nodes=40, nodes_capped=True),
            listed_nodes=25,
        )

        sentence = next(s for s in sentences if "entity list shows" in s)
        assert "25" in sentence
        assert "40" in sentence

    def test_a_capped_edge_list_names_both_numbers(self) -> None:
        sentences = caveats(
            totals=totals(edges=900, edges_capped=True),
            listed_edges=200,
        )

        sentence = next(s for s in sentences if "edge list shows" in s)
        assert "200" in sentence
        assert "900" in sentence

    def test_an_untracked_address_breakdown_is_stated_as_a_partial(self) -> None:
        sentences = caveats(totals=totals(untracked_address_flows=7))

        sentence = next(s for s in sentences if "not attributed to an address" in s)
        assert "7" in sentence
        assert "the totals are not" in sentence

    def test_an_untracked_pair_breakdown_is_stated_as_a_partial(self) -> None:
        sentences = caveats(totals=totals(untracked_pair_flows=2))

        assert any("not attributed to a pair" in s for s in sentences)

    def test_a_complete_read_says_nothing_about_partials(self) -> None:
        joined = " ".join(caveats())

        assert "partial" not in joined
        assert "shows the busiest" not in joined


class TestTheReasons:
    """Why a rollup is answering, in the deployment's own terms."""

    def test_the_off_mode_says_it_can_be_turned_on(self) -> None:
        sentence = flow_rollup_reason(LogStoreMode.OFF)

        assert "AEGIS_FLOW_STORE is off" in sentence
        assert "AEGIS_FLOW_STORE=on" in sentence

    def test_the_auto_mode_says_a_database_was_never_named(self) -> None:
        sentence = flow_rollup_reason(LogStoreMode.AUTO)

        assert "no database URL is named" in sentence
        assert "AEGIS_DATABASE_URL" in sentence
        assert "alembic upgrade head" in sentence

    def test_the_two_reasons_are_different_sentences(self) -> None:
        assert flow_rollup_reason(LogStoreMode.OFF) != flow_rollup_reason(LogStoreMode.AUTO)

    def test_every_reason_is_a_sentence(self) -> None:
        for mode in LogStoreMode:
            sentence = flow_rollup_reason(mode)
            assert sentence.endswith(".")


class TestTheRollupSource:
    """The wrapper the composition root installs."""

    def test_it_names_itself_rollup(self) -> None:
        source = RollupFlowSource(InProcessFlowRollup(), reason="why")

        assert source.name == "rollup"

    def test_its_widest_window_is_its_own_retention(self) -> None:
        source = RollupFlowSource(InProcessFlowRollup(retention_minutes=30), reason="why")

        assert source.max_span_seconds == 1_800.0

    def test_it_carries_the_reason_it_was_given(self) -> None:
        source = RollupFlowSource(InProcessFlowRollup(), reason="because there is no store")

        assert source.reason == "because there is no store"

    def test_appending_counts_into_the_rollup(self) -> None:
        import asyncio

        from app.schemas.ingest import Direction, FlowRecordIn, Protocol

        rollup = InProcessFlowRollup()
        source = RollupFlowSource(rollup, reason="why")
        record = FlowRecordIn(
            timestamp=START,
            src_ip="10.0.0.1",  # type: ignore[arg-type]
            dst_ip="10.0.0.2",  # type: ignore[arg-type]
            src_port=1,
            dst_port=2,
            protocol=Protocol.TCP,
            direction=Direction.OUTBOUND,
            packets=3,
            src_packets=3,
            dst_packets=0,
            src_bytes=100,
            dst_bytes=40,
            duration=1.0,
        )

        kept = asyncio.run(source.append([record]))

        assert kept == 1
        assert rollup.retained_from == START

    def test_a_summary_reaches_the_rollup(self) -> None:
        import asyncio

        source = RollupFlowSource(InProcessFlowRollup(), reason="why")

        summary = asyncio.run(source.summary(WINDOW, bucket_minutes=60))

        assert summary.totals.flows == 0
        assert len(summary.series) == 1
