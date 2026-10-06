"""The log tail's fold, bounds and caveats (T-407).

Everything worth being sure of lives here rather than on the wire: what a cluster
counts, what a key is, what eviction does, and what a response says about the lines
it could not show. The route tests are in ``test_logs_api.py``, which asserts the
HTTP contract over this service.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.schemas.ingest import LogLevel, LogRecordIn
from app.services.log_tail import (
    MAX_CLUSTER_LIMIT,
    MAX_LINE_LIMIT,
    MESSAGE_KEY_PREFIX,
    LogTail,
    LogWindow,
    cluster_key,
    level_rank,
    message_key,
)

START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)


class Clock:
    """A clock a test drives, so "aged out" is a fact rather than a sleep."""

    def __init__(self, at: datetime = START) -> None:
        """Start at ``at``; only a test moves it."""
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def advance(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)


def line(
    *,
    offset: float = 0.0,
    message: str = "connection refused to db-1",
    template_id: str | None = "t-1",
    level: LogLevel = LogLevel.ERROR,
    host: str = "web-1",
    service: str = "api",
    parameters: dict[str, str] | None = None,
) -> LogRecordIn:
    """One ``log@1`` line, with everything a cluster row reads overridable."""
    return LogRecordIn(
        timestamp=START + timedelta(seconds=offset),
        host=host,
        service=service,
        level=level,
        message=message,
        template_id=template_id,
        parameters=parameters if parameters is not None else {"db": "db-1"},
    )


def tail(**overrides: object) -> LogTail:
    """A tail with a driven clock and short bounds, so eviction is testable."""
    options: dict[str, object] = {"max_lines": 100, "max_age_seconds": 60.0, "clock": Clock()}
    options.update(overrides)
    return LogTail(**options)  # type: ignore[arg-type]


def window(*, start: datetime = START, seconds: float = 60.0, **filters: object) -> LogWindow:
    return LogWindow(start=start, end=start + timedelta(seconds=seconds), **filters)  # type: ignore[arg-type]


# --- the key -----------------------------------------------------------------


def test_a_line_with_a_template_id_clusters_by_it() -> None:
    assert cluster_key(line(template_id="t-42")) == "t-42"


def test_a_blank_template_id_is_not_a_cluster_name() -> None:
    """A collector sending "" means "not mined"; a cluster of "" would gather all of them."""
    empty = line(template_id="", message="one")
    spaces = line(template_id="   ", message="one")

    # Both fall back to the message digest, so two untemplated *different* messages
    # do not share a row and one untemplated message does.
    assert cluster_key(empty) == message_key("one")
    assert cluster_key(spaces) == message_key("one")
    assert cluster_key(line(template_id=None, message="two")) != cluster_key(empty)


def test_the_message_key_is_a_digest_so_content_stays_out_of_urls() -> None:
    key = message_key("user alice logged in from 10.0.0.7")

    assert key.startswith(MESSAGE_KEY_PREFIX)
    assert "alice" not in key
    assert "10.0.0.7" not in key
    assert len(key) == len(MESSAGE_KEY_PREFIX) + 12
    # Stable for the same message, which is all a key has to be.
    assert key == message_key("user alice logged in from 10.0.0.7")


def test_every_level_has_a_rank_and_critical_is_the_worst() -> None:
    assert level_rank(LogLevel.DEBUG) < level_rank(LogLevel.INFO)
    assert level_rank(LogLevel.ERROR) < level_rank(LogLevel.CRITICAL)
    assert max(LogLevel, key=level_rank) is LogLevel.CRITICAL


# --- the fold ----------------------------------------------------------------


def test_identical_lines_collapse_into_one_row_with_a_count() -> None:
    """The acceptance criterion, at ten thousand lines."""
    subject = tail(max_lines=20_000)
    subject.append([line(offset=i / 100) for i in range(10_000)])

    folded = subject.clusters(window(seconds=120))

    assert len(folded.clusters) == 1
    assert folded.clusters[0].count == 10_000
    assert folded.lines_seen == 10_000


def test_a_cluster_carries_its_span_levels_hosts_and_newest_sample() -> None:
    subject = tail()
    subject.append(
        [
            line(offset=0, level=LogLevel.WARNING, host="web-1", parameters={"db": "old"}),
            line(
                offset=5, level=LogLevel.ERROR, host="web-2", message="connection refused to db-2"
            ),
            line(offset=9, level=LogLevel.INFO, host="web-1"),
        ]
    )

    cluster = subject.clusters(window()).clusters[0]

    assert cluster.key == "t-1"
    assert cluster.template_id == "t-1"
    assert cluster.count == 3
    assert cluster.first_seen == START
    assert cluster.last_seen == START + timedelta(seconds=9)
    assert cluster.worst_level is LogLevel.ERROR
    assert cluster.levels == {"error": 1, "info": 1, "warning": 1}
    assert cluster.hosts == ["web-1", "web-2"]
    assert cluster.services == ["api"]
    # The newest line, not the first: a sample that never changed would show a
    # parameter value from the beginning of the window.
    assert cluster.sample_message == "connection refused to db-1"
    assert cluster.parameters == {"db": "db-1"}


def test_clusters_are_ordered_by_count_then_by_key() -> None:
    subject = tail()
    subject.append(
        [
            line(template_id="b", offset=0),
            line(template_id="a", offset=1),
            line(template_id="a", offset=2),
            line(template_id="a", offset=3),
            line(template_id="b", offset=4),
            line(template_id="c", offset=5),
        ]
    )

    folded = subject.clusters(window())

    # a=3, then b=2 and c=1 -- and ties break on the key, so two reads of the same
    # tail cannot disagree.
    assert [(cluster.key, cluster.count) for cluster in folded.clusters] == [
        ("a", 3),
        ("b", 2),
        ("c", 1),
    ]


def test_a_line_outside_the_half_open_window_is_not_counted() -> None:
    subject = tail(max_age_seconds=600)
    subject.append([line(offset=0), line(offset=60), line(offset=120)])

    folded = subject.clusters(window(seconds=60))

    # [10:00:00, 10:01:00): the line at exactly 10:01:00 belongs to the next window.
    assert folded.lines_seen == 1
    assert folded.clusters[0].count == 1


def test_the_filters_narrow_what_the_fold_sees() -> None:
    subject = tail(max_age_seconds=600)
    subject.append(
        [
            line(offset=0, host="web-1", service="api", level=LogLevel.ERROR),
            line(offset=1, host="web-2", service="api", level=LogLevel.INFO),
            line(offset=2, host="web-1", service="worker", level=LogLevel.ERROR),
        ]
    )

    by_host = subject.clusters(window(seconds=600, host="web-1"))
    by_service = subject.clusters(window(seconds=600, service="worker"))
    by_level = subject.clusters(window(seconds=600, level=LogLevel.INFO))

    assert by_host.lines_seen == 2
    assert by_service.lines_seen == 1
    assert by_level.lines_seen == 1


def test_a_key_filter_selects_exactly_the_cluster_it_names() -> None:
    subject = tail(max_age_seconds=600)
    subject.append([line(template_id="t-1", offset=0), line(template_id="t-2", offset=1)])

    folded = subject.clusters(window(seconds=600, key="t-2"))

    assert [cluster.key for cluster in folded.clusters] == ["t-2"]


def test_an_untemplated_key_filter_matches_by_digest() -> None:
    subject = tail(max_age_seconds=600)
    subject.append(
        [
            line(template_id=None, message="disk full on /var", offset=0),
            line(template_id=None, message="disk full on /var", offset=1),
            line(template_id=None, message="disk full on /tmp", offset=2),
        ]
    )

    folded = subject.clusters(window(seconds=600, key=message_key("disk full on /var")))

    assert folded.lines_seen == 2
    assert folded.clusters[0].count == 2
    assert folded.clusters[0].template_id is None


def test_a_template_id_that_looks_like_a_digest_is_still_a_template() -> None:
    """The key is resolved as a template first, so the digest prefix cannot shadow one."""
    subject = tail(max_age_seconds=600)
    lookalike = f"{MESSAGE_KEY_PREFIX}deadbeefcafe"
    subject.append(
        [
            line(template_id=lookalike, message="a", offset=0),
            line(template_id=None, message="a", offset=1),
        ]
    )

    folded = subject.clusters(window(seconds=600, key=lookalike))

    assert folded.lines_seen == 1
    assert folded.clusters[0].template_id == lookalike


def test_the_cluster_limit_truncates_the_list_and_says_so() -> None:
    subject = tail()
    subject.append([line(template_id=f"t-{index}", offset=index) for index in range(5)])

    folded = subject.clusters(window(), limit=2)

    assert len(folded.clusters) == 2
    assert folded.clusters_seen == 5
    assert folded.clusters_truncated is True
    assert any("row limit" in caveat for caveat in folded.caveats)


def test_a_limit_below_one_is_a_programming_error_not_an_empty_list() -> None:
    subject = tail()
    subject.append([line()])

    with pytest.raises(ValueError, match="limit"):
        subject.clusters(window(), limit=0)
    with pytest.raises(ValueError, match="limit"):
        subject.lines(window(), limit=0)


def test_the_row_limits_are_caps_a_panel_can_live_with() -> None:
    assert MAX_CLUSTER_LIMIT >= 100
    assert MAX_LINE_LIMIT >= MAX_CLUSTER_LIMIT


# --- the raw lines -----------------------------------------------------------


def test_raw_lines_come_back_oldest_first() -> None:
    subject = tail(max_age_seconds=600)
    subject.append([line(offset=20), line(offset=0), line(offset=10)])

    read = subject.lines(window(seconds=600))

    assert [entry.timestamp for entry in read.lines] == [
        START,
        START + timedelta(seconds=10),
        START + timedelta(seconds=20),
    ]
    assert read.lines_seen == 3
    assert read.lines_truncated is False


def test_a_truncated_raw_read_keeps_the_newest_lines_and_says_so() -> None:
    """The interesting end of a tail is its newest; a silent cut there would hide it."""
    subject = tail(max_age_seconds=600)
    subject.append([line(offset=index) for index in range(10)])

    read = subject.lines(window(seconds=600), limit=3)

    assert [entry.timestamp for entry in read.lines] == [
        START + timedelta(seconds=7),
        START + timedelta(seconds=8),
        START + timedelta(seconds=9),
    ]
    assert read.lines_seen == 10
    assert read.lines_truncated is True
    assert any("row limit" in caveat for caveat in read.caveats)


def test_a_raw_line_carries_the_key_the_fold_used() -> None:
    subject = tail()
    subject.append([line(template_id=None, message="tls handshake failed")])

    read = subject.lines(window())

    assert read.lines[0].key == message_key("tls handshake failed")
    assert read.lines[0].template_id is None


# --- the bounds --------------------------------------------------------------


def test_the_tail_keeps_at_most_max_lines_and_counts_what_it_dropped() -> None:
    subject = tail(max_lines=3, max_age_seconds=600)
    subject.append([line(offset=index) for index in range(6)])

    retained_from, retained_to, held, dropped = subject.retention()

    assert held == 3
    assert dropped == 3
    assert retained_from == START + timedelta(seconds=3)
    assert retained_to == START + timedelta(seconds=5)


def test_a_line_older_than_the_age_bound_is_evicted() -> None:
    clock = Clock()
    subject = LogTail(max_lines=100, max_age_seconds=30.0, clock=clock)
    subject.append([line(offset=0), line(offset=10), line(offset=20)])

    # The bound is measured from the clock, not from the newest line: at 35 s the
    # floor is 5 s, so the line at 0 is gone and the two after it stay.
    clock.advance(35)

    retained_from, retained_to, held, dropped = subject.retention()
    assert held == 2
    assert dropped == 1
    assert retained_from == START + timedelta(seconds=10)
    assert retained_to == START + timedelta(seconds=20)


def test_reading_does_not_evict_more_than_the_bounds_say() -> None:
    """A read is not a reason to lose lines: same bounds, same answer, twice."""
    clock = Clock()
    subject = LogTail(max_lines=10, max_age_seconds=60.0, clock=clock)
    subject.append([line(offset=index) for index in range(5)])

    first = subject.clusters(window(seconds=60))
    clock.advance(1)
    second = subject.clusters(window(seconds=60))

    assert first.retained_lines == second.retained_lines == 5
    assert second.dropped_lines == 0


def test_a_line_from_the_future_is_kept_rather_than_evicted_by_a_skewed_clock() -> None:
    """A host whose clock runs ahead is a fact about the host, not a line to drop."""
    subject = tail(max_age_seconds=60)

    subject.append([line(offset=600)])

    assert len(subject) == 1
    _, retained_to, _held, dropped = subject.retention()
    assert retained_to == START + timedelta(seconds=600)
    assert dropped == 0


def test_a_bound_of_zero_is_refused_rather_than_silently_disabling_the_tail() -> None:
    with pytest.raises(ValueError, match="max_lines"):
        LogTail(max_lines=0, max_age_seconds=60)
    with pytest.raises(ValueError, match="max_age_seconds"):
        LogTail(max_lines=10, max_age_seconds=0)


def test_appending_nothing_is_not_an_eviction_pass() -> None:
    subject = tail()

    assert subject.append([]) == 0
    assert len(subject) == 0


# --- the caveats -------------------------------------------------------------


def test_every_read_says_the_tail_is_not_a_store() -> None:
    subject = tail()
    subject.append([line()])

    caveats = " ".join(subject.clusters(window()).caveats)

    assert "not a store" in caveats
    assert "1,000 lines or 1 minutes" not in caveats  # the numbers come from the bounds


def test_an_empty_response_says_why_it_is_empty() -> None:
    """R-70: an empty screen is never a silent success."""
    never_filled = tail().clusters(window())
    assert any("nothing to show" in caveat for caveat in never_filled.caveats)

    aged_out = tail(max_age_seconds=60)
    aged_out.append([line(offset=0)])
    later = age_out(aged_out)
    stale = aged_out.clusters(window(start=later, seconds=60))
    # Aged out is its own sentence: "nothing was ever accepted" would be a
    # different, and untrue, claim about the same empty screen.
    assert any("aged out" in caveat for caveat in stale.caveats)


def age_out(subject: LogTail) -> datetime:
    """Read the tail past its age bound from the outside, returning the new clock."""
    clock = subject._clock  # noqa: SLF001 - the fixture drives the tail's own clock
    assert isinstance(clock, Clock)
    clock.advance(600)
    return clock.at


def test_a_filter_that_removed_everything_is_distinguished_from_an_empty_tail() -> None:
    subject = tail()
    subject.append([line(offset=0, host="web-1")])

    folded = subject.clusters(window(host="web-9"))

    # The window does hold a line; the filter is what removed it. Saying "nothing
    # has arrived" here would send an analyst to the collector instead of the filter.
    assert any("Nothing matched these filters" in caveat for caveat in folded.caveats)
    assert not any("Nothing has arrived" in caveat for caveat in folded.caveats)


def test_a_window_that_falls_between_retained_lines_says_which_it_is() -> None:
    subject = tail(max_age_seconds=600)
    subject.append([line(offset=0), line(offset=400)])

    folded = subject.clusters(window(start=START + timedelta(seconds=200), seconds=100))

    assert any("falls between them" in caveat for caveat in folded.caveats)


def test_untemplated_lines_are_counted_in_the_caveats() -> None:
    subject = tail()
    subject.append([line(template_id=None, offset=0), line(template_id="t-1", offset=1)])

    folded = subject.clusters(window())

    assert any("carry no template id" in caveat for caveat in folded.caveats)


def test_the_severity_a_cluster_carries_is_named_as_a_level_not_a_score() -> None:
    """The honest half of design.md §4.5: no log model is served in this build."""
    subject = tail()
    subject.append([line()])

    caveats = " ".join(subject.clusters(window()).caveats)

    assert "not a model's anomaly score" in caveats


def test_two_messages_differing_only_in_case_are_two_clusters() -> None:
    """A digest key must not fold distinct messages together.

    Hashing a lowercased message would cluster ``Disk full`` with ``disk full`` --
    two lines a reader would want to see separately, quietly sharing one count.
    """
    subject = tail()
    subject.append([line(template_id=None, message="Disk full on /var", offset=0)])
    subject.append([line(template_id=None, message="disk full on /var", offset=1)])

    folded = subject.clusters(window())

    assert len(folded.clusters) == 2
    assert {cluster.count for cluster in folded.clusters} == {1}


def test_the_cluster_order_does_not_depend_on_arrival_order() -> None:
    """Two templates with an equal count are ordered by key, not by arrival.

    Otherwise the same tail reads differently after a retry, and a screen comparing
    two reads sees rows swap places.
    """
    forwards = tail()
    forwards.append([line(template_id="t-a", offset=0), line(template_id="t-b", offset=1)])
    backwards = tail()
    backwards.append([line(template_id="t-b", offset=1), line(template_id="t-a", offset=0)])

    assert [cluster.key for cluster in forwards.clusters(window()).clusters] == [
        "t-a",
        "t-b",
    ]
    assert [cluster.key for cluster in backwards.clusters(window()).clusters] == [
        "t-a",
        "t-b",
    ]


def test_a_line_exactly_at_the_age_bound_is_still_held() -> None:
    """“Past the age bound” evicts, so the bound itself is a line a reader can see.

    The distinction is a second of a busy minute: an off-by-one here drops the very
    line at the edge of the window a reader is looking at. Eviction happens when the
    next batch arrives, so that is what the test drives.
    """
    clock = Clock()
    subject = tail(max_age_seconds=60.0, clock=clock)
    subject.append([line(offset=-60)])

    # Exactly at the bound: held.
    assert len(subject) == 1
    assert subject.dropped() == 0

    clock.advance(1)
    subject.append([line(offset=1, message="later")])

    # Now one second past it, and the new batch is what notices.
    assert [record.message for record in subject.lines(window(seconds=120)).lines] == ["later"]
    assert subject.dropped() == 1


def test_the_level_histogram_is_ordered_least_severe_first() -> None:
    """The histogram's key order is published, not whatever the fold inserted.

    A reader scanning the object should meet the levels least severe first, like every
    other level listing in the product.
    """
    subject = tail()
    subject.append(
        [
            line(offset=0, level=LogLevel.INFO),
            line(offset=1, level=LogLevel.ERROR),
            line(offset=2, level=LogLevel.INFO),
        ]
    )

    (cluster,) = subject.clusters(window()).clusters

    # By rank, not alphabetically: sorting the keys would publish `critical` before
    # `debug`, which is a level listing in no order at all.
    assert list(cluster.levels) == ["info", "error"]
    assert cluster.levels == {"info": 2, "error": 1}
