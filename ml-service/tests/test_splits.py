"""Tests for the temporal, entity-disjoint split (T-109).

The fixture below is deliberately shaped: eight hosts in four time bands, two
per band, so that hosts appear and disappear over time. That churn is what makes
a split which is *both* strictly temporal *and* entity-disjoint possible at all
— see ``test_a_stream_with_no_entity_churn_is_refused`` for what happens without
it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aegis_ml.data.records import Direction, FlowRecord, Protocol
from aegis_ml.data.splits import Split, group_split, split_windows
from aegis_ml.data.synthetic import GenerationSpec, Scenario, generate_flows
from aegis_ml.data.windowing import Window, window_flows

EPOCH = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)

#: Four time bands, two hosts each. Bands are separated by gaps no host is
#: active during, which is where the cuts land.
BANDS: tuple[tuple[str, ...], ...] = (
    ("10.4.20.11", "10.4.20.12"),
    ("10.4.20.13", "10.4.20.14"),
    ("10.4.20.15", "10.4.20.16"),
    ("10.4.20.17", "10.4.20.18"),
)


def host_flows(host: str, start: datetime, count: int = 30) -> list[FlowRecord]:
    """Build ``count`` evenly spaced flows from one host."""
    return [
        FlowRecord(
            timestamp=start + timedelta(seconds=index),
            src_ip=host,
            dst_ip="10.4.20.90",
            src_port=51000 + index,
            dst_port=443,
            protocol=Protocol.TCP,
            direction=Direction.INTERNAL,
            packets=10,
            src_packets=5,
            dst_packets=5,
            src_bytes=1200,
            dst_bytes=3400,
            duration=0.4,
            label="normal",
        )
        for index in range(count)
    ]


def banded_windows(size: int = 5) -> tuple[Window[FlowRecord], ...]:
    """Window a stream of eight hosts across four time bands: 48 windows."""
    flows: list[FlowRecord] = []
    for band, hosts in enumerate(BANDS):
        for host in hosts:
            flows.extend(host_flows(host, EPOCH + timedelta(seconds=band * 40)))
    flows.sort(key=lambda record: record.timestamp)
    return window_flows(flows, size=size)


# --- the acceptance criteria --------------------------------------------


def test_test_is_strictly_later_than_train() -> None:
    """R-60: the model can never be tuned on the period it is scored on."""
    split = split_windows(banded_windows(), test_fraction=0.25, valid_fraction=1 / 3)

    assert split.max_train_start < split.min_test_start
    assert split.audit()["test_after_train"] is True
    # Nothing in valid may be as late as test either.
    assert max(window.start for window in split.valid) < split.min_test_start
    assert max(window.start for window in split.train) < min(window.start for window in split.valid)


def test_no_entity_appears_in_two_folds() -> None:
    """R-61: memorising a host must not be rewarded."""
    split = split_windows(banded_windows(), test_fraction=0.25, valid_fraction=1 / 3)

    assert split.audit()["entities_disjoint"] is True
    assert not (split.train_entities & split.valid_entities)
    assert not (split.train_entities & split.test_entities)
    assert not (split.valid_entities & split.test_entities)
    assert split.train_entities == {"10.4.20.11", "10.4.20.12", "10.4.20.13", "10.4.20.14"}
    assert split.valid_entities == {"10.4.20.15", "10.4.20.16"}
    assert split.test_entities == {"10.4.20.17", "10.4.20.18"}


def test_fold_sizes_and_cutoffs_are_exact() -> None:
    """48 windows over four bands of twelve: 24 / 12 / 12, cut in the gaps."""
    split = split_windows(banded_windows(), test_fraction=0.25, valid_fraction=1 / 3)

    assert (len(split.train), len(split.valid), len(split.test)) == (24, 12, 12)
    assert split.test_cutoff == EPOCH + timedelta(seconds=120)
    assert split.valid_cutoff == EPOCH + timedelta(seconds=80)
    assert split.dropped == 0, "no host spans a cut, so nothing is discarded"


def test_splitting_is_deterministic() -> None:
    windows = banded_windows()
    first = split_windows(windows, test_fraction=0.25, valid_fraction=1 / 3)
    second = split_windows(windows, test_fraction=0.25, valid_fraction=1 / 3)

    assert first == second


# --- the honest failure modes -------------------------------------------


def test_a_stream_with_no_entity_churn_is_refused() -> None:
    """Every host active end to end makes both invariants unsatisfiable.

    Rather than quietly leak, the split raises. This is the common case on
    captured traffic and is worth knowing before trusting any score.
    """
    flows = generate_flows(GenerationSpec(Scenario.NORMAL, 200, 7))
    windows = window_flows(flows, size=10)

    assert len({window.key for window in windows}) == 4
    with pytest.raises(ValueError, match="leaves one side empty"):
        split_windows(windows, test_fraction=0.25, valid_fraction=1 / 3)


def test_windows_spanning_the_cut_are_dropped_and_counted() -> None:
    """A host on both sides keeps its early windows and loses its late ones."""
    windows = banded_windows()
    # A ninth host that is active in the first band and again in the last.
    spanning = window_flows(
        sorted(
            host_flows("10.4.20.99", EPOCH)
            + host_flows("10.4.20.99", EPOCH + timedelta(seconds=120)),
            key=lambda record: record.timestamp,
        ),
        size=5,
    )
    combined = tuple(sorted((*windows, *spanning), key=lambda window: (window.start, window.key)))

    split = split_windows(combined, test_fraction=0.3, valid_fraction=2 / 7)

    assert "10.4.20.99" in split.train_entities
    assert "10.4.20.99" not in split.test_entities
    assert split.dropped == 6, "the spanning host's six late windows are reported"
    assert split.audit()["entities_disjoint"] is True
    assert split.audit()["test_after_train"] is True


# --- validation ----------------------------------------------------------


def test_input_and_fractions_are_validated() -> None:
    windows = banded_windows()

    with pytest.raises(ValueError, match="empty sequence"):
        split_windows([])

    with pytest.raises(ValueError, match="test_fraction must be in"):
        split_windows(windows, test_fraction=0.0)

    with pytest.raises(ValueError, match="valid_fraction must be in"):
        split_windows(windows, valid_fraction=1.0)

    with pytest.raises(ValueError, match="leave room for training"):
        split_windows(windows, test_fraction=0.6, valid_fraction=0.6)


def test_a_single_host_cannot_be_split() -> None:
    windows = window_flows(host_flows("10.4.20.11", EPOCH, 60), size=5)

    with pytest.raises(ValueError, match="leaves one side empty"):
        split_windows(windows)


def test_audit_reports_every_invariant() -> None:
    split = split_windows(banded_windows(), test_fraction=0.25, valid_fraction=1 / 3)

    audit = split.audit()

    assert set(audit) == {
        "train",
        "valid",
        "test",
        "dropped",
        "entity_disjoint_enforced",
        "temporal_enforced",
        "train_entities",
        "test_entities",
        "test_after_train",
        "shared_train_test_entities",
        "shared_train_valid_entities",
        "shared_valid_test_entities",
        "entities_disjoint",
    }
    assert audit["entity_disjoint_enforced"] is True
    assert audit["temporal_enforced"] is True
    assert audit["train"] == 24 and audit["test"] == 12 and audit["dropped"] == 0


def test_split_is_reusable_for_the_leakage_audit() -> None:
    """T-111 needs these handles, so they are part of the contract."""
    split: Split[FlowRecord] = split_windows(
        banded_windows(), test_fraction=0.25, valid_fraction=1 / 3
    )

    assert isinstance(split.train[0].records[0], FlowRecord)
    assert split.train[0].key in split.train_entities


# --- the split policy (D-015) ---------------------------------------------


def spanning_stream() -> tuple[Window[FlowRecord], ...]:
    """Eight banded hosts plus one host active in both the first and last band."""
    spanning = window_flows(
        sorted(
            host_flows("10.4.20.99", EPOCH)
            + host_flows("10.4.20.99", EPOCH + timedelta(seconds=120)),
            key=lambda record: record.timestamp,
        ),
        size=5,
    )
    return tuple(
        sorted((*banded_windows(), *spanning), key=lambda window: (window.start, window.key))
    )


def test_relaxing_entity_disjointness_keeps_the_spanning_host() -> None:
    """R-61 is a policy, so turning it off must observably change the fold."""
    windows = spanning_stream()
    strict = split_windows(windows, test_fraction=0.3, valid_fraction=2 / 7)
    relaxed = split_windows(windows, test_fraction=0.3, valid_fraction=2 / 7, entity_disjoint=False)

    assert strict.dropped == 6
    assert relaxed.dropped == 0, "nothing is discarded when R-61 is off"
    assert len(relaxed.test) == len(strict.test) + 6
    assert "10.4.20.99" in strict.train_entities
    assert "10.4.20.99" not in strict.test_entities
    assert "10.4.20.99" in relaxed.train_entities
    assert "10.4.20.99" in relaxed.test_entities


def test_the_audit_counts_the_overlap_it_reports() -> None:
    """The leakage is measured, not asserted, so a caller can price it."""
    windows = spanning_stream()
    strict = split_windows(windows, test_fraction=0.3, valid_fraction=2 / 7)
    relaxed = split_windows(windows, test_fraction=0.3, valid_fraction=2 / 7, entity_disjoint=False)

    assert strict.audit()["shared_train_test_entities"] == 0
    assert strict.audit()["entities_disjoint"] is True
    assert relaxed.audit()["shared_train_test_entities"] == 1
    assert relaxed.audit()["entities_disjoint"] is False
    assert relaxed.audit()["entity_disjoint_enforced"] is False
    assert strict.audit()["entity_disjoint_enforced"] is True


def test_the_temporal_invariant_is_never_relaxed() -> None:
    """R-60 has no off switch: relaxing the policy must not reorder folds."""
    relaxed = split_windows(
        spanning_stream(),
        test_fraction=0.3,
        valid_fraction=2 / 7,
        entity_disjoint=False,
    )

    assert relaxed.audit()["test_after_train"] is True
    assert relaxed.min_test_start > relaxed.max_train_start


def test_entity_disjointness_is_the_default() -> None:
    """A caller that says nothing still gets the release-gate policy."""
    windows = spanning_stream()

    assert split_windows(windows, test_fraction=0.3, valid_fraction=2 / 7) == split_windows(
        windows, test_fraction=0.3, valid_fraction=2 / 7, entity_disjoint=True
    )


# --- the entity-only policy (Q-07) ----------------------------------------


def many_host_windows(hosts: int = 60, size: int = 5) -> tuple[Window[FlowRecord], ...]:
    """Window a stream of many hosts.

    A hash partition needs enough entities that every fold is populated by
    construction rather than by luck: `banded_windows` has eight, and splitting
    eight entities three ways is a coin toss the split is right to refuse.
    """
    flows: list[FlowRecord] = []
    for index in range(hosts):
        flows.extend(host_flows(f"10.4.30.{index}", EPOCH + timedelta(seconds=index * 7)))
    flows.sort(key=lambda record: record.timestamp)
    return window_flows(flows, size=size)


def group_fixture() -> tuple[Window[FlowRecord], ...]:
    """Sixty hosts plus one that is active at both ends of the capture."""
    spanning = window_flows(
        sorted(
            host_flows("10.4.20.99", EPOCH)
            + host_flows("10.4.20.99", EPOCH + timedelta(seconds=400)),
            key=lambda record: record.timestamp,
        ),
        size=5,
    )
    return tuple(
        sorted((*many_host_windows(), *spanning), key=lambda window: (window.start, window.key))
    )


def test_group_split_keeps_every_entity_whole() -> None:
    """An entity's windows never straddle a fold, so the disjointness is exact."""
    windows = group_fixture()
    split = group_split(windows, test_fraction=0.25, valid_fraction=1 / 3)

    folds = [
        {window.key for window in split.train},
        {window.key for window in split.valid},
        {window.key for window in split.test},
    ]
    assert sum(len(keys) for keys in folds) == len({w.key for w in windows})
    assert len(split.train) + len(split.valid) + len(split.test) == len(windows)


def test_group_split_is_exactly_entity_disjoint() -> None:
    """No overlap to report, because the partition is by entity rather than time."""
    audit = group_split(group_fixture(), test_fraction=0.25, valid_fraction=1 / 3).audit()

    assert audit["entities_disjoint"] is True
    assert audit["shared_train_test_entities"] == 0
    assert audit["shared_train_valid_entities"] == 0
    assert audit["shared_valid_test_entities"] == 0
    assert audit["entity_disjoint_enforced"] is True
    assert audit["temporal_enforced"] is False
    assert audit["dropped"] == 0


def test_group_split_is_deterministic() -> None:
    """A salted hash would reshuffle folds per process and silently move metrics."""
    windows = group_fixture()

    assert group_split(windows, test_fraction=0.25, valid_fraction=1 / 3) == group_split(
        windows, test_fraction=0.25, valid_fraction=1 / 3
    )


def test_group_split_holds_a_persistent_entity_in_one_fold() -> None:
    """The property the temporal split cannot provide: a spanning host is not cut.

    Under R-60 + R-61 the spanning host's late windows are dropped entirely, so
    an attack from a persistent source can never reach the test fold. Here every
    one of its windows survives, in whichever single fold its key hashed to.
    """
    combined = group_fixture()
    temporal = split_windows(combined, test_fraction=0.25, valid_fraction=1 / 3)
    grouped = group_split(combined, test_fraction=0.25, valid_fraction=1 / 3)

    def spanning_in(split: Split[FlowRecord]) -> list[Window[FlowRecord]]:
        return [
            window
            for window in (*split.train, *split.valid, *split.test)
            if window.key == "10.4.20.99"
        ]

    total = sum(1 for window in combined if window.key == "10.4.20.99")
    kept_temporal = spanning_in(temporal)
    kept_grouped = spanning_in(grouped)
    assert temporal.dropped > 0, "the temporal split discards spanning windows"
    assert grouped.dropped == 0
    # Every one of that host's windows survives the group split...
    assert len(kept_grouped) == total
    # ...while the temporal split necessarily loses some of them.
    assert len(kept_temporal) < total
    # And the surviving windows sit in exactly one fold, not spread across them.
    occupied = [
        fold
        for fold in (grouped.train, grouped.valid, grouped.test)
        if any(window.key == "10.4.20.99" for window in fold)
    ]
    assert len(occupied) == 1


def test_group_split_refuses_too_few_entities() -> None:
    """With eight entities a three-way partition is luck, so it refuses."""
    with pytest.raises(ValueError, match="too few"):
        group_split(banded_windows(), test_fraction=0.25, valid_fraction=1 / 3)
    # One entity cannot populate three folds at all.
    with pytest.raises(ValueError, match="too few"):
        group_split(window_flows(sorted(host_flows("10.4.20.9", EPOCH), key=lambda r: r.timestamp)))


def test_group_split_validates_its_input() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        group_split([])
    with pytest.raises(ValueError, match="test_fraction"):
        group_split(many_host_windows(), test_fraction=0.0, valid_fraction=0.1)
    with pytest.raises(ValueError, match="leave room"):
        group_split(many_host_windows(), test_fraction=0.6, valid_fraction=0.6)
