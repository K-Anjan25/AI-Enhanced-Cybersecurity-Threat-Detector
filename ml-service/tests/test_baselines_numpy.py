"""The numpy fits must reproduce the pure-Python reference fits.

The numpy path is what training runs. The reference loops are slow, so the test uses
small data. Weights may differ in the last bits (numpy sums in a different order), so
the checks are tolerances on the parameters, and exact agreement on the stump splits
wherever the reference's best split is not a near-tie.
"""

from __future__ import annotations

import numpy as np
import pytest
from aegis_ml.training.baselines import (
    GradientBoostedStumps,
    LogisticRegression,
    _sigmoid,
    _sigmoid_array,
)


def _dataset(seed: int, rows: int = 300, width: int = 6) -> tuple[list[list[float]], list[int]]:
    rng = np.random.default_rng(seed)
    features = rng.standard_normal((rows, width))
    noise = rng.standard_normal(rows) * 0.8
    score = 1.5 * features[:, 0] - 2.0 * features[:, 1] + 0.5 * features[:, 2] + noise
    labels = (score > 0).astype(int)
    return features.tolist(), labels.tolist()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_logistic_numpy_matches_reference(seed: int) -> None:
    rows, targets = _dataset(seed)
    fast = LogisticRegression.fit(rows, targets, epochs=60)
    slow = LogisticRegression.fit_reference(rows, targets, epochs=60)
    assert fast.epochs == slow.epochs == 60
    assert fast.bias == pytest.approx(slow.bias, abs=1e-9)
    for a, b in zip(fast.weights, slow.weights, strict=True):
        assert a == pytest.approx(b, abs=1e-9)
    for row in rows[:20]:
        assert fast.score(row) == pytest.approx(slow.score(row), abs=1e-9)


def test_logistic_refuses_single_class_on_both_paths() -> None:
    rows, _ = _dataset(4, rows=10)
    with pytest.raises(ValueError, match="one class is absent"):
        LogisticRegression.fit(rows, [0] * len(rows))
    with pytest.raises(ValueError, match="one class is absent"):
        LogisticRegression.fit_reference(rows, [1] * len(rows))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_stumps_numpy_matches_reference(seed: int) -> None:
    rows, targets = _dataset(seed)
    fast = GradientBoostedStumps.fit(rows, targets, n_stumps=12)
    slow = GradientBoostedStumps.fit_reference(rows, targets, n_stumps=12)
    assert fast.base == pytest.approx(slow.base, abs=1e-12)
    assert len(fast.stumps) == len(slow.stumps)
    for a, b in zip(fast.stumps, slow.stumps, strict=True):
        assert a.feature == b.feature
        assert a.threshold == pytest.approx(b.threshold, abs=1e-9)
        assert a.low == pytest.approx(b.low, abs=1e-9)
        assert a.high == pytest.approx(b.high, abs=1e-9)
    for row in rows[:20]:
        assert fast.score(row) == pytest.approx(slow.score(row), abs=1e-9)


def test_sigmoid_paths_agree_for_extreme_inputs() -> None:
    values = [-800.0, -30.0, -1.0, 0.0, 1.0, 30.0, 800.0]
    got = _sigmoid_array(np.asarray(values, dtype=np.float64))
    for value, probability in zip(values, got, strict=True):
        assert probability == pytest.approx(_sigmoid(value), abs=1e-12)
