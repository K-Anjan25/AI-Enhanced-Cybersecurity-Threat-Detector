"""Tests for :mod:`aegis_ml.scoring.explanation` (T-206).

The contract under test is R-70's: every scored window yields at least three
reasons naming feature, value and baseline, or an explicit
``explanation_unavailable`` marker. The failure mode these tests exist to catch is
an alert that renders as if nothing were unusual because its explanation quietly
came back empty.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="torch is the ml-service[training] extra")

from aegis_ml.models.flownet import FlowNet, FlowNetConfig  # noqa: E402
from aegis_ml.scoring.explanation import (  # noqa: E402
    MIN_REASONS,
    Explanation,
    Reason,
    attribute,
    explain,
)

WIDTH = 8
NAMES = tuple(f"feature_{i}" for i in range(WIDTH))


def make_model() -> FlowNet:
    """A small deterministic model, good enough to attribute against."""
    torch.manual_seed(3)
    return FlowNet(FlowNetConfig(input_dim=WIDTH, d_model=32, nhead=4, dim_feedforward=64)).eval()


def make_window(seq: int = 10, spike: int | None = None) -> list[list[float]]:
    """A window of zeros, optionally with one feature driven hard."""
    window = [[0.0] * WIDTH for _ in range(seq)]
    if spike is not None:
        for row in window:
            row[spike] = 6.0
    return window


BASELINE = [0.0] * WIDTH


# --- the R-70 contract -----------------------------------------------------


def test_a_scored_window_yields_at_least_three_reasons() -> None:
    result = explain(make_model(), make_window(), BASELINE, NAMES)

    assert result.unavailable is False
    assert len(result.reasons) >= MIN_REASONS


def test_every_reason_names_the_feature_the_value_and_the_baseline() -> None:
    """The clause that makes a reason useful rather than decorative."""
    result = explain(make_model(), make_window(spike=2), BASELINE, NAMES)

    for reason in result.reasons:
        assert reason.feature in NAMES
        rendered = reason.render()
        assert reason.feature in rendered
        assert f"{reason.value:.3f}" in rendered
        assert f"{reason.baseline:.3f}" in rendered


def test_reasons_are_ordered_by_how_much_they_moved_the_score() -> None:
    result = explain(make_model(), make_window(spike=4), BASELINE, NAMES)
    magnitudes = [abs(r.contribution) for r in result.reasons]

    assert magnitudes == sorted(magnitudes, reverse=True)


def test_explanation_is_deterministic_for_the_same_window() -> None:
    """An explanation that changes between renders cannot be audited."""
    model = make_model()
    window = make_window(spike=1)

    first = explain(model, window, BASELINE, NAMES)
    second = explain(model, window, BASELINE, NAMES)

    assert first == second


def test_explain_never_returns_empty_reasons_without_the_flag() -> None:
    """The specific way an alert ends up looking unexplained while appearing fine."""
    model = make_model()

    for window, baseline in (
        (make_window(), BASELINE),  # normal case
        ([[0.0] * 2 for _ in range(4)], [0.0, 0.0]),  # too narrow
        (make_window(), [0.0]),  # mismatched baseline
    ):
        names = NAMES if len(window[0]) == WIDTH else tuple(f"f{i}" for i in range(len(window[0])))
        result = explain(model, window, baseline, names)

        assert result.reasons or result.unavailable, "empty reasons with no unavailable flag"


# --- the unavailable marker ------------------------------------------------


def test_a_window_too_narrow_to_explain_is_marked_unavailable() -> None:
    """Fewer attributable features than the floor is not an explanation."""
    model = FlowNet(FlowNetConfig(input_dim=2, d_model=32, nhead=4, dim_feedforward=64)).eval()
    window = [[0.1, 0.2] for _ in range(4)]

    result = explain(model, window, [0.0, 0.0], ("a", "b"))

    assert result.unavailable is True
    assert result.reasons == ()
    assert result.detail is not None
    assert str(MIN_REASONS) in result.detail


def test_a_mismatched_baseline_is_marked_unavailable_rather_than_raising() -> None:
    """The alert still stands; only the explanation failed."""
    result = explain(make_model(), make_window(), [0.0], NAMES)

    assert result.unavailable is True
    assert "baseline" in (result.detail or "")


def test_the_marker_constructor_never_produces_a_silent_blank() -> None:
    marker = Explanation.unavailable_explanation(0.9, "boom")

    assert marker.unavailable is True
    assert marker.detail == "boom"
    assert marker.score == pytest.approx(0.9)


# --- attribution is not vacuous --------------------------------------------


def test_the_driven_feature_is_attributed_at_or_near_the_top() -> None:
    """Guards the whole module against returning plausible-looking noise.

    Shape checks and ordering checks pass on a random ranking too. This one does
    not: it requires the feature that was actually changed to be found.
    """
    reasons = attribute(make_model(), make_window(spike=5), BASELINE, NAMES)

    assert reasons[0].feature == "feature_5"


def test_an_unchanged_window_attributes_little_to_anything() -> None:
    """With no signal there is nothing to explain, and it should say so quietly."""
    reasons = attribute(make_model(), make_window(), BASELINE, NAMES)

    assert all(abs(r.contribution) < 0.5 for r in reasons)


def test_attribute_validates_its_inputs() -> None:
    model = make_model()

    with pytest.raises(ValueError, match="empty window"):
        attribute(model, [], BASELINE, NAMES)
    with pytest.raises(ValueError, match="baseline has"):
        attribute(model, make_window(), [0.0], NAMES)
    with pytest.raises(ValueError, match="names for"):
        attribute(model, make_window(), BASELINE, ("only_one",))


def test_reason_rendering_reads_as_a_sentence() -> None:
    reason = Reason(feature="dst_bytes", value=9000.0, baseline=1200.0, contribution=0.31)

    rendered = reason.render()

    assert "dst_bytes" in rendered
    assert "9000.000" in rendered
    assert "1200.000" in rendered
    assert "raised" in rendered


def test_a_negative_contribution_renders_as_lowering_the_score() -> None:
    reason = Reason(feature="duration", value=0.1, baseline=0.4, contribution=-0.2)

    assert "lowered" in reason.render()
