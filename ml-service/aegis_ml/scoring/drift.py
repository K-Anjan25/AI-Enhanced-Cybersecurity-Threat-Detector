r"""Per-feature population stability index and drift flagging (T-211, FR-32).

A detector trained on one capture decays silently on the next. Nothing errors,
recall just quietly falls — which is exactly the failure T-208 measured between
UNSW-NB15 and CIC-IDS2017. PSI is how that decay becomes visible before it shows
up as missed attacks.

    PSI = Σ (actual_i − expected_i) · ln(actual_i / expected_i)

Three design points, each of which changes the number.

**Bin edges come from the reference distribution and nothing else.** Using the
incoming data to place bins would make PSI incomparable between two windows: the
metric would move because the partition moved, not because the traffic did. This
is the same rule as R-62 applied to a different artifact.

**Zero counts are floored, not skipped.** A bin empty in the incoming window makes
``ln(actual / expected)`` undefined and a bin empty in the reference makes the
ratio infinite. Rather than dropping the bin — which would hide precisely the
"this traffic appeared out of nowhere" case drift monitoring exists to catch — an
empty proportion is floored at ``EPSILON``. The cost is that PSI is bounded above
instead of able to reach infinity, which is stated rather than left implicit.

**Categorical features are not binned.** A category is already a partition, and
re-binning an encoded category id would invent an ordering that was never there.

The metric name is ``aegis_drift_psi{feature}``, fixed by architecture.md §12 and
not a free choice here.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

#: FR-32 and architecture.md's alert rule. Above this a feature has drifted.
PSI_DRIFT_THRESHOLD = 0.25

#: Metric name, fixed by architecture.md §12.
METRIC_NAME = "aegis_drift_psi"

#: Floor for an empty bin's proportion. See the module docstring for why flooring
#: rather than skipping: skipping hides the bin that appeared from nowhere.
EPSILON = 1e-6

#: Conventional interpretation bands, recorded for the operator reading a gauge.
#: Not used to decide drift — FR-32 fixes a single threshold at 0.25.
PSI_STABLE_MAX = 0.10
PSI_MODERATE_MAX = 0.25

#: Default number of bins for a numeric feature.
DEFAULT_BINS = 10


class MetricSink(Protocol):
    """Where drift numbers go. Kept a protocol so no dependency is implied."""

    def gauge(self, name: str, labels: Mapping[str, str], value: float) -> None:
        """Record a labelled gauge."""
        ...


class InMemoryMetricSink:
    """A sink that keeps everything, for tests and for the CLI."""

    def __init__(self) -> None:
        """Start empty."""
        self.records: list[tuple[str, tuple[tuple[str, str], ...], float]] = []

    def gauge(self, name: str, labels: Mapping[str, str], value: float) -> None:
        """Store one labelled gauge reading."""
        self.records.append((name, tuple(sorted(labels.items())), value))

    def values(self, name: str) -> dict[tuple[tuple[str, str], ...], float]:
        """Latest reading per label set, for assertions."""
        found = {labels: value for entry, labels, value in self.records if entry == name}
        return found


@dataclass(frozen=True, slots=True)
class FeatureDrift:
    """PSI for one feature.

    Attributes:
        feature: feature name, used as the metric label.
        psi: population stability index against the reference.
        drifted: whether ``psi`` exceeds the threshold.
        band: human-readable interpretation of ``psi``.
        bins: how many bins the comparison used.
        reference_size: rows the reference distribution was built from.
        actual_size: rows in the incoming window.
    """

    feature: str
    psi: float
    drifted: bool
    band: str
    bins: int
    reference_size: int
    actual_size: int

    def as_json(self) -> dict[str, object]:
        """Serialisable form, for the manifest and the API."""
        return {
            "feature": self.feature,
            "psi": self.psi,
            "drifted": self.drifted,
            "band": self.band,
            "bins": self.bins,
            "reference_size": self.reference_size,
            "actual_size": self.actual_size,
        }


@dataclass(frozen=True, slots=True)
class DriftReport:
    """PSI for every measured feature.

    Attributes:
        features: one entry per feature, in the order they were measured.
        threshold: the threshold that decided ``drifted``.
    """

    features: tuple[FeatureDrift, ...]
    threshold: float

    def drifted(self) -> tuple[FeatureDrift, ...]:
        """Only the features over the threshold, worst first."""
        over = [entry for entry in self.features if entry.drifted]
        return tuple(sorted(over, key=lambda entry: -entry.psi))

    @property
    def any_drift(self) -> bool:
        """Whether anything moved. One drifted feature is enough."""
        return any(entry.drifted for entry in self.features)

    def worst(self) -> FeatureDrift | None:
        """The most-drifted feature, or ``None`` when nothing was measured."""
        if not self.features:
            return None
        return max(self.features, key=lambda entry: entry.psi)

    def as_json(self) -> dict[str, object]:
        """Serialisable form."""
        return {
            "metric_name": METRIC_NAME,
            "threshold": self.threshold,
            "any_drift": self.any_drift,
            "drifted_features": [entry.feature for entry in self.drifted()],
            "features": [entry.as_json() for entry in self.features],
        }


def band_for(psi: float) -> str:
    """Conventional interpretation of a PSI value."""
    if psi < PSI_STABLE_MAX:
        return "stable"
    if psi < PSI_MODERATE_MAX:
        return "moderate"
    return "significant"


def _proportions(counts: Sequence[float], *, epsilon: float = EPSILON) -> list[float]:
    """Normalise counts to proportions, flooring empties at ``epsilon``.

    Raises:
        ValueError: if there are no bins, or any count is negative.
    """
    if not counts:
        raise ValueError("cannot compute PSI over zero bins")
    if any(count < 0 for count in counts):
        raise ValueError("negative counts are not a distribution")
    total = sum(counts)
    if total <= 0:
        raise ValueError("the reference or incoming window is empty")
    return [max(count / total, epsilon) for count in counts]


def psi_from_counts(
    reference: Sequence[float],
    actual: Sequence[float],
    *,
    epsilon: float = EPSILON,
) -> float:
    """PSI from two aligned sequences of bin counts.

    The sequences must be bin-aligned: entry ``i`` of each is the same bin.
    """
    if len(reference) != len(actual):
        raise ValueError(
            f"reference has {len(reference)} bins but actual has {len(actual)}; "
            "the two must be bin-aligned"
        )
    expected = _proportions(reference, epsilon=epsilon)
    observed = _proportions(actual, epsilon=epsilon)
    return sum(
        (observed - expected) * math.log(observed / expected)
        for observed, expected in zip(observed, expected, strict=True)
    )


def bin_edges(reference: Sequence[float], *, bins: int = DEFAULT_BINS) -> list[float]:
    """Interior bin edges from the reference distribution alone.

    Edges are the reference's own quantiles, so each bin holds a roughly equal
    share of the reference traffic. Duplicate edges are dropped: a feature with
    few distinct values would otherwise produce empty bins by construction, and an
    empty bin that was always going to be empty says nothing about drift.

    Raises:
        ValueError: if ``bins`` is below 2 or the reference is empty.
    """
    if bins < 2:
        raise ValueError(f"needs at least 2 bins, got {bins}")
    values = sorted(float(value) for value in reference)
    if not values:
        raise ValueError("cannot derive bin edges from an empty reference")
    edges: list[float] = []
    for index in range(1, bins):
        position = index / bins * (len(values) - 1)
        low = math.floor(position)
        high = math.ceil(position)
        weight = position - low
        edge = values[low] * (1 - weight) + values[high] * weight
        if not edges or edge > edges[-1]:
            edges.append(edge)
    return edges


def _histogram(values: Sequence[float], edges: Sequence[float]) -> list[float]:
    """Count ``values`` into ``len(edges) + 1`` bins, last bin closed on both ends."""
    counts = [0.0] * (len(edges) + 1)
    for value in values:
        placed = False
        for index, edge in enumerate(edges):
            if value <= edge:
                counts[index] += 1.0
                placed = True
                break
        if not placed:
            counts[-1] += 1.0
    return counts


def numeric_psi(
    reference: Sequence[float],
    actual: Sequence[float],
    *,
    bins: int = DEFAULT_BINS,
    epsilon: float = EPSILON,
) -> float:
    """PSI for one numeric feature, binned on the reference's own quantiles.

    Raises:
        ValueError: if either sequence is empty, or ``bins`` is below 2.
    """
    if not reference or not actual:
        raise ValueError("both the reference and the incoming window must be non-empty")
    edges = bin_edges(reference, bins=bins)
    return psi_from_counts(_histogram(reference, edges), _histogram(actual, edges), epsilon=epsilon)


def categorical_psi(
    reference: Sequence[str],
    actual: Sequence[str],
    *,
    epsilon: float = EPSILON,
) -> float:
    """PSI for one categorical feature, over the reference's own categories.

    Categories present in the incoming window but absent from the reference still
    contribute: that is the "a value nobody has seen before appeared" case, and it
    is the most interesting thing this function can report.

    Raises:
        ValueError: if either sequence is empty.
    """
    if not reference or not actual:
        raise ValueError("both the reference and the incoming window must be non-empty")
    reference_counts = Counter(reference)
    actual_counts = Counter(actual)
    categories = sorted(set(reference_counts) | set(actual_counts))
    return psi_from_counts(
        [float(reference_counts.get(category, 0)) for category in categories],
        [float(actual_counts.get(category, 0)) for category in categories],
        epsilon=epsilon,
    )


def measure_drift(
    reference_columns: Mapping[str, Sequence[object]],
    actual_columns: Mapping[str, Sequence[object]],
    *,
    bins: int = DEFAULT_BINS,
    threshold: float = PSI_DRIFT_THRESHOLD,
    sink: MetricSink | None = None,
) -> DriftReport:
    """Compute per-feature PSI and publish ``aegis_drift_psi{feature}``.

    Every measured feature is published, drifted or not: a gauge that only appears
    when something is wrong cannot show that a feature has been stable for weeks,
    and "no news" would be indistinguishable from "not measured".

    A feature present in the reference but absent from the incoming columns is
    skipped rather than reported as drift — its absence is a pipeline problem, not
    a distribution change, and conflating the two would make the gauge lie.

    Args:
        reference_columns: feature name to reference values.
        actual_columns: feature name to incoming values.
        bins: bins for numeric features.
        threshold: FR-32's 0.25 unless a caller has a reason to override.
        sink: where to publish. When ``None`` nothing is published.

    Returns:
        A :class:`DriftReport` covering every feature present in both.
    """
    if threshold <= 0:
        raise ValueError(f"threshold must be positive, got {threshold}")

    entries: list[FeatureDrift] = []
    for feature, reference_values in reference_columns.items():
        if feature not in actual_columns:
            continue
        actual_values = actual_columns[feature]
        is_numeric = all(isinstance(value, (int, float)) for value in reference_values) and all(
            isinstance(value, (int, float)) for value in actual_values
        )
        if is_numeric:
            value = numeric_psi(
                [float(v) for v in reference_values],  # type: ignore[arg-type]
                [float(v) for v in actual_values],  # type: ignore[arg-type]
                bins=bins,
            )
            used_bins = len(bin_edges([float(v) for v in reference_values], bins=bins)) + 1  # type: ignore[arg-type]
        else:
            value = categorical_psi(
                [str(v) for v in reference_values],
                [str(v) for v in actual_values],
            )
            used_bins = len(set(reference_values) | set(actual_values))

        entry = FeatureDrift(
            feature=feature,
            psi=value,
            drifted=value > threshold,
            band=band_for(value),
            bins=used_bins,
            reference_size=len(reference_values),
            actual_size=len(actual_values),
        )
        entries.append(entry)
        if sink is not None:
            sink.gauge(METRIC_NAME, {"feature": feature}, value)

    return DriftReport(features=tuple(entries), threshold=threshold)
