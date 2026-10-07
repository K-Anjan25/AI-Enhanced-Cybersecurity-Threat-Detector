"""What happened to each delivery attempt, and where an operator reads it (T-422).

T-311's delivery half makes attempts and reports them: to its caller, and to a
log sink as a structured record. What it did not have is a *read model* — a place
the connectors screen can ask "did that endpoint take anything, and if it did not,
why not" — so this module is that, and the route that serves it reads a
:class:`DeliveryLog` rather than the process log.

Four things it is careful about:

* **A record is made where the attempt is made**, by the sender handing its report
  to a sink, not by the route that asked for the send. A read model fed by its own
  callers would go quiet exactly when a delivery went wrong somewhere else.
* **A record carries no URL, no secret and no alert content** (R-54, R-58). It
  names the target by id, and carries the attempt count, the outcome, the status
  code and a reason *code* — never a message from the peer, which could echo a
  body back. The operator who needs the payload has the alerts API and the
  receiver's own log, joined by ``delivery_id``.
* **The list is bounded, and says what it is.** The log keeps the newest
  ``max_records`` attempts and counts every record it has ever made, so a screen
  can say "showing the newest 20 of 112" instead of implying it holds them all.
  It lives in this process: a restart forgets every record, and that is stated in
  words rather than implied by an empty table.
* **Nothing is claimed about dispatch.** A deployment with no sender configured
  has a log that is empty by construction, and :func:`delivery_caveats` says so
  in exactly those terms instead of letting an operator read an empty table as a
  quiet endpoint.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.schemas.query import AlertRow
from app.services.alert_stream import AlertNotification
from app.services.correlator import Severity
from app.services.webhook_delivery import DeliveryReport

__all__ = [
    "DEFAULT_MAX_RECORDS",
    "DEFAULT_READ_LIMIT",
    "MAX_READ_LIMIT",
    "DeliveryLog",
    "DeliveryRecord",
    "InMemoryDeliveryLog",
    "delivery_caveats",
    "probe_notification",
    "record_of",
    "sender_sink",
]

#: How many attempts the process keeps. Bounded because this is a diagnostic
#: window, not an audit trail -- the audit trail records that a target was
#: configured and by whom (T-312), and it deliberately records nothing per send.
DEFAULT_MAX_RECORDS = 200

#: What a read returns when the caller does not say.
DEFAULT_READ_LIMIT = 50

#: Most a caller may ask for in one read.
MAX_READ_LIMIT = 200


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    """One delivery that was attempted, as the connectors screen reads it.

    Attributes:
        delivery_id: the id the receiver saw in ``X-AEGIS-Delivery``, so its log
            and this record can be joined.
        target_id: which configured target.
        at: when the delivery finished, on the process clock the API runs on.
        delivered: whether a receiver accepted it.
        attempt_count: how many requests were made.
        waited_seconds: total time spent in backoffs between them.
        outcome: the last attempt's outcome -- ``delivered``, ``retry``,
            ``rejected``, ``blocked`` or ``transport_error``.
        status: the HTTP status of the last attempt, when there was one.
        reason: a short code for that outcome, never a message from the peer.
    """

    delivery_id: str
    target_id: str
    at: datetime
    delivered: bool
    attempt_count: int
    waited_seconds: float
    outcome: str
    status: int | None
    reason: str


def record_of(report: DeliveryReport, *, at: datetime) -> DeliveryRecord:
    """Turn one delivery report into the record a screen reads.

    Raises:
        ValueError: if the report holds no attempts. A skipped delivery -- below
            the severity floor, or to an inactive target -- never reached the
            network, so it is not an attempt and has no outcome to report.
    """
    if not report.attempts:
        msg = f"delivery {report.delivery_id or '(none)'} made no attempt"
        raise ValueError(msg)
    last = report.attempts[-1]
    return DeliveryRecord(
        delivery_id=report.delivery_id,
        target_id=report.target_id,
        at=at,
        delivered=report.delivered,
        attempt_count=report.attempt_count,
        waited_seconds=report.waited_seconds,
        outcome=last.outcome,
        status=last.status,
        reason=last.reason,
    )


class DeliveryLog(Protocol):
    """Where delivery attempts are recorded and read back."""

    def record(self, report: DeliveryReport, *, at: datetime) -> DeliveryRecord:
        """Record one attempted delivery and return the record.

        Raises:
            ValueError: if the report holds no attempts, as :func:`record_of`.
        """
        ...

    def recent(self, *, limit: int = DEFAULT_READ_LIMIT) -> tuple[DeliveryRecord, ...]:
        """The newest ``limit`` records, newest first."""
        ...

    @property
    def recorded(self) -> int:
        """How many records this log has made, including ones it has dropped."""
        ...

    @property
    def held(self) -> int:
        """How many records it still holds."""
        ...


class InMemoryDeliveryLog:
    """A :class:`DeliveryLog` in a deque, for this process's lifetime.

    The newest record is first, and the oldest is dropped past ``max_records``
    while ``recorded`` keeps counting, so a capped list is visibly a window onto
    more attempts rather than all of them.

    **One record per delivery.** A report is identified by its ``delivery_id``,
    and recording the same one twice returns the record already held rather than
    appending a second. That is what makes two plausible ways to record a
    delivery -- the sender's sink and the route that asked for the send -- safe to
    have at once, and it is the same deduplication a receiver does on the header.
    """

    __slots__ = ("_max_records", "_recorded", "_records", "_seen")

    def __init__(self, *, max_records: int = DEFAULT_MAX_RECORDS) -> None:
        """Start empty, keeping at most ``max_records``.

        Raises:
            ValueError: if ``max_records`` is not positive -- a log that holds
                nothing would answer every read with an empty table.
        """
        if max_records < 1:
            msg = f"max_records must be positive, got {max_records}"
            raise ValueError(msg)
        self._max_records = max_records
        self._recorded = 0
        self._records: deque[DeliveryRecord] = deque()
        self._seen: dict[str, DeliveryRecord] = {}

    def record(self, report: DeliveryReport, *, at: datetime) -> DeliveryRecord:
        """Record one attempted delivery, dropping the oldest past the cap.

        Idempotent on ``delivery_id``: a report already recorded is returned as
        it stands, so a delivery cannot be counted twice by being reported from
        two places.
        """
        existing = self._seen.get(report.delivery_id)
        if existing is not None:
            return existing
        record = record_of(report, at=at)
        self._records.appendleft(record)
        self._recorded += 1
        self._seen[record.delivery_id] = record
        while len(self._records) > self._max_records:
            self._records.pop()
        return record

    def extend(self, reports: Iterable[DeliveryReport], *, at: datetime) -> None:
        """Record several deliveries that finished at the same moment."""
        for report in reports:
            self.record(report, at=at)

    def recent(self, *, limit: int = DEFAULT_READ_LIMIT) -> tuple[DeliveryRecord, ...]:
        """The newest records, newest first, at most ``limit`` of them."""
        if limit < 1:
            msg = f"limit must be positive, got {limit}"
            raise ValueError(msg)
        return tuple(self._records)[:limit]

    @property
    def recorded(self) -> int:
        """How many records have been made in this log's lifetime."""
        return self._recorded

    @property
    def held(self) -> int:
        """How many records the log still holds."""
        return len(self._records)

    def __len__(self) -> int:
        """Alias for :attr:`held`, for the assertion that reads naturally."""
        return len(self._records)


def probe_notification(severity: Severity) -> AlertNotification:
    """The synthetic alert a test send carries (T-422).

    A probe sends the *same document a real alert would* -- the receiver's schema
    is exercised rather than a bespoke test payload -- with content that cannot be
    mistaken for a detection: entity ``0``, family "Connectivity test", score
    ``0.0`` and an alert id of ``0``. The severity is the target's own floor, so
    what a receiver sees is the band that target asked for.

    The stream sequence is ``0`` on purpose: a probe is not in the alert stream,
    and giving it a position would make it look like one alert among others to
    anything that counted it. A receiver that deduplicates on the delivery id
    still sees a distinct id per probe.
    """
    return AlertNotification(
        sequence=0,
        alert=AlertRow(
            id=0,
            created_at=datetime.now(UTC),
            entity_id=0,
            family="Connectivity test",
            severity=severity.value,
            score=0.0,
            status="open",
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            occurrence_count=1,
            trace_id=None,
        ),
    )


def sender_sink(
    log: DeliveryLog, *, clock: Callable[[], datetime] | None = None
) -> Callable[[DeliveryReport], None]:
    """The sink that records a report the moment it is made (T-422).

    Handed to :class:`~app.services.webhook_delivery.WebhookSender` as
    ``on_report``, so a delivery is recorded where the attempt is made rather than
    by whichever caller asked for it -- the pipeline's dispatch path, a probe, or
    something not written yet. Recording is idempotent on the delivery id, so a
    caller that also records the report it got back does not create a second row.

    Args:
        log: the log to record into.
        clock: what "now" means for the record; defaults to UTC wall time.

    Returns:
        A callable taking one report.
    """
    stamp = clock or (lambda: datetime.now(UTC))

    def sink(report: DeliveryReport) -> None:
        """Record one finished delivery.

        A *skipped* delivery is dropped rather than recorded: it never reached the
        network, so it has no outcome to show and no attempt for a record to
        summarise -- and it is the sender that says so, once, here, rather than
        every sink re-deciding what counts.
        """
        if report.attempts:
            log.record(report, at=stamp())

    return sink


def delivery_caveats(
    *,
    log: DeliveryLog,
    shown: int,
    dispatch_configured: bool,
) -> list[str]:
    """What a reader must know to read a delivery list honestly (R-70, R-74).

    Args:
        log: the log the read came from, for its counts.
        shown: how many records this response carries.
        dispatch_configured: whether this deployment has a sender at all.

    Returns:
        The sentences, in the order a reader needs them: what a record is and is
        not, how much of the log this response holds, and -- when nothing has
        ever been attempted -- whether that is silence or a missing caller.
    """
    caveats = [
        "A record names the target, the attempts made, the outcome and the status code. "
        "It never carries the URL, the signing secret or alert content: an operator who "
        "needs the payload joins the receiver's log by the delivery id.",
        "Delivery records live in this process's memory rather than in a store: a restart "
        f"forgets them, and only the newest {DEFAULT_MAX_RECORDS} attempts are kept.",
    ]
    if log.recorded > shown:
        caveats.append(
            f"{shown} of the {log.recorded} attempts this process has recorded are shown "
            "here, newest first."
        )
    if log.recorded == 0:
        if dispatch_configured:
            caveats.append(
                "Nothing has been attempted in this process. A delivery is made when an "
                "alert is dispatched to a target, so a deployment with no alerts since it "
                "started has an empty list rather than a failing endpoint."
            )
        else:
            caveats.append(
                "Nothing has been attempted in this process, and nothing can be yet: this "
                "deployment has no outbound transport configured, so the delivery "
                "machinery exists and records every attempt it makes while no caller is "
                "wired to it. The test action reports the same refusal."
            )
    return caveats
