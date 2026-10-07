"""T-422: the delivery read model -- what is kept, what is dropped, what is said.

The route-level half of T-422 lives in ``test_webhooks.py``, beside T-311's own
contract, because it needs that file's transport and resolver stubs. This file
tests the log itself, where the interesting properties are not about HTTP:

* a *skipped* delivery is not an attempt, so it cannot become a record -- the
  refusal is asserted rather than assumed, because a record with no attempt would
  be an outcome without a question;
* one delivery is one record however many times it is reported, so the sender's
  sink and the route that asked for the send cannot double-count it;
* the list is a bounded window that says so: ``recorded`` keeps counting past
  ``max_records``, which is what lets a screen print "showing 20 of 112" rather
  than imply it holds everything;
* the caveats name what a record is not (no URL, no secret, no alert content) and
  what an empty list means in this deployment (no sender, rather than a silent
  endpoint).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.services.correlator import Severity
from app.services.webhook_deliveries import (
    DEFAULT_MAX_RECORDS,
    DEFAULT_READ_LIMIT,
    InMemoryDeliveryLog,
    delivery_caveats,
    probe_notification,
    record_of,
    sender_sink,
)
from app.services.webhook_delivery import DeliveryAttempt, DeliveryReport

AT = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)


def report(
    delivery_id: str = "d-1",
    *,
    target_id: str = "wh_1",
    delivered: bool = True,
    outcomes: tuple[str, ...] = ("delivered",),
) -> DeliveryReport:
    """A delivery report with the attempts a test wants to describe."""
    attempts = tuple(
        DeliveryAttempt(
            attempt=index + 1,
            outcome=outcome,
            status=200 if outcome == "delivered" else None,
            delay_before=0.0 if index == 0 else 1.0,
            reason="ok" if outcome == "delivered" else outcome,
        )
        for index, outcome in enumerate(outcomes)
    )
    return DeliveryReport(
        delivery_id=delivery_id,
        target_id=target_id,
        delivered=delivered,
        attempts=attempts,
    )


def skipped(target_id: str = "wh_1") -> DeliveryReport:
    """A delivery that never reached the network: not an attempt."""
    return DeliveryReport(
        delivery_id="", target_id=target_id, delivered=False, attempts=(), skipped="below_floor"
    )


# --- a record is an attempt --------------------------------------------------


def test_a_skipped_delivery_cannot_become_a_record() -> None:
    """No attempt, no outcome -- so the transaction is refused, not stored."""
    with pytest.raises(ValueError, match="made no attempt"):
        record_of(skipped(), at=AT)


def test_a_record_summarises_the_last_attempt() -> None:
    record = record_of(report(outcomes=("retry", "delivered")), at=AT)

    assert record.attempt_count == 2
    assert record.waited_seconds == pytest.approx(1.0)
    assert (record.outcome, record.status, record.reason) == ("delivered", 200, "ok")
    assert record.delivered is True
    assert record.at == AT


def test_a_failed_delivery_records_the_failure_not_a_blank() -> None:
    record = record_of(report(delivered=False, outcomes=("retry", "transport_error")), at=AT)

    assert record.delivered is False
    assert record.outcome == "transport_error"
    assert record.status is None


def test_the_same_delivery_is_recorded_once_however_often_it_is_reported() -> None:
    """The sink and the caller both reporting is the shape this exists to allow."""
    log = InMemoryDeliveryLog()
    once = log.record(report(), at=AT)
    twice = log.record(report(), at=AT + timedelta(seconds=5))

    assert once == twice
    assert log.recorded == 1
    assert len(log) == 1


def test_two_targets_two_deliveries_are_two_records() -> None:
    log = InMemoryDeliveryLog()
    log.record(report("d-1", target_id="wh_1"), at=AT)
    log.record(report("d-2", target_id="wh_2"), at=AT)

    assert [record.delivery_id for record in log.recent()] == ["d-2", "d-1"]


# --- the window is bounded and says so ---------------------------------------


def test_the_newest_record_is_first() -> None:
    log = InMemoryDeliveryLog()
    for index in range(3):
        log.record(report(f"d-{index}"), at=AT + timedelta(seconds=index))

    assert [record.delivery_id for record in log.recent()] == ["d-2", "d-1", "d-0"]


def test_the_log_drops_the_oldest_and_counts_what_it_dropped() -> None:
    log = InMemoryDeliveryLog(max_records=2)
    for index in range(5):
        log.record(report(f"d-{index}"), at=AT)

    assert log.recorded == 5
    assert log.held == 2
    assert [record.delivery_id for record in log.recent()] == ["d-4", "d-3"]


def test_a_read_is_limited_without_forgetting_the_rest() -> None:
    log = InMemoryDeliveryLog()
    for index in range(5):
        log.record(report(f"d-{index}"), at=AT)

    assert len(log.recent(limit=2)) == 2
    assert log.held == 5


@pytest.mark.parametrize("limit", [0, -1])
def test_a_read_that_asks_for_nothing_is_refused(limit: int) -> None:
    """A limit of zero is a caller bug, not an empty answer."""
    with pytest.raises(ValueError, match="limit must be positive"):
        InMemoryDeliveryLog().recent(limit=limit)


def test_a_log_that_holds_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="max_records must be positive"):
        InMemoryDeliveryLog(max_records=0)


def test_the_sink_records_where_the_attempt_was_made() -> None:
    """The seam the pipeline will use, exercised as the probe route uses it."""
    log = InMemoryDeliveryLog()
    sink = sender_sink(log, clock=lambda: AT)

    sink(report())

    assert log.recorded == 1
    assert log.recent()[0].at == AT


def test_the_sink_drops_a_skipped_delivery_rather_than_raising() -> None:
    """``deliver`` reports a below-floor target, and the sink must survive it.

    A skipped delivery is handed to the sink like any other report, so a sink
    that passed it to :func:`record_of` would turn a correctly filtered alert
    into a ``ValueError`` in the sender's dispatch loop.
    """
    log = InMemoryDeliveryLog()
    sink = sender_sink(log, clock=lambda: AT)

    sink(skipped())

    assert log.recorded == 0
    assert log.held == 0


# --- the sentences -----------------------------------------------------------


def test_the_caveats_say_what_a_record_is_not() -> None:
    log = InMemoryDeliveryLog()
    caveats = delivery_caveats(log=log, shown=0, dispatch_configured=True)

    assert "never carries the URL, the signing secret or alert content" in caveats[0]
    assert "a restart forgets them" in caveats[1]
    assert str(DEFAULT_MAX_RECORDS) in caveats[1]


def test_an_empty_list_in_a_deployment_with_no_sender_says_why() -> None:
    """The difference between "nothing has happened" and "nothing can happen"."""
    log = InMemoryDeliveryLog()

    without = delivery_caveats(log=log, shown=0, dispatch_configured=False)
    with_sender = delivery_caveats(log=log, shown=0, dispatch_configured=True)

    assert any("no outbound transport" in sentence for sentence in without)
    assert not any("no outbound transport" in sentence for sentence in with_sender)
    assert any("has an empty list rather than a failing endpoint" in s for s in with_sender)


def test_a_capped_read_says_how_much_of_the_log_it_holds() -> None:
    log = InMemoryDeliveryLog()
    for index in range(DEFAULT_READ_LIMIT + 5):
        log.record(report(f"d-{index}"), at=AT)

    caveats = delivery_caveats(log=log, shown=DEFAULT_READ_LIMIT, dispatch_configured=True)

    assert any("of the" in sentence and "newest first" in sentence for sentence in caveats)


def test_a_full_read_says_nothing_about_a_cap() -> None:
    """A sentence that is always present tells a reader nothing when it matters."""
    log = InMemoryDeliveryLog()
    log.record(report(), at=AT)

    caveats = delivery_caveats(log=log, shown=1, dispatch_configured=True)

    assert len(caveats) == 2


# --- the probe's content -----------------------------------------------------


def test_the_probe_sends_an_alert_shaped_document_that_is_clearly_synthetic() -> None:
    notification = probe_notification(Severity.critical)

    assert notification.alert.family == "Connectivity test"
    assert notification.alert.entity_id == 0
    assert notification.alert.id == 0
    assert notification.alert.score == 0.0
    assert notification.sequence == 0


def test_the_probe_uses_the_targets_own_floor_band() -> None:
    assert probe_notification(Severity.low).alert.severity == "low"
