"""Tests for :mod:`aegis_ml.scoring.fusion` (T-205).

The two acceptance clauses — monotonic in both inputs, and single-modality output
always flagged — are each tested by sweeping rather than by spot-checking a
handful of values. A fusion rule can be monotonic at the points you happened to
try and still break between them.
"""

from __future__ import annotations

import pytest
from aegis_ml.scoring.fusion import FusedScore, FusionConfig, fuse

STEPS = 101


def sweep() -> list[float]:
    """The whole score range, finely enough that a non-monotonic rule shows."""
    return [i / (STEPS - 1) for i in range(STEPS)]


def is_non_decreasing(values: list[float]) -> bool:
    """Whether no step goes down. Tolerates float noise, not real decreases."""
    return all(b >= a - 1e-12 for a, b in zip(values, values[1:], strict=False))


# --- the arithmetic --------------------------------------------------------


def test_both_modalities_combine_as_a_weighted_mean() -> None:
    result = fuse(1.0, 0.0)

    assert result.score == pytest.approx(0.6)
    assert result.partial_evidence is False
    assert result.contributing == ("flow", "log")


def test_a_higher_flow_score_raises_the_composite() -> None:
    assert fuse(0.9, 0.5).score > fuse(0.2, 0.5).score


# --- monotonicity, swept ---------------------------------------------------


@pytest.mark.parametrize("fixed", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_the_composite_is_monotonic_in_the_flow_score(fixed: float) -> None:
    """Acceptance clause one, for flow, at five levels of log evidence."""
    scores = [fuse(flow, fixed).score for flow in sweep()]

    assert is_non_decreasing(scores), "composite fell as flow evidence increased"


@pytest.mark.parametrize("fixed", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_the_composite_is_monotonic_in_the_log_score(fixed: float) -> None:
    """The same clause for the other modality, which is easy to forget to test."""
    scores = [fuse(fixed, log).score for log in sweep()]

    assert is_non_decreasing(scores), "composite fell as log evidence increased"


def test_single_modality_scores_are_also_monotonic() -> None:
    """The penalty must not introduce a non-monotonic region of its own."""
    flow_only = [fuse(flow, None).score for flow in sweep()]
    log_only = [fuse(None, log).score for log in sweep()]

    assert is_non_decreasing(flow_only)
    assert is_non_decreasing(log_only)


# --- the flag --------------------------------------------------------------


def test_a_missing_modality_is_flagged_and_never_presented_as_full_evidence() -> None:
    """Acceptance clause two.

    The dangerous failure is not a wrong number, it is a partial score rendered
    indistinguishably from a complete one - an operator sees 0.72 and cannot tell
    whether both models agreed or one was offline.
    """
    assert fuse(0.9, None).partial_evidence is True
    assert fuse(None, 0.9).partial_evidence is True
    assert fuse(0.9, 0.9).partial_evidence is False


def test_the_contributing_list_names_only_what_actually_ran() -> None:
    assert fuse(0.5, None).contributing == ("flow",)
    assert fuse(None, 0.5).contributing == ("log",)
    assert fuse(0.5, 0.5).contributing == ("flow", "log")


def test_a_missing_modality_is_penalised_rather_than_treated_as_benign() -> None:
    """Imputing zero would convert a probe outage into a quiet-looking network."""
    assert fuse(1.0, None).score < fuse(1.0, 1.0).score
    assert fuse(1.0, None).score == pytest.approx(0.75)


def test_the_partial_score_is_strictly_below_the_unpenalised_one() -> None:
    """Holds across the range, not just at 1.0."""
    for value in sweep():
        if value > 0.0:
            assert fuse(value, None).score < value


def test_a_partial_flag_survives_a_custom_config() -> None:
    """So the flag cannot be turned off by a caller who prefers not to see it."""
    result = fuse(0.8, None, FusionConfig(partial_penalty=0.0))

    assert result.partial_evidence is True
    assert result.score == pytest.approx(0.8)


# --- refusing to invent evidence -------------------------------------------


def test_no_evidence_at_all_is_refused() -> None:
    """A zero here would report an outage as a clean network."""
    with pytest.raises(ValueError, match="refusing to invent one"):
        fuse(None, None)


def test_out_of_range_scores_are_rejected_not_clamped() -> None:
    """Clamping would let a broken model look identical to a confident one."""
    with pytest.raises(ValueError, match="flow_score must be in"):
        fuse(1.7, 0.5)
    with pytest.raises(ValueError, match="log_score must be in"):
        fuse(0.5, -0.1)


def test_weights_must_form_a_convex_combination() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        FusionConfig(flow_weight=0.6, log_weight=0.6)
    with pytest.raises(ValueError, match="flow_weight must be in"):
        FusionConfig(flow_weight=1.4, log_weight=-0.4)
    with pytest.raises(ValueError, match="partial_penalty must be in"):
        FusionConfig(partial_penalty=1.0)


def test_the_composite_stays_inside_the_unit_interval() -> None:
    """Whatever the inputs, a probability-shaped score must stay a probability."""
    for flow in sweep():
        for log in (0.0, 0.5, 1.0):
            assert 0.0 <= fuse(flow, log).score <= 1.0
        assert 0.0 <= fuse(flow, None).score <= 1.0


def test_fused_score_is_immutable() -> None:
    """A caller must not be able to rewrite the flag after the fact."""
    result: FusedScore = fuse(0.9, None)

    with pytest.raises(Exception):  # noqa: B017, PT011 - frozen dataclass raises
        result.partial_evidence = False  # type: ignore[misc]
