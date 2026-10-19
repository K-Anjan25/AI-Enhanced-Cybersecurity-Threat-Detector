"""Baseline models: logistic regression and gradient boosting (T-110).

These are the bar the transformers at T-201 must beat, and they are written in
plain Python for the same reason the evaluation harness is: a baseline nobody
has to install a scientific stack to run is a baseline that actually gets run,
and a number that can be reproduced from first principles is a number that can
be argued with.

Both models are deterministic — no RNG is used at all. Logistic regression
starts from zero weights and takes fixed-size steps; the boosted stumps search
exhaustively. Two runs of the same data therefore produce identical weights,
which is what R-67 asks of every model here, not just the deep ones.

The stump search is the standard cumulative-sum sweep rather than a scan over
candidate thresholds: sorting each feature once and sliding the split point
finds the *globally* best stump in O(n log n) instead of approximating it over
a quantile grid. Approximating a baseline to make it fast is how a baseline ends
up looking worse than it is.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from aegis_ml.data.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, FlowFeatures
from aegis_ml.data.preprocess import Preprocessor

#: Baseline used before any tree has been fitted.
DEFAULT_LEARNING_RATE = 0.3
DEFAULT_STUMP_COUNT = 60
DEFAULT_LR_EPOCHS = 300
DEFAULT_LR_RATE = 0.1
DEFAULT_L2 = 1e-4


def _sigmoid(z: float) -> float:
    """Numerically stable logistic function."""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    exponent = math.exp(z)
    return exponent / (1.0 + exponent)


def design_matrix(
    windows: Sequence[FlowFeatures],
    preprocessor: Preprocessor,
) -> tuple[list[list[float]], list[int]]:
    """Turn window features into numeric rows and binary targets.

    Categorical features are one-hot encoded against the training vocabulary, so
    a value never seen in training becomes the reserved unknown column rather
    than an index error. Windows with no label are dropped: a baseline cannot be
    scored against an unknown target, and silently treating it as negative would
    invent supervision.
    """
    rows: list[list[float]] = []
    targets: list[int] = []
    for window in windows:
        if window.label is None:
            continue
        rows.append(encode_row(window, preprocessor))
        targets.append(0 if window.label == "normal" else 1)
    return rows, targets


def encode_row(window: FlowFeatures, preprocessor: Preprocessor) -> list[float]:
    """One feature row as the model sees it: scaled numerics, then one-hot categoricals.

    Shared by training (:func:`design_matrix`) and serving, so the two cannot
    encode the same flow differently. Does not look at the label.
    """
    scaled = preprocessor.scaler.transform(list(window.numeric))
    for name, value in zip(CATEGORICAL_FEATURES, window.categorical, strict=True):
        vocabulary = preprocessor.vocabularies[name]
        encoded = [0.0] * len(vocabulary.values)
        encoded[vocabulary.encode(value)] = 1.0
        scaled.extend(encoded)
    return scaled


def _sigmoid_array(z: np.ndarray) -> np.ndarray:
    """Vectorised :func:`_sigmoid`, stable for large positive and negative inputs."""
    out = np.empty_like(z)
    positive = z >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-z[positive]))
    exponent = np.exp(z[~positive])
    out[~positive] = exponent / (1.0 + exponent)
    return out


def _logistic_numpy(
    rows: Sequence[Sequence[float]],
    targets: Sequence[int],
    epochs: int,
    learning_rate: float,
    l2: float,
) -> tuple[list[float], float]:
    """Full-batch gradient descent, one matrix product per epoch.

    Same update as :meth:`LogisticRegression.fit_reference`: the gradient is averaged over
    all rows, the weights start at zero, and the L2 term does not touch the bias.
    """
    design = np.asarray(rows, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    count = design.shape[0]
    weights = np.zeros(design.shape[1], dtype=np.float64)
    bias = 0.0
    for _ in range(epochs):
        error = _sigmoid_array(design @ weights + bias) - y
        grad = design.T @ error
        grad_bias = float(error.sum())
        weights = weights - learning_rate * (grad / count + l2 * weights)
        bias -= learning_rate * (grad_bias / count)
    return [float(w) for w in weights], float(bias)


def _best_stump_sorted(
    values: np.ndarray, order: np.ndarray, residuals: np.ndarray
) -> tuple[float, float, float, float] | None:
    """Best split for one feature, given its presorted row order (same rule as the reference)."""
    sorted_values = values[order]
    sorted_residuals = residuals[order]
    count = sorted_values.size
    if count < 2:
        return None
    valid = sorted_values[:-1] != sorted_values[1:]  # no split inside a run of equal values
    if not valid.any():
        return None
    left_sum = np.cumsum(sorted_residuals)[:-1]
    total_sum = float(sorted_residuals.sum())
    total_sq = float(np.square(sorted_residuals).sum())
    left_n = np.arange(1, count, dtype=np.float64)
    right_sum = total_sum - left_sum
    right_n = count - left_n
    sse = total_sq - np.square(left_sum) / left_n - np.square(right_sum) / right_n
    sse = np.where(valid, sse, np.inf)
    index = int(np.argmin(sse))  # first minimum, as the reference's strict < keeps
    if not math.isfinite(float(sse[index])):
        return None
    threshold = (float(sorted_values[index]) + float(sorted_values[index + 1])) / 2.0
    return (
        threshold,
        float(left_sum[index] / left_n[index]),
        float(right_sum[index] / right_n[index]),
        float(sse[index]),
    )


def _stumps_numpy(
    rows: Sequence[Sequence[float]],
    targets: Sequence[int],
    n_stumps: int,
    learning_rate: float,
) -> tuple[list[DecisionStump], float]:
    """Least-squares boosting over stumps. Each feature is sorted once, not once per stump."""
    design = np.asarray(rows, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    count, width = design.shape
    rate = float(y.sum()) / count
    base = math.log(rate / (1.0 - rate))
    predictions = np.full(count, base, dtype=np.float64)
    columns = [np.ascontiguousarray(design[:, f]) for f in range(width)]
    orders = [np.argsort(column, kind="stable") for column in columns]
    stumps: list[DecisionStump] = []
    for _ in range(n_stumps):
        residuals = y - predictions
        best: tuple[int, float, float, float, float] | None = None
        for feature in range(width):
            candidate = _best_stump_sorted(columns[feature], orders[feature], residuals)
            if candidate is not None and (best is None or candidate[3] < best[4]):
                best = (feature, *candidate)
        if best is None:
            break  # every feature is constant; no further split exists
        feature, threshold, low, high, _sse = best
        stump = DecisionStump(feature=feature, threshold=threshold, low=low, high=high)
        leaf = np.where(columns[feature] <= threshold, low, high)
        predictions = predictions + learning_rate * leaf
        stumps.append(stump)
    return stumps, base


class LogisticRegression(BaseModel):
    """L2-regularised logistic regression trained by gradient descent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: tuple[float, ...]
    bias: float
    epochs: int = Field(ge=0)

    @classmethod
    def fit(
        cls,
        rows: Sequence[Sequence[float]],
        targets: Sequence[int],
        *,
        epochs: int = DEFAULT_LR_EPOCHS,
        learning_rate: float = DEFAULT_LR_RATE,
        l2: float = DEFAULT_L2,
    ) -> LogisticRegression:
        """Fit by batch gradient descent from a zero initialisation."""
        if len(rows) != len(targets):
            msg = f"{len(rows)} rows but {len(targets)} targets"
            raise ValueError(msg)
        if not rows:
            msg = "cannot fit on zero rows"
            raise ValueError(msg)
        positives = sum(targets)
        if positives in (0, len(targets)):
            # A single-class training fold yields a model that predicts one label
            # for everything. That is not a failed model, it is a degenerate one,
            # and it scores like a real model on a balanced test fold — recall 0,
            # plausible-looking precision. Refusing is the only safe option.
            msg = "cannot fit logistic regression when one class is absent"
            raise ValueError(msg)
        weights, bias = _logistic_numpy(rows, targets, epochs, learning_rate, l2)
        return cls(weights=tuple(weights), bias=bias, epochs=epochs)

    @classmethod
    def fit_reference(
        cls,
        rows: Sequence[Sequence[float]],
        targets: Sequence[int],
        *,
        epochs: int = DEFAULT_LR_EPOCHS,
        learning_rate: float = DEFAULT_LR_RATE,
        l2: float = DEFAULT_L2,
    ) -> LogisticRegression:
        """Pure-Python fit with the same arithmetic as :meth:`fit`.

        Kept as the reference the numpy path is tested against. It is slow (one Python
        loop per row per epoch), so training does not use it.
        """
        if len(rows) != len(targets):
            msg = f"{len(rows)} rows but {len(targets)} targets"
            raise ValueError(msg)
        if not rows:
            msg = "cannot fit on zero rows"
            raise ValueError(msg)
        positives = sum(targets)
        if positives in (0, len(targets)):
            msg = "cannot fit logistic regression when one class is absent"
            raise ValueError(msg)
        width = len(rows[0])
        weights = [0.0] * width
        bias = 0.0
        count = len(rows)

        for _ in range(epochs):
            grad = [0.0] * width
            grad_bias = 0.0
            for row, target in zip(rows, targets, strict=True):
                error = _sigmoid(bias + sum(w * x for w, x in zip(weights, row, strict=True)))
                error -= target
                for index, value in enumerate(row):
                    grad[index] += error * value
                grad_bias += error
            weights = [
                w - learning_rate * (g / count + l2 * w) for w, g in zip(weights, grad, strict=True)
            ]
            bias -= learning_rate * (grad_bias / count)

        return cls(weights=tuple(weights), bias=bias, epochs=epochs)

    def score(self, row: Sequence[float]) -> float:
        """Probability that this row is an attack."""
        return _sigmoid(self.bias + sum(w * x for w, x in zip(self.weights, row, strict=True)))


class DecisionStump(BaseModel):
    """A depth-one tree: one feature, one threshold, two leaf values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    feature: int = Field(ge=0)
    threshold: float
    low: float = Field(description="Value when the feature is at or below the threshold.")
    high: float

    def predict(self, row: Sequence[float]) -> float:
        """Leaf value for one row."""
        return self.low if row[self.feature] <= self.threshold else self.high


def _best_stump_for_feature(
    column: Sequence[float], residuals: Sequence[float]
) -> tuple[float, float, float, float] | None:
    """Exact best split for one feature by cumulative-sum sweep.

    Returns ``(threshold, low, high, sse)``, or None when the feature is
    constant and admits no split at all.
    """
    pairs = sorted(zip(column, residuals, strict=True), key=lambda p: p[0])
    total_sum = sum(r for _, r in pairs)
    total_sq = sum(r * r for _, r in pairs)
    best: tuple[float, float, float, float] | None = None
    left_sum = 0.0
    left_n = 0
    count = len(pairs)

    for index in range(count - 1):
        value, residual = pairs[index]
        left_sum += residual
        left_n += 1
        if value == pairs[index + 1][0]:
            continue  # a split inside a run of equal values separates nothing
        right_sum = total_sum - left_sum
        right_n = count - left_n
        sse = total_sq - (left_sum * left_sum) / left_n - (right_sum * right_sum) / right_n
        if best is None or sse < best[3]:
            threshold = (value + pairs[index + 1][0]) / 2.0
            best = (threshold, left_sum / left_n, right_sum / right_n, sse)
    return best


class GradientBoostedStumps(BaseModel):
    """Least-squares gradient boosting over decision stumps."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stumps: tuple[DecisionStump, ...]
    base: float = Field(description="Initial log-odds prediction.")
    learning_rate: float

    @classmethod
    def fit(
        cls,
        rows: Sequence[Sequence[float]],
        targets: Sequence[int],
        *,
        n_stumps: int = DEFAULT_STUMP_COUNT,
        learning_rate: float = DEFAULT_LEARNING_RATE,
    ) -> GradientBoostedStumps:
        """Fit stumps sequentially against the current pseudo-residuals."""
        if len(rows) != len(targets):
            msg = f"{len(rows)} rows but {len(targets)} targets"
            raise ValueError(msg)
        positives = sum(targets)
        if positives in (0, len(targets)):
            msg = "cannot fit gradient boosting when one class is absent"
            raise ValueError(msg)
        stumps, base = _stumps_numpy(rows, targets, n_stumps, learning_rate)
        return cls(stumps=tuple(stumps), base=base, learning_rate=learning_rate)

    @classmethod
    def fit_reference(
        cls,
        rows: Sequence[Sequence[float]],
        targets: Sequence[int],
        *,
        n_stumps: int = DEFAULT_STUMP_COUNT,
        learning_rate: float = DEFAULT_LEARNING_RATE,
    ) -> GradientBoostedStumps:
        """Pure-Python fit with the same split rule as :meth:`fit`; the test reference."""
        if len(rows) != len(targets):
            msg = f"{len(rows)} rows but {len(targets)} targets"
            raise ValueError(msg)
        positives = sum(targets)
        if positives in (0, len(targets)):
            msg = "cannot fit gradient boosting when one class is absent"
            raise ValueError(msg)
        # Initial prediction is the log-odds of the positive rate.
        rate = positives / len(targets)
        base = math.log(rate / (1.0 - rate))
        predictions = [base] * len(targets)
        width = len(rows[0])
        stumps: list[DecisionStump] = []

        for _ in range(n_stumps):
            # Squared loss on the log-odds scale: residual = target - prediction.
            residuals = [t - p for t, p in zip(targets, predictions, strict=True)]
            best: tuple[int, float, float, float, float] | None = None
            for feature in range(width):
                column = [row[feature] for row in rows]
                candidate = _best_stump_for_feature(column, residuals)
                if candidate is not None and (best is None or candidate[3] < best[4]):
                    best = (feature, *candidate)
            if best is None:
                break  # every feature is constant; no further split exists
            feature, threshold, low, high, _sse = best
            stump = DecisionStump(feature=feature, threshold=threshold, low=low, high=high)
            for index, row in enumerate(rows):
                predictions[index] += learning_rate * stump.predict(row)
            stumps.append(stump)

        return cls(stumps=tuple(stumps), base=base, learning_rate=learning_rate)

    def score(self, row: Sequence[float]) -> float:
        """Probability that this row is an attack."""
        total = self.base + self.learning_rate * sum(s.predict(row) for s in self.stumps)
        return _sigmoid(total)


def score_all(
    model: LogisticRegression | GradientBoostedStumps, rows: Sequence[Sequence[float]]
) -> list[float]:
    """Score every row with either baseline."""
    return [model.score(row) for row in rows]


def column_names(vocabularies: Mapping[str, object]) -> tuple[str, ...]:
    """Names of the design-matrix columns, in order."""
    names = list(NUMERIC_FEATURES)
    for name in CATEGORICAL_FEATURES:
        vocabulary = vocabularies[name]
        names.extend(f"{name}={value}" for value in getattr(vocabulary, "values", ()))
    return tuple(names)
