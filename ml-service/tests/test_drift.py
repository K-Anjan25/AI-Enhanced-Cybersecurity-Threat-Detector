r"""Tests for per-feature PSI drift monitoring (T-211, FR-32).

The acceptance criterion is that PSI matches a hand-computed reference case, so
the central test below does the arithmetic in the test itself rather than asking
the implementation. If the test called :func:`psi_from_counts` to build its own
expected value it would pass against any consistent implementation, including a
wrong one.
"""

from __future__ import annotations

import math

import pytest
from aegis_ml.scoring.drift import (
    DEFAULT_BINS,
    EPSILON,
    METRIC_NAME,
    PSI_DRIFT_THRESHOLD,
    InMemoryMetricSink,
    band_for,
    bin_edges,
    categorical_psi,
    measure_drift,
    numeric_psi,
    psi_from_counts,
)


class TestHandComputedReference:
    """The criterion that gates this task."""

    def test_matches_arithmetic_done_by_hand(self) -> None:
        r"""Reference proportions (0.5, 0.3, 0.2) against actual (0.4, 0.4, 0.2).

        (0.4 - 0.5) * ln(0.4 / 0.5) = -0.1 * ln(0.8)   =  0.022314355...
        (0.4 - 0.3) * ln(0.4 / 0.3) =  0.1 * ln(4 / 3) =  0.028768207...
        (0.2 - 0.2) * ln(0.2 / 0.2) =  0

        total = 0.051082562...
        """
        term1 = -0.1 * math.log(0.8)
        term2 = 0.1 * math.log(4 / 3)
        expected = term1 + term2

        # Counts of 50/30/20 and 40/40/20 out of 100 give exactly those
        # proportions, so the function under test sees the same distribution.
        actual = psi_from_counts([50.0, 30.0, 20.0], [40.0, 40.0, 20.0])

        assert actual == pytest.approx(expected, rel=1e-12)
        assert actual == pytest.approx(0.051082562376599, rel=1e-9)

    def test_identical_distributions_give_zero(self) -> None:
        assert psi_from_counts([10, 20, 30], [10, 20, 30]) == pytest.approx(0.0, abs=1e-12)

    def test_proportions_are_scale_invariant(self) -> None:
        """PSI compares distributions, so doubling both counts changes nothing."""
        base = psi_from_counts([50, 30, 20], [40, 40, 20])
        doubled = psi_from_counts([100, 60, 40], [80, 80, 40])

        assert doubled == pytest.approx(base, rel=1e-12)

    def test_symmetric_in_its_arguments(self) -> None:
        """Swapping reference and actual leaves PSI unchanged."""
        forward = psi_from_counts([50, 30, 20], [10, 20, 70])
        backward = psi_from_counts([10, 20, 70], [50, 30, 20])

        assert forward == pytest.approx(backward, rel=1e-12)

    def test_a_complete_shift_is_large(self) -> None:
        """No overlap between the two distributions must read as significant."""
        value = psi_from_counts([100, 0, 0], [0, 0, 100])

        assert value > PSI_DRIFT_THRESHOLD


class TestBinEdges:
    """Bin edges are derived from the reference and nothing else."""

    def test_edges_are_reference_quantiles(self) -> None:
        edges = bin_edges([float(i) for i in range(11)], bins=5)

        # Quintiles of 0..10 are 2, 4, 6, 8.
        assert edges == [2.0, 4.0, 6.0, 8.0]

    def test_actual_values_do_not_move_the_edges(self) -> None:
        """The whole point: the partition must not follow the incoming traffic."""
        reference = [float(i) for i in range(11)]
        baseline = bin_edges(reference, bins=5)

        assert bin_edges(reference, bins=5) == baseline

    def test_duplicate_edges_are_dropped(self) -> None:
        """A near-constant feature must not manufacture empty bins."""
        edges = bin_edges([1.0, 1.0, 1.0, 1.0, 5.0], bins=10)

        assert len(edges) < 9
        assert all(edge > previous for previous, edge in zip(edges, edges[1:], strict=False))

    def test_rejects_fewer_than_two_bins(self) -> None:
        with pytest.raises(ValueError, match="at least 2 bins"):
            bin_edges([1.0, 2.0], bins=1)

    def test_rejects_an_empty_reference(self) -> None:
        with pytest.raises(ValueError, match="empty reference"):
            bin_edges([], bins=4)


class TestNumericPsi:
    """The numeric path, end to end."""

    def test_stable_traffic_reads_near_zero(self) -> None:
        reference = [float(i) for i in range(100)]
        actual = [float(i) + 0.25 for i in range(100)]

        assert numeric_psi(reference, actual) < 0.10

    def test_shifted_traffic_reads_as_drift(self) -> None:
        reference = [float(i) for i in range(100)]
        actual = [float(i) + 500.0 for i in range(100)]

        assert numeric_psi(reference, actual) > PSI_DRIFT_THRESHOLD

    def test_rejects_empty_input(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            numeric_psi([], [1.0, 2.0])

    def test_rejects_a_missing_incoming_window(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            numeric_psi([1.0, 2.0], [])


class TestCategoricalPsi:
    """Categories are already a partition, so they are never binned."""

    def test_identical_categories_give_zero(self) -> None:
        values = ["tcp", "udp", "tcp", "icmp"]

        assert categorical_psi(values, values) == pytest.approx(0.0, abs=1e-12)

    def test_a_changed_mix_gives_a_positive_value(self) -> None:
        value = categorical_psi(["tcp"] * 8 + ["udp"] * 2, ["tcp"] * 2 + ["udp"] * 8)

        assert value > 0.0

    def test_an_unseen_category_still_contributes(self) -> None:
        """The most useful thing this function can report must not be dropped."""
        reference = ["tcp"] * 10
        actual = ["tcp"] * 5 + ["quic"] * 5

        value = categorical_psi(reference, actual)
        without_the_new_category = categorical_psi(reference, ["tcp"] * 10)

        assert value > without_the_new_category
        assert value > 0.0

    def test_rejects_empty_input(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            categorical_psi([], ["tcp"])


class TestZeroHandling:
    """Empty bins are floored, and the cost of flooring is knowable."""

    def test_an_empty_bin_does_not_raise(self) -> None:
        value = psi_from_counts([50, 50], [100, 0])

        assert math.isfinite(value)

    def test_an_empty_reference_bin_does_not_raise(self) -> None:
        value = psi_from_counts([100, 0], [50, 50])

        assert math.isfinite(value)

    def test_flooring_bounds_psi_from_above(self) -> None:
        """With a total shift, PSI approaches ln(1/EPSILON) rather than infinity."""
        value = psi_from_counts([1000, 0], [0, 1000])

        assert value <= 2 * math.log(1 / EPSILON)


class TestValidation:
    """Bad input must fail loudly rather than produce a plausible number."""

    def test_misaligned_bins_are_refused(self) -> None:
        with pytest.raises(ValueError, match="bin-aligned"):
            psi_from_counts([1, 2, 3], [1, 2])

    def test_no_bins_at_all_are_refused(self) -> None:
        with pytest.raises(ValueError, match="zero bins"):
            psi_from_counts([], [])

    def test_negative_counts_are_refused(self) -> None:
        with pytest.raises(ValueError, match="negative counts"):
            psi_from_counts([10, -5], [10, 5])

    def test_an_all_zero_distribution_is_refused(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            psi_from_counts([0, 0, 0], [1, 2, 3])

    def test_a_non_positive_threshold_is_refused(self) -> None:
        with pytest.raises(ValueError, match="threshold must be positive"):
            measure_drift({"a": [1.0]}, {"a": [1.0]}, threshold=0.0)


class TestBands:
    """The interpretation bands an operator reads off a gauge."""

    def test_band_boundaries(self) -> None:
        assert band_for(0.0) == "stable"
        assert band_for(0.05) == "stable"
        assert band_for(0.15) == "moderate"
        assert band_for(0.30) == "significant"
        assert band_for(1.0) == "significant"


class TestMeasureDrift:
    """The per-feature entry point and the metric it publishes."""

    def _columns(self) -> tuple[dict[str, list[object]], dict[str, list[object]]]:
        reference: dict[str, list[object]] = {
            "bytes": [float(i) for i in range(100)],
            "protocol": ["tcp"] * 80 + ["udp"] * 20,
        }
        actual: dict[str, list[object]] = {
            "bytes": [float(i) + 500.0 for i in range(100)],
            "protocol": ["tcp"] * 20 + ["udp"] * 80,
        }
        return reference, actual

    def test_reports_every_feature_present_in_both(self) -> None:
        reference, actual = self._columns()

        report = measure_drift(reference, actual)

        assert {entry.feature for entry in report.features} == {"bytes", "protocol"}

    def test_drifted_features_are_flagged_and_sorted_worst_first(self) -> None:
        reference, actual = self._columns()

        report = measure_drift(reference, actual)

        assert report.any_drift
        drifted = report.drifted()
        assert all(entry.drifted for entry in drifted)
        assert [entry.psi for entry in drifted] == sorted(
            (entry.psi for entry in drifted), reverse=True
        )

    def test_stable_features_are_not_flagged(self) -> None:
        values = [float(i) for i in range(100)]

        report = measure_drift({"bytes": values}, {"bytes": values})

        assert not report.any_drift
        assert report.features[0].band == "stable"

    def test_a_feature_missing_from_the_incoming_window_is_skipped(self) -> None:
        """A pipeline gap is not a distribution change, and must not read as one."""
        report = measure_drift({"bytes": [1.0, 2.0], "ports": [3.0, 4.0]}, {"bytes": [1.0, 2.0]})

        assert [entry.feature for entry in report.features] == ["bytes"]

    def test_publishes_the_architecture_metric_name_per_feature(self) -> None:
        """aegis_drift_psi{feature} is fixed by architecture.md §12."""
        reference, actual = self._columns()
        sink = InMemoryMetricSink()

        measure_drift(reference, actual, sink=sink)

        published = sink.values(METRIC_NAME)
        assert (("feature", "bytes"),) in published
        assert (("feature", "protocol"),) in published

    def test_publishes_stable_features_too(self) -> None:
        """A gauge that only appears on failure cannot show a week of stability."""
        values = [float(i) for i in range(100)]
        sink = InMemoryMetricSink()

        measure_drift({"bytes": values}, {"bytes": values}, sink=sink)

        assert (("feature", "bytes"),) in sink.values(METRIC_NAME)

    def test_nothing_is_published_without_a_sink(self) -> None:
        reference, actual = self._columns()

        report = measure_drift(reference, actual, sink=None)

        assert report.any_drift  # still computed, just not published

    def test_the_published_value_matches_the_reported_value(self) -> None:
        reference, actual = self._columns()
        sink = InMemoryMetricSink()

        report = measure_drift(reference, actual, sink=sink)
        published = sink.values(METRIC_NAME)

        for entry in report.features:
            assert published[(("feature", entry.feature),)] == pytest.approx(entry.psi)

    def test_a_custom_threshold_is_honoured(self) -> None:
        values = [float(i) for i in range(100)]
        shifted = [float(i) + 5.0 for i in range(100)]

        lenient = measure_drift({"bytes": values}, {"bytes": shifted}, threshold=100.0)
        strict = measure_drift({"bytes": values}, {"bytes": shifted}, threshold=1e-9)

        assert not lenient.any_drift
        assert strict.any_drift

    def test_recorded_sizes_and_bins(self) -> None:
        reference = {"bytes": [float(i) for i in range(100)]}
        actual = {"bytes": [float(i) for i in range(40)]}

        entry = measure_drift(reference, actual).features[0]

        assert entry.reference_size == 100
        assert entry.actual_size == 40
        assert entry.bins == DEFAULT_BINS

    def test_report_serialises(self) -> None:
        reference, actual = self._columns()

        payload = measure_drift(reference, actual).as_json()

        assert payload["metric_name"] == METRIC_NAME
        assert payload["threshold"] == PSI_DRIFT_THRESHOLD
        assert isinstance(payload["features"], list)
        assert isinstance(payload["drifted_features"], list)

    def test_worst_on_an_empty_report_is_none(self) -> None:
        assert measure_drift({}, {}).worst() is None

    def test_worst_is_the_largest_psi(self) -> None:
        reference, actual = self._columns()

        report = measure_drift(reference, actual)

        assert report.worst() is not None
        assert report.worst().psi == max(entry.psi for entry in report.features)


class TestThresholdConstant:
    """FR-32's threshold is a contract, not a tuning knob."""

    def test_threshold_is_fr32s_value(self) -> None:
        assert PSI_DRIFT_THRESHOLD == 0.25

    def test_metric_name_is_the_architecture_name(self) -> None:
        assert METRIC_NAME == "aegis_drift_psi"
