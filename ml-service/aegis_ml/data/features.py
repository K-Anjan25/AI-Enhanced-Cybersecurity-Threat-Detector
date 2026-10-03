"""Feature extraction for the ``features@1`` schema (T-107).

Turns raw :class:`~aegis_ml.data.records.FlowRecord` and
:class:`~aegis_ml.data.records.LogRecord` objects into fixed-order feature rows
that a model can consume. The feature list is the contract, so it is pinned by
:func:`schema_hash` and a golden test: changing a feature definition without
bumping :data:`FEATURES_SCHEMA_VERSION` fails the build.

Why features are not stored on the records
------------------------------------------
``FlowRecord`` holds raw observations only (D-011). Derived quantities such as
``byte_ratio`` or ``port_entropy`` are computed here, so redefining a feature
never silently rewrites captured data — it produces a new schema version.

Window-level features
---------------------
Five features are properties of the window rather than of a single flow:
``inter_arrival_mean``, ``inter_arrival_std``, ``port_entropy``,
``dst_port_count`` and ``dst_ip_count``. They are broadcast onto every row in
the window, which is why extracting the same flow inside two different windows
legitimately yields two different rows.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from aegis_ml.data.records import FlowRecord, LogLevel, LogRecord

#: Schema contract for everything in this module.
FEATURES_SCHEMA_VERSION: Literal["features@1"] = "features@1"

#: Categorical features, embedded rather than standardised.
CATEGORICAL_FEATURES: tuple[str, ...] = ("protocol", "service", "state", "direction")

#: Volume features. Standardised downstream (T-105), raw here.
VOLUME_FEATURES: tuple[str, ...] = (
    "src_bytes",
    "dst_bytes",
    "packets",
    "src_packets",
    "dst_packets",
)

#: Timing features. The two inter-arrival statistics are window-level.
TIMING_FEATURES: tuple[str, ...] = ("duration", "inter_arrival_mean", "inter_arrival_std")

#: TCP flag counters. Counts, not booleans — a flood is visible in the count.
FLAG_FEATURES: tuple[str, ...] = ("syn", "ack", "rst", "fin", "psh", "urg")

#: Derived features. All five are window-level.
DERIVED_FEATURES: tuple[str, ...] = (
    "byte_ratio",
    "packet_ratio",
    "port_entropy",
    "dst_port_count",
    "dst_ip_count",
)

#: Everything numeric, in the order :class:`FlowFeatures` stores it.
NUMERIC_FEATURES: tuple[str, ...] = (
    VOLUME_FEATURES + TIMING_FEATURES + FLAG_FEATURES + DERIVED_FEATURES
)

#: The full contract, in order.
FEATURE_NAMES: tuple[str, ...] = CATEGORICAL_FEATURES + NUMERIC_FEATURES

#: Log-side features. Deliberately small: template mining is Drain3's job and
#: lands at T-204, so ``template_id`` is passed through here, not inferred.
LOG_FEATURE_NAMES: tuple[str, ...] = ("level_ordinal", "parameter_count", "template_known")

#: Sentinel for optional categorical fields that are null on a record. A distinct
#: string keeps "unknown" learnable instead of silently becoming a zero.
MISSING: str = "unknown"


def schema_hash() -> str:
    """Return a digest over the feature contract.

    The digest covers the schema version and every feature name in order, for
    both modalities, so renaming, reordering, adding or dropping a feature all
    change it.
    """
    parts = [FEATURES_SCHEMA_VERSION, "|".join(FEATURE_NAMES), "|".join(LOG_FEATURE_NAMES)]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


#: Pinned digest of the contract above. Must equal :func:`schema_hash`; the
#: golden test asserts it, so a feature change forces a deliberate version bump.
FEATURES_SCHEMA_HASH: str = "3b9fa1af3b5644dcde52081944af2ae77df34b12e69c9acc1a4787bdc85367dd"


@dataclass(frozen=True, slots=True)
class FlowFeatures:
    """One per-flow feature row.

    ``categorical`` aligns with :data:`CATEGORICAL_FEATURES` and ``numeric``
    with :data:`NUMERIC_FEATURES`; the tests assert both lengths so a name
    cannot drift away from its position.
    """

    schema_version: Literal["features@1"]
    entity: str
    timestamp: datetime
    categorical: tuple[str, ...]
    numeric: tuple[float, ...]
    label: str | None

    def as_dict(self) -> dict[str, str | float | None]:
        """Return the row as a name → value mapping, for tests and debugging."""
        values: dict[str, str | float | None] = dict(
            zip(CATEGORICAL_FEATURES, self.categorical, strict=True)
        )
        values.update(zip(NUMERIC_FEATURES, self.numeric, strict=True))
        values["label"] = self.label
        return values

    def numeric_value(self, name: str) -> float:
        """Return one numeric feature by name.

        Raises:
            KeyError: if ``name`` is not a numeric feature, so a typo fails here
                instead of returning a default (R-06).
        """
        try:
            return self.numeric[NUMERIC_FEATURES.index(name)]
        except ValueError:
            raise KeyError(f"{name!r} is not a numeric feature") from None

    def categorical_value(self, name: str) -> str:
        """Return one categorical feature by name.

        Raises:
            KeyError: if ``name`` is not a categorical feature.
        """
        try:
            return self.categorical[CATEGORICAL_FEATURES.index(name)]
        except ValueError:
            raise KeyError(f"{name!r} is not a categorical feature") from None


@dataclass(frozen=True, slots=True)
class LogFeatures:
    """One per-line log feature row. See :data:`LOG_FEATURE_NAMES`."""

    schema_version: Literal["features@1"]
    host: str
    service: str
    timestamp: datetime
    template_id: str | None
    numeric: tuple[float, ...]
    label: str | None

    def as_dict(self) -> dict[str, str | float | None]:
        """Return the row as a name → value mapping, for tests and debugging."""
        values: dict[str, str | float | None] = dict(
            zip(LOG_FEATURE_NAMES, self.numeric, strict=True)
        )
        values["template_id"] = self.template_id
        values["label"] = self.label
        return values

    def numeric_value(self, name: str) -> float:
        """Return one log feature by name.

        Raises:
            KeyError: if ``name`` is not a log feature.
        """
        try:
            return self.numeric[LOG_FEATURE_NAMES.index(name)]
        except ValueError:
            raise KeyError(f"{name!r} is not a log feature") from None


def _population_std(values: Sequence[float]) -> float:
    """Return the population standard deviation, or 0.0 for fewer than two values.

    Sample standard deviation is undefined for a single value; a window of two
    flows has exactly one inter-arrival gap, and reporting 0.0 spread is the
    honest reading of that.
    """
    if len(values) < 2:
        return 0.0
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _shannon_entropy(items: Sequence[object]) -> float:
    """Return Shannon entropy in bits over the distribution of ``items``.

    Zero when every item is identical (a single-port conversation) and
    ``log2(n)`` when all ``n`` are distinct (a port sweep) — exactly the
    separation T1 reconnaissance needs.
    """
    if not items:
        return 0.0
    counts = Counter(items)
    total = len(items)
    return -math.fsum((count / total) * math.log2(count / total) for count in counts.values())


def _ratio(numerator: float, denominator: float) -> float:
    """Return a smoothed ratio that is defined even when the denominator is 0.

    Port-scan and half-open flows legitimately carry zero reply bytes, and those
    are precisely the rows where the ratio matters, so the feature must not
    become infinite or NaN there. Laplace smoothing keeps it finite, positive,
    and equal to 1.0 when both sides are zero.
    """
    return (numerator + 1.0) / (denominator + 1.0)


def extract_flow_window(flows: Sequence[FlowRecord]) -> tuple[FlowFeatures, ...]:
    """Extract one feature row per flow from a single-entity window.

    Raises:
        ValueError: if the window is empty, spans more than one source entity, or
            is not ordered by arrival time. A window that silently mixed entities
            would leak behaviour across hosts, so it is refused (R-06).
    """
    if not flows:
        raise ValueError("cannot extract features from an empty window")

    entities = {flow.src_ip for flow in flows}
    if len(entities) > 1:
        raise ValueError(f"a window must cover exactly one source entity, got {len(entities)}")

    timestamps = [flow.timestamp for flow in flows]
    if any(later < earlier for earlier, later in zip(timestamps, timestamps[1:], strict=False)):
        raise ValueError("window must be ordered by arrival time")

    gaps = [
        (later - earlier).total_seconds()
        for earlier, later in zip(timestamps, timestamps[1:], strict=False)
    ]
    inter_arrival_mean = math.fsum(gaps) / len(gaps) if gaps else 0.0
    inter_arrival_std = _population_std(gaps)
    port_entropy = _shannon_entropy([flow.dst_port for flow in flows])
    dst_port_count = float(len({flow.dst_port for flow in flows}))
    dst_ip_count = float(len({flow.dst_ip for flow in flows}))
    label = _window_label([flow.label for flow in flows])
    entity = str(next(iter(entities)))

    rows: list[FlowFeatures] = []
    for flow in flows:
        categorical = (
            flow.protocol.value,
            flow.service if flow.service is not None else MISSING,
            flow.state if flow.state is not None else MISSING,
            flow.direction.value,
        )
        numeric = (
            float(flow.src_bytes),
            float(flow.dst_bytes),
            float(flow.packets),
            float(flow.src_packets),
            float(flow.dst_packets),
            flow.duration,
            inter_arrival_mean,
            inter_arrival_std,
            float(flow.syn),
            float(flow.ack),
            float(flow.rst),
            float(flow.fin),
            float(flow.psh),
            float(flow.urg),
            _ratio(float(flow.src_bytes), float(flow.dst_bytes)),
            _ratio(float(flow.src_packets), float(flow.dst_packets)),
            port_entropy,
            dst_port_count,
            dst_ip_count,
        )
        rows.append(
            FlowFeatures(
                schema_version=FEATURES_SCHEMA_VERSION,
                entity=entity,
                timestamp=flow.timestamp,
                categorical=categorical,
                numeric=numeric,
                label=label,
            )
        )
    return tuple(rows)


def extract_log_window(logs: Sequence[LogRecord]) -> tuple[LogFeatures, ...]:
    """Extract one feature row per log line from a single host+service window.

    Raises:
        ValueError: if the window is empty, spans more than one host+service, or
            is not ordered by time. Mirrors :func:`extract_flow_window`.
    """
    if not logs:
        raise ValueError("cannot extract features from an empty window")

    keys = {(line.host, line.service) for line in logs}
    if len(keys) > 1:
        raise ValueError(f"a window must cover exactly one host+service, got {len(keys)}")

    timestamps = [line.timestamp for line in logs]
    if any(later < earlier for earlier, later in zip(timestamps, timestamps[1:], strict=False)):
        raise ValueError("window must be ordered by time")

    label = _window_label([line.label for line in logs])
    host, service = next(iter(keys))
    levels = list(LogLevel)

    rows: list[LogFeatures] = []
    for line in logs:
        numeric = (
            float(levels.index(line.level)),
            float(len(line.parameters)),
            1.0 if line.template_id is not None else 0.0,
        )
        rows.append(
            LogFeatures(
                schema_version=FEATURES_SCHEMA_VERSION,
                host=host,
                service=service,
                timestamp=line.timestamp,
                template_id=line.template_id,
                numeric=numeric,
                label=label,
            )
        )
    return tuple(rows)


def _window_label(labels: Sequence[str | None]) -> str | None:
    """Return the window's label, or ``None`` when its members disagree.

    A window that mixes labels is ambiguous, and training on an ambiguous label
    teaches the model something untrue. Returning ``None`` keeps such a window
    out of supervised loss instead of guessing; the count of mixed windows is a
    data-quality signal worth surfacing (T-111).
    """
    distinct = set(labels)
    if len(distinct) != 1:
        return None
    return next(iter(distinct))
