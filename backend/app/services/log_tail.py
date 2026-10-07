"""The log tail: the lines this process accepted, folded into clusters (T-407).

design.md §4.5 asks for a streaming tail in which identical lines collapse into one
row with a count, expandable back to the raw lines. Two facts about this build
decide the shape of the module:

* **A tail, not the store.** The ingest route validates a batch, hands it to the
  broker for scoring, and keeps a copy here so the explorer has something to read
  *now*: this is a bounded in-process view that lives and dies with the process.
  T-419 added the persistent alternative (the ``log_events`` table, read through
  :mod:`app.services.log_store`) and a deployment that configures it answers from
  there instead; this module is what a deployment without a database has, and every
  response says which of the two answered (R-70).
* **Clustering is a read-time fold, not a write-time index.** ``log@1`` carries
  ``template_id``, mined by the collector before the wire (T-104's miner), so the
  cluster key is the template id when there is one. A line without one cannot be given
  a mined template here — mining belongs to the ML service and this image does not
  install it — so it groups by a digest of its exact message. Both cases collapse
  *identical* lines, which is the behaviour the screen promises; the digest also keeps
  log content out of URLs, query strings and access logs (R-58).

The bounds are the feature rather than a limitation to apologise for: a tail that grew
without limit would be a log store nobody chose. The two questions a bounded view
raises — how far back it reaches, and how much has aged out — are fields on every
response, and the fold reports how many lines it read so a count can never be mistaken
for the whole stream.

**What this module deliberately does not do.** It does not score a template. The
severity a cluster carries is the worst ``level`` among its lines, which is data; the
anomaly signal design.md §4.5 colours would be a model's, and no log model is served in
this build at all. It does not link a cluster to an alert either: an alert's evidence
is a window identity, not a set of lines, so there is nothing to join on yet — the
screen says "no link" rather than inventing one.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta

from app.schemas.ingest import LogLevel, LogRecordIn
from app.schemas.logs import LogClusterOut, LogLineOut, LogLinesOut, LogTailOut
from app.services.log_keys import MESSAGE_KEY_PREFIX, cluster_key, message_key

__all__ = [
    "DEFAULT_CLUSTER_LIMIT",
    "DEFAULT_LINE_LIMIT",
    "MAX_CLUSTER_LIMIT",
    "MAX_LINE_LIMIT",
    "MESSAGE_KEY_PREFIX",
    "LogTail",
    "LogWindow",
    "cluster_key",
    "level_rank",
    "message_key",
]

#: How many clusters one read returns unless the caller asks for fewer.
DEFAULT_CLUSTER_LIMIT = 100
#: The ceiling on clusters per read. A tail of 20,000 lines cannot produce more
#: distinct templates than it holds lines, and a screen cannot render them anyway.
MAX_CLUSTER_LIMIT = 500
#: How many raw lines one expansion returns unless the caller asks for fewer.
DEFAULT_LINE_LIMIT = 200
#: The ceiling on raw lines per read: opening a cluster is a look, not an export.
MAX_LINE_LIMIT = 1_000
#: Levels in the order ``log@1`` defines them, least severe first.
_LEVEL_ORDER: tuple[LogLevel, ...] = (
    LogLevel.DEBUG,
    LogLevel.INFO,
    LogLevel.WARNING,
    LogLevel.ERROR,
    LogLevel.CRITICAL,
)
_RANK: dict[LogLevel, int] = {level: index for index, level in enumerate(_LEVEL_ORDER)}


def _utcnow() -> datetime:
    """The clock, in UTC. A function so tests can drive it."""
    return datetime.now(UTC)


def level_rank(level: LogLevel) -> int:
    """Where one level sits in ``log@1``'s order, least severe first."""
    return _RANK[level]


class LogWindow:
    """What one read asks for: a time window and the filters within it.

    A window is required rather than defaulted, and its span is checked by the
    caller against the tail's retention — R-34's "bounded by construction",
    applied to a stream where the bound on offer is the retention rather than a
    day. The window is half-open, ``[start, end)``, like every other window in
    this codebase, so two adjacent reads cannot both claim the boundary line.
    """

    __slots__ = ("end", "host", "key", "level", "service", "start")

    def __init__(
        self,
        *,
        start: datetime,
        end: datetime,
        key: str | None = None,
        host: str | None = None,
        service: str | None = None,
        level: LogLevel | None = None,
    ) -> None:
        """Build a half-open window, refusing one that cannot contain anything.

        Raises:
            ValueError: if the window is inverted or empty. The route turns this
                into a 400; a service called directly gets a loud failure rather
                than a read that silently matches nothing.
        """
        if end <= start:
            msg = "a log window must end after it starts"
            raise ValueError(msg)
        self.start = start
        self.end = end
        self.key = key
        self.host = host
        self.service = service
        self.level = level

    def contains(self, record: LogRecordIn) -> bool:
        """Whether one line is inside this window and passes its filters.

        A line whose template id is present must also *match* the key, and a line
        without one is matched by digest: resolving a key as a template first is
        what keeps a template id that happens to look like a digest from being
        read as a message search.
        """
        if not (self.start <= record.timestamp < self.end):
            return False
        if self.host is not None and record.host != self.host:
            return False
        if self.service is not None and record.service != self.service:
            return False
        if self.level is not None and record.level is not self.level:
            return False
        return self.key is None or cluster_key(record) == self.key


class LogTail:
    """A bounded, in-process tail of accepted log lines.

    The store is a deque behind a lock. Ingest is the only writer and it appends a
    whole batch at once; reads filter, fold and sort a copy of the slice they need,
    so a read never holds the lock while it renders and never sees a half-appended
    batch.
    """

    __slots__ = ("_clock", "_dropped", "_lines", "_lock", "_max_age", "_max_lines")

    def __init__(
        self,
        *,
        max_lines: int,
        max_age_seconds: float,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Build a tail that keeps at most ``max_lines`` lines and ``max_age_seconds``.

        Both bounds are required: a tail with only one of them is either unbounded
        in time or unbounded in size, and the point of the thing is that it is
        bounded in both.

        Raises:
            ValueError: if either bound is not positive. A configured zero would
                turn the tail into a silent no-op.
        """
        if max_lines < 1:
            msg = f"max_lines must be at least 1, got {max_lines}"
            raise ValueError(msg)
        if max_age_seconds <= 0:
            msg = f"max_age_seconds must be positive, got {max_age_seconds}"
            raise ValueError(msg)
        self._max_lines = max_lines
        self._max_age = timedelta(seconds=max_age_seconds)
        self._clock = clock if clock is not None else _utcnow
        self._lock = threading.Lock()
        self._lines: deque[LogRecordIn] = deque()
        self._dropped = 0

    @property
    def max_lines(self) -> int:
        """How many lines this tail keeps at most."""
        return self._max_lines

    @property
    def max_age_seconds(self) -> float:
        """How long, in seconds, a line stays in the tail."""
        return self._max_age.total_seconds()

    def __len__(self) -> int:
        """How many lines are held right now."""
        with self._lock:
            return len(self._lines)

    def dropped(self) -> int:
        """How many lines have been evicted since the process started.

        Reported rather than hidden: a caller comparing the tail with a collector's
        own count needs to know the difference is aged-out lines, not a bug.
        """
        with self._lock:
            return self._dropped

    def append(self, records: Sequence[LogRecordIn]) -> int:
        """Keep a batch of accepted lines, evicting whatever the bounds exclude.

        Returns:
            How many of the given records are now held. Only *accepted* records
            reach here — the ingest route calls this after validation and after
            the back-pressure check — so the tail never shows a line the API
            refused.
        """
        if not records:
            return 0
        now = self._clock()
        with self._lock:
            self._lines.extend(records)
            self._evict(now)
            return len(records)

    def retention(self) -> tuple[datetime | None, datetime | None, int, int]:
        """The instants the tail currently covers, its size, and what has aged out.

        The floor is the clock at read time rather than the oldest line: a tail
        that has received nothing for an hour covers no time, but it still has an
        age bound, and a caller asking "why is this empty" deserves the bound
        rather than the oldest of zero lines.
        """
        now = self._clock()
        with self._lock:
            self._evict(now)
            oldest = self._lines[0].timestamp if self._lines else None
            newest = max((record.timestamp for record in self._lines), default=None)
            return oldest, newest, len(self._lines), self._dropped

    def clusters(self, window: LogWindow, *, limit: int = DEFAULT_CLUSTER_LIMIT) -> LogTailOut:
        """Fold the window's lines into clusters, ordered by count then key.

        The fold is over every matching line, so the count on a row is the number
        of lines that arrived rather than a page of them.
        """
        if limit < 1:
            msg = f"limit must be at least 1, got {limit}"
            raise ValueError(msg)
        now = self._clock()
        with self._lock:
            self._evict(now)
            matched = [record for record in self._lines if window.contains(record)]
            present = sum(
                1 for record in self._lines if window.start <= record.timestamp < window.end
            )
            folded = _fold(matched)
            retained_from, retained_to = _retained(self._lines)
            held, dropped = len(self._lines), self._dropped

        ordered = sorted(folded.items(), key=lambda item: (-item[1].count, item[0]))
        top = ordered[:limit]
        caveats = _caveats(
            window=window,
            matched=len(matched),
            present=present,
            retained_lines=held,
            retained_from=retained_from,
            retained_to=retained_to,
            dropped=dropped,
            truncated=len(ordered) > len(top),
            untemplated=sum(1 for record in matched if not (record.template_id or "").strip()),
            max_lines=self._max_lines,
            max_age=self._max_age,
        )
        return LogTailOut(
            source="tail",
            start=window.start,
            end=window.end,
            clusters=[entry.cluster for _key, entry in top],
            lines_seen=len(matched),
            clusters_seen=len(ordered),
            clusters_truncated=len(ordered) > len(top),
            retained_from=retained_from,
            retained_to=retained_to,
            retained_lines=held,
            dropped_lines=dropped,
            caveats=caveats,
        )

    def lines(self, window: LogWindow, *, limit: int = DEFAULT_LINE_LIMIT) -> LogLinesOut:
        """The raw lines a window matches, oldest first, capped at ``limit``.

        Oldest first because expanding a cluster is reading a stack trace, and a
        trace read backwards is a different story. The cap takes the *newest*
        ``limit`` lines and says that it did: a tail's interesting end is its
        newest, and a silent truncation at the old end would hide exactly the
        lines an analyst opened the cluster to see.
        """
        if limit < 1:
            msg = f"limit must be at least 1, got {limit}"
            raise ValueError(msg)
        now = self._clock()
        with self._lock:
            self._evict(now)
            matched = [record for record in self._lines if window.contains(record)]
            present = sum(
                1 for record in self._lines if window.start <= record.timestamp < window.end
            )
            retained_from, retained_to = _retained(self._lines)
            held, dropped = len(self._lines), self._dropped

        # Ordered by instant, and stably, so equal instants keep arrival order. A
        # batch that arrives out of order would otherwise make a window read depend
        # on how the collector happened to pack it.
        ordered = sorted(matched, key=lambda record: record.timestamp)
        truncated = len(ordered) > limit
        kept = ordered[-limit:] if truncated else ordered
        caveats = _caveats(
            window=window,
            matched=len(matched),
            present=present,
            retained_lines=held,
            retained_from=retained_from,
            retained_to=retained_to,
            dropped=dropped,
            truncated=truncated,
            untemplated=0,
            max_lines=self._max_lines,
            max_age=self._max_age,
        )
        return LogLinesOut(
            source="tail",
            start=window.start,
            end=window.end,
            key=window.key,
            lines=[_line_of(record) for record in kept],
            lines_seen=len(matched),
            lines_truncated=truncated,
            retained_from=retained_from,
            retained_to=retained_to,
            retained_lines=held,
            dropped_lines=dropped,
            caveats=caveats,
        )

    def _evict(self, now: datetime) -> None:
        """Drop lines past the age bound and then past the count bound.

        Age first, so the count bound is what decides only when the tail is
        genuinely busy. Called under the lock.
        """
        floor = now - self._max_age
        while self._lines and self._lines[0].timestamp < floor:
            self._lines.popleft()
            self._dropped += 1
        while len(self._lines) > self._max_lines:
            self._lines.popleft()
            self._dropped += 1


class _Folded:
    """A cluster under construction: the counts a cluster row needs."""

    __slots__ = (
        "_first",
        "_last",
        "cluster",
        "count",
        "hosts",
        "levels",
        "services",
    )

    def __init__(self, key: str, record: LogRecordIn) -> None:
        self.count = 0
        self._first = record.timestamp
        self._last = record.timestamp
        self.levels: dict[str, int] = {}
        self.hosts: set[str] = set()
        self.services: set[str] = set()
        self.cluster = LogClusterOut(
            key=key,
            template_id=(record.template_id or "").strip() or None,
            count=0,
            first_seen=record.timestamp,
            last_seen=record.timestamp,
            worst_level=record.level,
            levels={},
            hosts=[],
            services=[],
            sample_message=record.message,
            parameters=dict(record.parameters),
        )

    def add(self, record: LogRecordIn) -> None:
        """Fold one more line in, keeping the newest line's sample and parameters."""
        self.count += 1
        self.levels[record.level.value] = self.levels.get(record.level.value, 0) + 1
        self.hosts.add(record.host)
        self.services.add(record.service)
        if record.timestamp < self._first:
            self._first = record.timestamp
        if record.timestamp >= self._last:
            self._last = record.timestamp
            self.cluster.sample_message = record.message
            self.cluster.parameters = dict(record.parameters)

    def finish(self) -> None:
        """Write the folded counts onto the row, in a stable order."""
        self.cluster.count = self.count
        self.cluster.first_seen = self._first
        self.cluster.last_seen = self._last
        # By rank, not alphabetically: sorting the keys would publish `critical`
        # before `debug`, which is a level listing in no order at all.
        order = sorted(self.levels.items(), key=lambda item: level_rank(LogLevel(item[0])))
        self.cluster.levels = dict(order)
        self.cluster.hosts = sorted(self.hosts)
        self.cluster.services = sorted(self.services)
        self.cluster.worst_level = max(
            (LogLevel(level) for level in self.levels),
            key=level_rank,
        )


def _fold(records: Iterable[LogRecordIn]) -> dict[str, _Folded]:
    """Group lines by cluster key, in first-seen order of the keys."""
    folded: dict[str, _Folded] = {}
    for record in records:
        key = cluster_key(record)
        entry = folded.get(key)
        if entry is None:
            entry = _Folded(key, record)
            folded[key] = entry
        entry.add(record)
    for entry in folded.values():
        entry.finish()
    return folded


def _line_of(record: LogRecordIn) -> LogLineOut:
    """One raw line, carrying its key so a client can group by what the server did."""
    return LogLineOut(
        timestamp=record.timestamp,
        host=record.host,
        service=record.service,
        level=record.level,
        message=record.message,
        template_id=(record.template_id or "").strip() or None,
        parameters=dict(record.parameters),
        key=cluster_key(record),
    )


def _retained(lines: Sequence[LogRecordIn]) -> tuple[datetime | None, datetime | None]:
    """The instants the held lines span, oldest and newest by timestamp."""
    if not lines:
        return None, None
    return (
        min(record.timestamp for record in lines),
        max(record.timestamp for record in lines),
    )


def _caveats(
    *,
    window: LogWindow,
    matched: int,
    present: int,
    retained_lines: int,
    retained_from: datetime | None,
    retained_to: datetime | None,
    dropped: int,
    truncated: bool,
    untemplated: int,
    max_lines: int,
    max_age: timedelta,
) -> list[str]:
    """What the caller must know to read the numbers above (R-70, R-74).

    Four different facts can make a log screen empty, and an analyst acts
    differently on each: nothing was ever accepted, everything aged out, the window
    is outside the retention, or a filter removed the lines. Saying "no results" for
    all four is how a quiet screen gets misread as a quiet system.

    Order is deliberate: the permanent shape of the thing first, then what this
    particular read did or could not do.
    """
    minutes = int(max_age.total_seconds() // 60)
    caveats = [
        (
            f"This tail holds the most recent {max_lines:,} lines or {minutes} minutes of "
            "the process that accepted them, whichever comes first. It is not a store: a "
            "restart, a second worker or an aged-out line is not shown here, and only "
            "accepted lines appear in it."
        )
    ]
    if retained_lines == 0 and dropped == 0:
        caveats.append(
            "No log line has been accepted since this process started, so the window is "
            "empty because there is nothing to show rather than because nothing matched."
        )
    elif retained_lines == 0:
        caveats.append(
            f"The tail is empty: {dropped:,} lines have aged out of the {minutes}-minute "
            "retention since this process started, and none arrived more recently."
        )
    elif present == 0:
        if retained_from is not None and window.end <= retained_from:
            caveats.append(
                f"No lines are retained at or before {window.end.isoformat()}: the oldest "
                f"line still held is from {retained_from.isoformat()}."
            )
        elif retained_to is not None and window.start >= retained_to:
            caveats.append(
                f"Nothing has arrived at or after {window.start.isoformat()}: the newest "
                f"line still held is from {retained_to.isoformat()}."
            )
        else:
            caveats.append(
                f"No line was accepted inside this window. The tail holds "
                f"{retained_lines:,} lines; this window falls between them."
            )
    elif matched == 0:
        caveats.append(
            "Nothing matched these filters, though the window does hold lines: the filter "
            "is what removed them, not the tail."
        )
    if truncated:
        caveats.append("This read hit its row limit; only the rows shown are listed.")
    if untemplated:
        caveats.append(
            f"{untemplated:,} of {matched:,} matching lines carry no template id, so they "
            "are grouped by a digest of their exact message rather than by a mined template."
        )
    caveats.append(
        "A cluster's severity is the worst level among its lines, not a model's anomaly "
        "score: no log model is served in this build, so nothing here is called anomalous."
    )
    return caveats
