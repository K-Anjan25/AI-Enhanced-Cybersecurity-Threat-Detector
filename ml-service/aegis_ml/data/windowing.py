"""Sliding windows over telemetry streams (T-108).

A window is the unit both models consume: ``architecture.md`` §7.1 feeds
`FlowNet` 50 consecutive flows from one entity, and §7.2 feeds `LogNet` 200
consecutive log lines from one host+service.

Two triggers close a window
---------------------------
**count** — the window reached its size, and **inactivity** — the gap to the
next record exceeded a threshold, so the burst is over and the records after it
belong to a different story. Inactivity is applied first: the per-key stream is
cut into bursts, and windows never span a burst boundary.

Which entity a flow window is keyed on (D-013)
----------------------------------------------
Reconnaissance and exfiltration are properties of a *source*, so the default key
is `WindowKey.SOURCE`. A volumetric flood is a property of a *destination* —
spread one flood across forty sources and each per-source window holds about one
flow, which is why `WindowKey.DESTINATION` exists. The key is a parameter rather
than a constant because the honest answer to "which entity?" is "whichever one
the behaviour being detected is a property of".

Determinism
-----------
Window boundaries are a pure function of the input stream, the size, the stride
and the inactivity threshold. Keys are processed in sorted order so the output
does not depend on dict iteration order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from aegis_ml.data.records import FlowRecord, LogRecord

#: Default flow window size — `architecture.md` §7.1.
FLOW_WINDOW_SIZE = 50

#: Default log window size — `architecture.md` §7.2.
LOG_WINDOW_SIZE = 200

#: Separator used when a key is composed of more than one field.
KEY_SEPARATOR = "|"


class WindowKey(StrEnum):
    """The entity dimension a flow window is keyed on. See D-013."""

    SOURCE = "source"
    DESTINATION = "destination"


class WindowTrigger(StrEnum):
    """Why a window closed. Recorded on every window so callers can filter."""

    COUNT = "count"
    INACTIVITY = "inactivity"
    END_OF_STREAM = "end_of_stream"


class _Timestamped(Protocol):
    """The only thing windowing needs from a record.

    Declared as a read-only property: the records are frozen, so the pydantic
    mypy plugin exposes their fields as read-only properties, and a mutable
    attribute member would not accept them.
    """

    @property
    def timestamp(self) -> datetime:
        """Event time of the record."""
        ...


R = TypeVar("R", bound=_Timestamped)


@dataclass(frozen=True)
class Window(Generic[R]):
    """One window: a contiguous, single-entity run of records.

    ``size`` is the configured window size, kept so :attr:`is_complete` can be
    answered without the caller remembering the configuration.
    """

    key: str
    key_kind: str
    index: int
    size: int
    trigger: WindowTrigger
    records: tuple[R, ...]

    @property
    def start(self) -> datetime:
        """Timestamp of the first record."""
        return self.records[0].timestamp

    @property
    def end(self) -> datetime:
        """Timestamp of the last record."""
        return self.records[-1].timestamp

    @property
    def is_complete(self) -> bool:
        """Whether the window holds a full ``size`` records.

        A partial window is a real thing to score in a live stream but a poor
        training example, so the distinction is exposed rather than hidden.
        """
        return len(self.records) == self.size


def flow_key(record: FlowRecord, key: WindowKey) -> str:
    """Return the windowing key for one flow record."""
    return str(record.src_ip if key is WindowKey.SOURCE else record.dst_ip)


def log_key(record: LogRecord) -> str:
    """Return the windowing key for one log line: host plus service."""
    return f"{record.host}{KEY_SEPARATOR}{record.service}"


def window_flows(
    flows: Sequence[FlowRecord],
    *,
    size: int = FLOW_WINDOW_SIZE,
    stride: int | None = None,
    inactivity: timedelta | None = None,
    key: WindowKey = WindowKey.SOURCE,
) -> tuple[Window[FlowRecord], ...]:
    """Cut a flow stream into single-entity windows.

    ``stride`` defaults to ``size``: tumbling, non-overlapping windows.
    Overlap is opt-in because overlapping windows count the same event in
    several windows, which inflates any metric computed per window (D-009).

    Raises:
        ValueError: if the configuration is unusable, or the stream is not in
            arrival order. An unordered stream has no well-defined "consecutive
            50 flows", so it is refused rather than silently sorted (R-06).
    """
    _validate(size, stride)
    step = size if stride is None else stride
    _require_arrival_order([record.timestamp for record in flows], "flow")
    groups: dict[str, list[FlowRecord]] = {}
    for record in flows:
        groups.setdefault(flow_key(record, key), []).append(record)
    return _build(groups, size, step, inactivity, key.value)


def window_logs(
    logs: Sequence[LogRecord],
    *,
    size: int = LOG_WINDOW_SIZE,
    stride: int | None = None,
    inactivity: timedelta | None = None,
) -> tuple[Window[LogRecord], ...]:
    """Cut a log stream into per host+service windows.

    Raises:
        ValueError: as :func:`window_flows`.
    """
    _validate(size, stride)
    step = size if stride is None else stride
    _require_arrival_order([record.timestamp for record in logs], "log")
    groups: dict[str, list[LogRecord]] = {}
    for record in logs:
        groups.setdefault(log_key(record), []).append(record)
    return _build(groups, size, step, inactivity, "host+service")


def _validate(size: int, stride: int | None) -> None:
    """Reject a window configuration that cannot produce usable windows."""
    if size <= 0:
        raise ValueError(f"window size must be positive, got {size}")
    if stride is not None:
        if stride <= 0:
            raise ValueError(f"stride must be positive, got {stride}")
        if stride > size:
            raise ValueError(
                f"stride {stride} exceeds window size {size}, which would drop records"
            )


def _require_arrival_order(stamps: Sequence[datetime], kind: str) -> None:
    """Assert the stream never runs backwards in time (R-06)."""
    for earlier, later in zip(stamps, stamps[1:], strict=False):
        if later < earlier:
            raise ValueError(
                f"{kind} stream must be in arrival order; "
                f"{later.isoformat()} follows {earlier.isoformat()}"
            )


def _segment(records: Sequence[R], inactivity: timedelta | None) -> list[tuple[list[R], bool]]:
    """Cut one key's records into bursts separated by inactivity gaps.

    Returns each burst with a flag saying whether it ended because of an
    inactivity gap rather than the end of the stream.
    """
    if inactivity is None or len(records) < 2:
        return [(list(records), False)]

    bursts: list[tuple[list[R], bool]] = []
    current: list[R] = [records[0]]
    for previous, record in zip(records, records[1:], strict=False):
        if record.timestamp - previous.timestamp > inactivity:
            bursts.append((current, True))
            current = [record]
        else:
            current.append(record)
    bursts.append((current, False))
    return bursts


def _build(
    groups: dict[str, list[R]],
    size: int,
    stride: int,
    inactivity: timedelta | None,
    key_kind: str,
) -> tuple[Window[R], ...]:
    """Slide across every key's bursts and emit windows.

    Keys are visited in sorted order, so the result does not depend on the
    insertion order of the input beyond the arrival order already required.
    """
    windows: list[Window[R]] = []
    for key in sorted(groups):
        index = 0
        for burst, cut_by_inactivity in _segment(groups[key], inactivity):
            for start, is_last in _starts(len(burst), size, stride):
                records = burst[start : start + size]
                if is_last and cut_by_inactivity:
                    trigger = WindowTrigger.INACTIVITY
                elif len(records) < size:
                    trigger = WindowTrigger.END_OF_STREAM
                else:
                    trigger = WindowTrigger.COUNT
                windows.append(
                    Window(
                        key=key,
                        key_kind=key_kind,
                        index=index,
                        size=size,
                        trigger=trigger,
                        records=tuple(records),
                    )
                )
                index += 1
    return tuple(windows)


def _starts(count: int, size: int, stride: int) -> list[tuple[int, bool]]:
    """Return the start offsets of every window over ``count`` records.

    Full windows start at 0, ``stride``, ``2*stride`` and so on while a whole
    window still fits. Whatever is left over becomes one final short window
    rather than a shifted full one, so window boundaries stay easy to reason
    about and to test. Each offset carries whether it is the last in the burst.
    """
    if count == 0:
        return []
    if count < size:
        return [(0, True)]

    offsets = list(range(0, count - size + 1, stride))
    covered = offsets[-1] + size
    if covered < count:
        offsets.append(covered)
    return [(offset, position == len(offsets) - 1) for position, offset in enumerate(offsets)]
