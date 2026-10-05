"""Consumer-group lag as a Prometheus gauge (T-306).

Lag is exported per `(group, topic, partition)` rather than as one number for
the group. A single aggregate hides the case that actually matters: one
partition stuck while the others keep up, which is exactly what a poison record
or a skewed key distribution looks like, and it averages away to nothing.

The gauge is a module-level singleton because Prometheus collects by scraping
process state; constructing a new Gauge per measurement would either duplicate
the metric or fail to register.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Gauge

__all__ = ["CONSUMER_LAG", "observe_lag", "observe_lags", "reset_lag"]

CONSUMER_LAG = Gauge(
    "aegis_kafka_consumer_lag",
    "Records a consumer group has yet to read, per partition.",
    labelnames=("group", "topic", "partition"),
)


def lag_from_offsets(committed: int, end_offset: int) -> int:
    """How far behind a consumer is.

    Never negative. A committed offset ahead of the log end happens legitimately
    after retention deletes records or a topic is recreated, and reporting a
    negative lag would make a dashboard show the consumer as "ahead" when it has
    in fact lost its place.
    """
    return max(0, end_offset - committed)


def observe_lag(group: str, topic: str, partition: int, lag: int) -> None:
    """Record one partition's lag."""
    CONSUMER_LAG.labels(group=group, topic=topic, partition=str(partition)).set(lag)


def observe_lags(group: str, topic: str, lags: dict[int, int]) -> None:
    """Record every partition's lag from one poll of the group's offsets."""
    for partition, lag in lags.items():
        observe_lag(group, topic, partition, lag)


def reset_lag() -> None:
    """Clear all lag series. Used by tests to isolate measurements."""
    CONSUMER_LAG.clear()


def current_lag(group: str, topic: str, partition: int) -> float | None:
    """The last observed lag for one partition, or None if never observed.

    Read through the registry rather than the metric object, so this observes
    what a Prometheus scrape would see and not an internal attribute.
    """
    return REGISTRY.get_sample_value(
        "aegis_kafka_consumer_lag",
        {"group": group, "topic": topic, "partition": str(partition)},
    )
