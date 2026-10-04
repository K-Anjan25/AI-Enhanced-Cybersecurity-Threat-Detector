"""Tests for the baseline models (T-110).

These assert properties that must hold rather than scores that merely happen:
both baselines are deterministic, both refuse a single-class fold instead of
returning a degenerate model that scores like a real one, and the stump search
finds the exact best split on a case small enough to solve by hand.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from aegis_ml.data.features import CATEGORICAL_FEATURES, FlowFeatures
from aegis_ml.data.preprocess import Preprocessor, StandardScaler, Vocabulary
from aegis_ml.training.baselines import (
    GradientBoostedStumps,
    LogisticRegression,
    _best_stump_for_feature,
    _sigmoid,
    column_names,
    design_matrix,
)

SEPARABLE_ROWS = [[0.0], [0.1], [0.2], [0.8], [0.9], [1.0]]
SEPARABLE_TARGETS = [0, 0, 0, 1, 1, 1]


def test_sigmoid_is_stable_at_both_extremes() -> None:
    """The branch at zero exists so exp() never overflows to inf."""
    assert _sigmoid(0.0) == 0.5
    assert _sigmoid(700.0) == 1.0
    assert math.isfinite(_sigmoid(700.0))
    # exp(-700) is denormal-small but not zero, and must not be NaN or -inf.
    assert _sigmoid(-700.0) < 1e-300
    assert math.isfinite(_sigmoid(-700.0))
    assert not math.isnan(_sigmoid(-700.0))


def test_logistic_regression_ranks_a_separable_problem_correctly() -> None:
    model = LogisticRegression.fit(SEPARABLE_ROWS, SEPARABLE_TARGETS, epochs=400)
    assert model.score([1.0]) > 0.5
    assert model.score([0.0]) < 0.5
    assert model.score([1.0]) > model.score([0.0])


def test_logistic_regression_is_deterministic() -> None:
    """No RNG is used, so two fits must agree exactly (R-67)."""
    first = LogisticRegression.fit(SEPARABLE_ROWS, SEPARABLE_TARGETS, epochs=50)
    second = LogisticRegression.fit(SEPARABLE_ROWS, SEPARABLE_TARGETS, epochs=50)
    assert first.weights == second.weights
    assert first.bias == second.bias


def test_logistic_regression_refuses_a_single_class_fold() -> None:
    """A degenerate model scores like a real one; refusing is the safe option."""
    with pytest.raises(ValueError, match="one class is absent"):
        LogisticRegression.fit([[0.0], [1.0]], [0, 0])
    with pytest.raises(ValueError, match="one class is absent"):
        LogisticRegression.fit([[0.0], [1.0]], [1, 1])


def test_logistic_regression_refuses_mismatched_inputs() -> None:
    with pytest.raises(ValueError, match="2 rows but 3 targets"):
        LogisticRegression.fit([[0.0], [1.0]], [0, 1, 1])
    with pytest.raises(ValueError, match="zero rows"):
        LogisticRegression.fit([], [])


def test_stump_finds_the_exact_best_split() -> None:
    """[-1,-1,1,1] over [0,0,1,1] splits at 0.5 with leaves -1 and +1."""
    best = _best_stump_for_feature([0.0, 0.0, 1.0, 1.0], [-1.0, -1.0, 1.0, 1.0])
    assert best is not None
    threshold, low, high, sse = best
    assert threshold == 0.5
    assert low == -1.0
    assert high == 1.0
    assert sse == 0.0


def test_stump_is_none_for_a_constant_feature() -> None:
    """A constant feature admits no split at all, and must not return one."""
    assert _best_stump_for_feature([3.0, 3.0, 3.0], [-1.0, 0.0, 1.0]) is None


def test_stump_prefers_the_informative_feature() -> None:
    """A perfect split beats a noisy one on SSE."""
    perfect = _best_stump_for_feature([0.0, 0.0, 1.0, 1.0], [-1.0, -1.0, 1.0, 1.0])
    noisy = _best_stump_for_feature([0.0, 1.0, 0.0, 1.0], [-1.0, -1.0, 1.0, 1.0])
    assert perfect is not None and noisy is not None
    assert perfect[3] < noisy[3]


def test_gradient_boosting_reduces_training_error() -> None:
    rows = [[float(i)] for i in range(20)]
    targets = [0] * 10 + [1] * 10
    model = GradientBoostedStumps.fit(rows, targets, n_stumps=25)
    assert model.stumps
    correct = sum(
        (model.score(row) > 0.5) == bool(target) for row, target in zip(rows, targets, strict=True)
    )
    assert correct == 20


def test_gradient_boosting_is_deterministic() -> None:
    rows = [[float(i)] for i in range(20)]
    targets = [0] * 10 + [1] * 10
    first = GradientBoostedStumps.fit(rows, targets, n_stumps=5)
    second = GradientBoostedStumps.fit(rows, targets, n_stumps=5)
    assert first.stumps == second.stumps
    assert first.base == second.base


def test_gradient_boosting_refuses_a_single_class_fold() -> None:
    with pytest.raises(ValueError, match="one class is absent"):
        GradientBoostedStumps.fit([[0.0], [1.0]], [0, 0])


def test_gradient_boosting_stops_when_no_split_remains() -> None:
    """Every feature constant: no stump exists, and fitting must still return."""
    model = GradientBoostedStumps.fit([[1.0, 2.0]] * 8, [0] * 4 + [1] * 4, n_stumps=10)
    assert model.stumps == ()
    assert model.base == pytest.approx(0.0)


def _window(label: str | None, service: str) -> FlowFeatures:
    return FlowFeatures(
        schema_version="features@1",
        entity="host-a",
        timestamp=datetime(2026, 1, 5, 8, 0, tzinfo=UTC),
        categorical=("tcp", service, "FIN", "inbound"),
        numeric=tuple(float(i) for i in range(19)),
        label=label,
    )


def _preprocessor(windows: list[FlowFeatures]) -> Preprocessor:
    return Preprocessor(
        scaler=StandardScaler.fit(
            [list(w.numeric) for w in windows], tuple(f"f{i}" for i in range(19))
        ),
        vocabularies={
            name: Vocabulary.fit(w.categorical[index] for w in windows)
            for index, name in enumerate(CATEGORICAL_FEATURES)
        },
    )


def test_design_matrix_drops_unlabelled_windows() -> None:
    """Live traffic has no label; inventing 'normal' for it would be supervision."""
    windows = [_window("DoS", "http"), _window(None, "http"), _window("normal", "dns")]
    rows, targets = design_matrix(windows, _preprocessor(windows))
    assert len(rows) == 2
    assert targets == [1, 0]


def test_design_matrix_one_hot_encodes_and_reserves_unknown() -> None:
    train = [_window("DoS", "http"), _window("normal", "dns")]
    preprocessor = _preprocessor(train)
    seen, _ = design_matrix(train, preprocessor)
    novel, _ = design_matrix([_window("DoS", "quic")], preprocessor)
    assert len(seen[0]) == len(novel[0])
    assert sum(novel[0][19:]) == pytest.approx(
        sum(seen[0][19:])
    )  # still exactly one hot per categorical


def test_column_names_cover_every_design_matrix_column() -> None:
    train = [_window("DoS", "http"), _window("normal", "dns")]
    preprocessor = _preprocessor(train)
    rows, _ = design_matrix(train, preprocessor)
    names = column_names(preprocessor.vocabularies)
    assert len(names) == len(rows[0])
    assert "protocol=tcp" in names
