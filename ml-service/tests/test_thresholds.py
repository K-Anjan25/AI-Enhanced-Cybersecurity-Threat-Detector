"""Tests for :mod:`aegis_ml.scoring.thresholds` (T-207).

The two acceptance clauses are tested as properties over sweeps rather than at
hand-picked points: a guardrail that holds at 0.5 and fails at 0.95 is worse than
no guardrail, because it has already earned the reviewer's trust.
"""

from __future__ import annotations

import os

import pytest
from aegis_ml.scoring.thresholds import (
    DEFAULT_GUARDRAIL,
    ThresholdChange,
    append_audit,
    calibrate,
    calibrate_and_record,
    fit_threshold,
    quantile,
    read_audit,
)

STEPS = 41


def sweep() -> list[float]:
    """The whole threshold range."""
    return [i / (STEPS - 1) for i in range(STEPS)]


# --- quantile arithmetic ---------------------------------------------------


def test_quantile_matches_known_positions() -> None:
    values = [0.0, 0.25, 0.5, 0.75, 1.0]

    assert quantile(values, 0.0) == 0.0
    assert quantile(values, 0.5) == 0.5
    assert quantile(values, 1.0) == 1.0
    assert quantile(values, 0.25) == pytest.approx(0.25)


def test_quantile_does_not_depend_on_input_order() -> None:
    assert quantile([0.9, 0.1, 0.5], 0.5) == quantile([0.1, 0.5, 0.9], 0.5)


def test_quantile_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match=r"q must be in"):
        quantile([0.5], 1.5)
    with pytest.raises(ValueError, match="empty sequence"):
        quantile([], 0.5)


# --- fitting ---------------------------------------------------------------


def test_fit_threshold_uses_the_benign_quantile() -> None:
    scores = [i / 100 for i in range(101)]

    assert fit_threshold(scores, quantile_=0.99) == pytest.approx(0.99)
    assert fit_threshold(scores, quantile_=0.50) == pytest.approx(0.50)


def test_fit_threshold_refuses_to_run_without_benign_scores() -> None:
    """Fitting on attacks would place the threshold inside the attack distribution."""
    with pytest.raises(ValueError, match="without benign scores"):
        fit_threshold([])


def test_fit_threshold_rejects_out_of_range_scores() -> None:
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        fit_threshold([0.5, 1.4])


# --- the guardrail ---------------------------------------------------------


def test_a_move_inside_the_guardrail_is_applied_exactly() -> None:
    change = calibrate("ddos", 0.55, previous=0.50)

    assert change.applied == pytest.approx(0.55)
    assert change.clamped is False


@pytest.mark.parametrize("requested", sweep())
def test_no_single_run_can_move_a_threshold_by_more_than_the_guardrail(requested: float) -> None:
    """Acceptance clause one, swept over every requested value from a mid start."""
    change = calibrate("tenant-a", requested, previous=0.50)

    assert abs(change.movement()) <= DEFAULT_GUARDRAIL + 1e-12


@pytest.mark.parametrize("previous", sweep())
def test_the_guardrail_holds_from_every_starting_threshold(previous: float) -> None:
    """The clause that is easy to pass at 0.5 and fail near the ends."""
    for requested in (0.0, 0.3, 0.5, 0.8, 1.0):
        change = calibrate("tenant-b", requested, previous=previous)

        assert abs(change.movement()) <= DEFAULT_GUARDRAIL + 1e-12
        assert 0.0 <= change.applied <= 1.0


def test_a_large_move_is_clamped_not_refused() -> None:
    """Refusing would freeze the threshold the first time the data is unusual."""
    change = calibrate("ddos", 1.0, previous=0.20)

    assert change.applied == pytest.approx(0.30)
    assert change.requested == pytest.approx(1.0)
    assert change.clamped is True


def test_the_threshold_never_leaves_the_unit_interval() -> None:
    """Near 0 or 1 the guardrail band reaches past the ends of the range."""
    assert calibrate("low", 1.0, previous=0.0).applied == pytest.approx(0.10)
    assert calibrate("high", 0.0, previous=1.0).applied == pytest.approx(0.90)


def test_repeated_runs_can_still_reach_a_distant_threshold() -> None:
    """Clamping limits a single run, so a genuine drift accumulates over several."""
    threshold = 0.20
    for _ in range(10):
        threshold = calibrate("ddos", 1.0, previous=threshold).applied

    assert threshold == pytest.approx(1.0)


def test_the_requested_value_is_preserved_alongside_the_applied_one() -> None:
    """The refused part of a change is the interesting record; dropping it loses it."""
    change = calibrate("ddos", 0.95, previous=0.30)

    assert change.requested == pytest.approx(0.95)
    assert change.applied == pytest.approx(0.40)
    assert change.clamped is True


def test_the_guardrail_itself_is_validated() -> None:
    with pytest.raises(ValueError, match="guardrail must be in"):
        calibrate("ddos", 0.5, previous=0.5, guardrail=1.0)
    with pytest.raises(ValueError, match="previous must be in"):
        calibrate("ddos", 0.5, previous=1.5)


# --- the audit log ---------------------------------------------------------


def test_every_change_appears_in_the_audit_log(tmp_path: object) -> None:
    """Acceptance clause two, including the clamped and no-op changes."""
    path = os.path.join(str(tmp_path), "thresholds.ndjson")  # noqa: PTH118
    changes = [
        calibrate("ddos", 0.55, previous=0.50),  # ordinary
        calibrate("ddos", 1.00, previous=0.55),  # clamped
        calibrate("ddos", 0.55, previous=0.55),  # no movement
    ]
    for change in changes:
        append_audit(path, change)

    recorded = read_audit(path)

    assert len(recorded) == len(changes)
    assert recorded == changes


def test_a_clamped_change_is_recorded_with_what_was_refused(tmp_path: object) -> None:
    path = os.path.join(str(tmp_path), "audit.ndjson")  # noqa: PTH118
    change = calibrate("tenant-c", 1.0, previous=0.10)
    append_audit(path, change)

    recorded = read_audit(path)[0]

    assert recorded.clamped is True
    assert recorded.requested == pytest.approx(1.0)
    assert recorded.applied == pytest.approx(0.20)


def test_the_audit_log_is_append_only_across_calls(tmp_path: object) -> None:
    """A second write must not overwrite the first."""
    path = os.path.join(str(tmp_path), "audit.ndjson")  # noqa: PTH118
    append_audit(path, calibrate("a", 0.5, previous=0.5))
    append_audit(path, calibrate("b", 0.6, previous=0.5))

    assert len(read_audit(path)) == 2


def test_read_audit_tolerates_a_missing_file(tmp_path: object) -> None:
    path = os.path.join(str(tmp_path), "absent.ndjson")  # noqa: PTH118

    assert read_audit(path) == []


def test_calibrate_and_record_writes_exactly_one_line_per_call(tmp_path: object) -> None:
    """Fit and record are combined so an unrecorded change takes extra effort."""
    path = os.path.join(str(tmp_path), "audit.ndjson")  # noqa: PTH118
    scores = [i / 100 for i in range(101)]

    first = calibrate_and_record(path, "ddos", scores, previous=0.50)
    second = calibrate_and_record(path, "ddos", scores, previous=first.applied)

    recorded = read_audit(path)
    assert len(recorded) == 2
    assert recorded[1].previous == pytest.approx(first.applied)
    assert second.sample_size == 101


def test_calibrate_and_record_applies_the_guardrail_to_a_real_fit(tmp_path: object) -> None:
    """End to end: a benign distribution far from the current threshold moves 0.10."""
    path = os.path.join(str(tmp_path), "audit.ndjson")  # noqa: PTH118
    scores = [0.95, 0.96, 0.97, 0.98, 0.99]

    change = calibrate_and_record(path, "ddos", scores, previous=0.30, quantile_=0.99)

    # 0.99 quantile of five points interpolates 96% of the way from 0.98 to 0.99.
    assert change.requested == pytest.approx(0.9896, abs=1e-9)
    assert change.applied == pytest.approx(0.40)
    assert change.clamped is True


def test_the_change_record_is_a_stable_serialisation() -> None:
    """Identical changes must serialise identically, or the log cannot be diffed."""
    change = ThresholdChange(
        key="ddos",
        previous=0.5,
        requested=0.6,
        applied=0.6,
        clamped=False,
        quantile=0.99,
        sample_size=100,
    )

    assert change.as_json() == change.as_json()
    assert '"key": "ddos"' in change.as_json()
