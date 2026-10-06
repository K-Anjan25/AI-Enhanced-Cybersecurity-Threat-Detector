"""Prometheus metrics for the ingest-to-alert path (NFR-07, T-317).

The metric names are architecture.md §13's list, because a dashboard is written
against names and an approximation of a name is a dashboard that silently shows
nothing: ``aegis_flows_ingested_total``, ``aegis_score_latency_seconds``,
``aegis_alerts_created_total`` and ``aegis_drift_psi`` (``aegis_kafka_consumer_lag``
already exists in :mod:`app.messaging.lag`), plus the golden signals for this
process. The metrics are module-level singletons for the reason given there:
Prometheus collects by scraping process state, so a metric constructed per call
would either duplicate a series or collide on registration.

**Labels are a fixed, reviewable set.** A label is a dimension in the time series
database, so a label whose value comes from the request is a way for a client to
make the process grow without bound -- one series per path, per credential, per
source address. Every label here is either a bounded constant chosen by this code
(``modality``, ``stage``, ``severity``, ``status``) or the *route template* after
routing, and anything that matched no route is reported under one name.
:func:`metric_label_names` exists so a test can assert that set rather than
trusting a reviewer to notice a new label.

**No identifiers, no content.** Counters of numbers, histogram buckets of
durations, and a gauge of a drift statistic. Nothing here identifies a user, a
host, a token or an alert, which is what lets ``/metrics`` be readable without
disclosing the data the service exists to protect (R-58).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from prometheus_client import Counter, Gauge, Histogram

__all__ = [
    "ALERTS_CREATED",
    "DRIFT_PSI",
    "FLOWS_INGESTED",
    "HTTP_LATENCY",
    "HTTP_REQUESTS",
    "MODALITIES",
    "RECORDS_REJECTED",
    "SCORE_LATENCY",
    "UNMATCHED_ROUTE",
    "metric_label_names",
    "observe_alert_created",
    "observe_drift_psi",
    "observe_http_request",
    "observe_ingest",
    "observe_score_latency",
]

#: The route label for a request that matched no route. Every unmatched path --
#: a typo, a scanner probing for `/admin`, a fuzzer -- collapses into this one
#: series instead of one series each.
UNMATCHED_ROUTE: Final = "unmatched"

#: Modality label values. Kept here so a caller cannot invent a third.
MODALITIES: Final[tuple[str, ...]] = ("flow", "log")

FLOWS_INGESTED = Counter(
    "aegis_flows_ingested_total",
    "Records accepted by the ingest API.",
    labelnames=("modality",),
)

RECORDS_REJECTED = Counter(
    "aegis_records_rejected_total",
    "Records the ingest API refused, by the stage that refused them.",
    labelnames=("modality", "stage"),
)

SCORE_LATENCY = Histogram(
    "aegis_score_latency_seconds",
    "Time the scoring worker spent waiting for one window's score.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

ALERTS_CREATED = Counter(
    "aegis_alerts_created_total",
    "Alerts opened, by the severity band they opened at.",
    labelnames=("severity",),
)

DRIFT_PSI = Gauge(
    "aegis_drift_psi",
    "Population stability index per feature, from the drift report.",
    labelnames=("feature",),
)

HTTP_REQUESTS = Counter(
    "aegis_http_requests_total",
    "HTTP requests, by method, route template and status.",
    labelnames=("method", "route", "status"),
)

HTTP_LATENCY = Histogram(
    "aegis_http_request_duration_seconds",
    "HTTP request duration, by method and route template.",
    labelnames=("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

#: Everything this module owns, for the label-allowlist check.
_OWNED: Final[tuple[Counter | Gauge | Histogram, ...]] = (
    FLOWS_INGESTED,
    RECORDS_REJECTED,
    SCORE_LATENCY,
    ALERTS_CREATED,
    DRIFT_PSI,
    HTTP_REQUESTS,
    HTTP_LATENCY,
)


def observe_ingest(modality: str, *, accepted: int, rejected: Mapping[str, int]) -> None:
    """Record one batch: what it put in and what it turned away, by stage.

    ``rejected`` maps the stage that refused a record (``validation``,
    ``structure``) to a count. A stage name comes from the ingest service's own
    vocabulary, not from the record, so it cannot be attacker-chosen.
    """
    if modality not in MODALITIES:
        msg = f"unknown modality {modality!r}; expected one of {MODALITIES}"
        raise ValueError(msg)
    if accepted < 0:
        msg = f"accepted count cannot be negative, got {accepted}"
        raise ValueError(msg)
    if accepted:
        FLOWS_INGESTED.labels(modality=modality).inc(accepted)
    for stage, count in rejected.items():
        if count < 0:
            msg = f"rejected count for stage {stage!r} cannot be negative, got {count}"
            raise ValueError(msg)
        if count:
            RECORDS_REJECTED.labels(modality=modality, stage=stage).inc(count)


def observe_score_latency(seconds: float) -> None:
    """Record how long one window's score took."""
    if seconds < 0:
        msg = f"a duration cannot be negative, got {seconds}"
        raise ValueError(msg)
    SCORE_LATENCY.observe(seconds)


def observe_alert_created(severity: str) -> None:
    """Record one alert opening.

    Called when a case is *created*, not when a repeat is folded into one: FR-15
    makes the repeat an increment, and counting it here would turn "alerts
    created" into "detections seen", which is a different number and the one a
    dashboard must not be fooled by.
    """
    ALERTS_CREATED.labels(severity=severity).inc()


def observe_drift_psi(feature: str, value: float) -> None:
    """Record one feature's PSI from a drift report (FR-32).

    Negative PSI is refused because PSI is a sum of non-negative terms; a
    negative value means the number did not come from the drift computation.
    """
    if value < 0:
        msg = f"PSI cannot be negative, got {value} for feature {feature!r}"
        raise ValueError(msg)
    DRIFT_PSI.labels(feature=feature).set(value)


def observe_http_request(method: str, route: str | None, status: int, seconds: float) -> None:
    """Record one HTTP request against its route template.

    ``route`` is the template the router matched
    (``/api/v1/models/{model_id}/metrics``), never the concrete path: a label
    carrying the path would be unbounded, which is why a request that matched
    nothing is recorded under :data:`UNMATCHED_ROUTE` instead.
    """
    if seconds < 0:
        msg = f"a duration cannot be negative, got {seconds}"
        raise ValueError(msg)
    label = route or UNMATCHED_ROUTE
    HTTP_REQUESTS.labels(method=method.upper(), route=label, status=str(status)).inc()
    HTTP_LATENCY.labels(method=method.upper(), route=label).observe(seconds)


def metric_label_names() -> dict[str, tuple[str, ...]]:
    """Every metric's exposed name and label set, for the allowlist test.

    The name is the one a dashboard writes: the client's internal ``_name`` for a
    counter drops the ``_total`` suffix it adds to the samples, and reporting the
    internal name would make the test assert a name no query uses.
    """
    names: dict[str, tuple[str, ...]] = {}
    for metric in _OWNED:
        name = metric._name  # noqa: SLF001
        if isinstance(metric, Counter) and not name.endswith("_total"):
            name = f"{name}_total"
        names[name] = tuple(metric._labelnames)  # noqa: SLF001
    return names
