"""T-308: severity banding, cool-down dedup, and flow/log grouping.

The acceptance criterion is that a duplicate (entity, family) inside the
cool-down increments `occurrence_count` instead of creating a row, so the tests
count rows and not just calls: an implementation could return the right object
while still inserting.

FR-13's thresholds are inclusive lower bounds and are tested at the boundary on
both sides, because "0.90 is critical, 0.8999 is high" is the kind of detail
that is silently wrong in one direction and nobody notices for months.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.services.correlator import (
    BAND_FLOOR,
    DEFAULT_COOL_DOWN,
    GROUPING_WINDOW,
    Correlator,
    InMemoryAlertStore,
    ScoreEvent,
    Severity,
    severity_band,
)

T0 = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)


def event(
    *,
    entity_id: int = 1,
    family: str = "DoS",
    score: float = 0.8,
    modality: str = "flow",
    at: datetime = T0,
    reasons: tuple[str, ...] = (),
) -> ScoreEvent:
    """A scored event, with defaults for the common case."""
    return ScoreEvent(
        entity_id=entity_id,
        entity_value=f"10.0.0.{entity_id}",
        family=family,
        score=score,
        modality=modality,  # type: ignore[arg-type]
        seen_at=at,
        reasons=reasons,
    )


# --- FR-13: severity banding ------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (1.0, Severity.CRITICAL),
        (0.95, Severity.CRITICAL),
        (0.90, Severity.CRITICAL),  # inclusive
        (0.8999, Severity.HIGH),
        (0.75, Severity.HIGH),  # inclusive
        (0.7499, Severity.MEDIUM),
        (0.55, Severity.MEDIUM),  # inclusive
        (0.5499, Severity.LOW),
        (0.35, Severity.LOW),  # inclusive
        (0.3499, Severity.INFO),
        (0.0, Severity.INFO),
    ],
)
def test_the_bands_match_fr13(score: float, expected: Severity) -> None:
    assert severity_band(score) is expected


def test_the_floor_is_the_documented_one() -> None:
    assert BAND_FLOOR == 0.35


def test_an_out_of_range_score_is_refused_not_clamped() -> None:
    """1.4 means something upstream is broken; banding it hides that."""
    for bad in (-0.01, 1.01, 2.0, -1.0):
        with pytest.raises(ValueError, match="outside"):
            severity_band(bad)


def test_the_severity_reaches_the_alert() -> None:
    store = InMemoryAlertStore()
    alert = Correlator(store).correlate(event(score=0.93))
    assert alert.severity == "critical"


# --- FR-15: the cool-down criterion -----------------------------------------


def test_a_duplicate_increments_instead_of_inserting() -> None:
    """The acceptance criterion, counted in rows."""
    store = InMemoryAlertStore()
    correlator = Correlator(store)

    first = correlator.correlate(event())
    second = correlator.correlate(event(at=T0 + timedelta(minutes=5)))

    assert len(store.all()) == 1
    assert first.alert_id == second.alert_id
    assert second.occurrence_count == 2
    assert store.all()[0].occurrence_count == 2
    # `first` is a snapshot taken when the count was 1 and must stay that way:
    # a caller holding an earlier result must not see it change underneath them.
    assert first.occurrence_count == 1
    assert first.is_new
    assert not second.is_new


def test_the_default_cool_down_is_15_minutes() -> None:
    assert timedelta(minutes=15) == DEFAULT_COOL_DOWN


def test_a_duplicate_at_exactly_the_boundary_is_suppressed() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event())
    correlator.correlate(event(at=T0 + DEFAULT_COOL_DOWN))
    assert len(store.all()) == 1


def test_a_duplicate_just_past_the_boundary_creates_a_row() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event())
    correlator.correlate(event(at=T0 + DEFAULT_COOL_DOWN + timedelta(seconds=1)))
    assert len(store.all()) == 2


def test_last_seen_moves_forward_on_increment() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event())
    alert = correlator.correlate(event(at=T0 + timedelta(minutes=5)))
    assert alert.last_seen == T0 + timedelta(minutes=5)
    assert alert.first_seen == T0


def test_a_late_arrival_does_not_move_last_seen_backwards() -> None:
    """Otherwise an alert looks less recent than it already did."""
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event())
    correlator.correlate(event(at=T0 + timedelta(minutes=10)))
    alert = correlator.correlate(event(at=T0 + timedelta(minutes=2)))
    assert alert.last_seen == T0 + timedelta(minutes=10)
    assert alert.occurrence_count == 3


def test_a_different_family_is_not_a_duplicate() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event(family="DoS"))
    correlator.correlate(event(family="Reconnaissance"))
    assert len(store.all()) == 2


def test_a_different_entity_is_not_a_duplicate() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event(entity_id=1))
    correlator.correlate(event(entity_id=2))
    assert len(store.all()) == 2


def test_many_duplicates_produce_one_row_with_the_right_count() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    for i in range(20):
        correlator.correlate(event(at=T0 + timedelta(minutes=i)))
    alerts = store.all()
    assert len(alerts) == 1
    assert alerts[0].occurrence_count == 20


def test_sliding_suppression_keeps_an_ongoing_attack_as_one_alert() -> None:
    """The chosen policy, stated as behaviour rather than as a comment."""
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    # Recurring every 14 minutes for 5 hours: always inside the window.
    for i in range(22):
        correlator.correlate(event(at=T0 + timedelta(minutes=14 * i)))
    alerts = store.all()
    assert len(alerts) == 1
    assert alerts[0].occurrence_count == 22
    # ...and the duration is recoverable, which is the only record of it.
    assert alerts[0].last_seen - alerts[0].first_seen == timedelta(minutes=14 * 21)


def test_the_fixed_anchor_would_have_created_many_rows() -> None:
    """Recorded so the choice is visible and reversible, not buried."""
    store = InMemoryAlertStore()
    correlator = Correlator(store, anchor="first_seen")
    for i in range(22):
        correlator.correlate(event(at=T0 + timedelta(minutes=14 * i)))
    assert len(store.all()) > 1


def test_the_cool_down_is_configurable() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store, cool_down=timedelta(minutes=1))
    correlator.correlate(event())
    correlator.correlate(event(at=T0 + timedelta(minutes=2)))
    assert len(store.all()) == 2


def test_a_non_positive_cool_down_is_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        Correlator(InMemoryAlertStore(), cool_down=timedelta(0))


def test_batch_order_decides_which_event_becomes_the_row() -> None:
    store = InMemoryAlertStore()
    results = Correlator(store).correlate_batch([event(at=T0 + timedelta(minutes=1)), event(at=T0)])
    assert results[0].is_new
    assert not results[1].is_new
    assert store.all()[0].first_seen == T0 + timedelta(minutes=1)


# --- FR-14: explanation -----------------------------------------------------


def test_the_explanation_is_attached() -> None:
    store = InMemoryAlertStore()
    alert = Correlator(store).correlate(
        event(reasons=("duration high", "dst_port_count high", "syn ratio high"))
    )
    assert alert.explanation == ["duration high", "dst_port_count high", "syn ratio high"]


def test_only_the_top_three_are_kept() -> None:
    """FR-14 says top-3; a longer list is not more useful at 3am."""
    store = InMemoryAlertStore()
    alert = Correlator(store).correlate(event(reasons=tuple(f"r{i}" for i in range(7))))
    assert alert.explanation == ["r0", "r1", "r2"]


def test_the_order_is_preserved() -> None:
    """Most significant first, so the first line is the one that matters."""
    store = InMemoryAlertStore()
    alert = Correlator(store).correlate(event(reasons=("biggest", "middle", "smallest")))
    assert alert.explanation[0] == "biggest"


# --- FR-19: flow/log grouping -----------------------------------------------


def test_the_grouping_window_is_60_seconds() -> None:
    assert timedelta(seconds=60) == GROUPING_WINDOW


def test_a_flow_and_log_alert_on_one_entity_group_into_one_case() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event(modality="flow", at=T0))
    correlator.correlate(
        event(family="Reconnaissance", modality="log", at=T0 + timedelta(seconds=30))
    )

    grouped = correlator.grouped_cases()
    assert len(grouped) == 1
    assert len(next(iter(grouped.values()))) == 2


def test_alerts_outside_the_window_do_not_group() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event(modality="flow", at=T0))
    correlator.correlate(
        event(family="Reconnaissance", modality="log", at=T0 + timedelta(seconds=61))
    )
    assert correlator.grouped_cases() == {}


def test_a_lone_alert_is_not_a_case() -> None:
    """Calling a single alert a "case" would overstate the grouping."""
    correlator = Correlator(InMemoryAlertStore())
    correlator.correlate(event())
    assert correlator.grouped_cases() == {}


def test_different_entities_do_not_group() -> None:
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event(entity_id=1, modality="flow", at=T0))
    correlator.correlate(event(entity_id=2, family="Reconnaissance", modality="log", at=T0))
    assert correlator.grouped_cases() == {}


def test_grouping_works_when_the_log_alert_arrives_first() -> None:
    """Neither alert knows the other's id, so order must not matter."""
    store = InMemoryAlertStore()
    correlator = Correlator(store)
    correlator.correlate(event(family="Reconnaissance", modality="log", at=T0))
    correlator.correlate(event(modality="flow", at=T0 + timedelta(seconds=20)))
    assert len(correlator.grouped_cases()) == 1
