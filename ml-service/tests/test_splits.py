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
from aegis_ml.data.splits import Split, split_windows
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
        "train_entities",
        "test_entities",
        "test_after_train",
        "entities_disjoint",
    }
    assert audit["train"] == 24 and audit["test"] == 12 and audit["dropped"] == 0


def test_split_is_reusable_for_the_leakage_audit() -> None:
    """T-111 needs these handles, so they are part of the contract."""
    split: Split[FlowRecord] = split_windows(
        banded_windows(), test_fraction=0.25, valid_fraction=1 / 3
    )

    assert isinstance(split.train[0].records[0], FlowRecord)
    assert split.train[0].key in split.train_entities
