"""Evaluation harness (T-112).

One entrypoint — :func:`evaluate` — turns a scored artifact into the full metric
set: precision, recall, F1, ROC-AUC, PR-AUC, a confusion matrix, score histogram
and threshold sweep, as a validated ``eval@2`` document.

Why the metrics are computed here rather than imported
-----------------------------------------------------
`ml-service` deliberately carries no scientific stack yet (torch and friends
arrive with T-201). These are short, exact implementations, and being able to
assert them against hand-computed values is worth more than a dependency — the
tests pin ROC-AUC and PR-AUC to numbers that can be checked on paper.

Determinism
-----------
Every function is pure. Ties are resolved by grouping equal scores rather than
by input order, so the same artifact always produces byte-identical JSON, which
is the acceptance criterion for this task.

Undefined metrics
-----------------
ROC-AUC and PR-AUC have no value when a set contains no positives (or, for AUC,
no negatives). They raise rather than returning NaN, because a NaN in a metrics
table is read as zero by the next person who looks at it (R-06).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Schema contract for the report this module produces.
EVAL_SCHEMA_VERSION: Literal["eval@2"] = "eval@2"

#: Number of points in a default threshold sweep, inclusive of 0.0 and 1.0.
DEFAULT_SWEEP_STEPS = 21

#: Fixed-width bins for the recorded score distribution, covering [0, 1].
DEFAULT_SCORE_HISTOGRAM_BINS = 10


class ConfusionCounts(BaseModel):
    """The four cells of a binary confusion matrix."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    tn: int = Field(ge=0)
    fn: int = Field(ge=0)


class ScoreHistogramBin(BaseModel):
    """One lower-inclusive score interval and its recorded class counts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(gt=0.0, le=1.0)
    benign: int = Field(ge=0)
    threat: int = Field(ge=0)

    @model_validator(mode="after")
    def upper_exceeds_lower(self) -> ScoreHistogramBin:
        """Reject empty or reversed intervals."""
        if self.upper <= self.lower:
            raise ValueError("score histogram bin upper must exceed lower")
        return self


class Metrics(BaseModel):
    """Threshold-independent quality measures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    roc_auc: float = Field(ge=0.0, le=1.0)
    pr_auc: float = Field(ge=0.0, le=1.0)
    accuracy: float = Field(ge=0.0, le=1.0)


class SweepPoint(BaseModel):
    """One threshold and everything measured at it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    threshold: float = Field(ge=0.0, le=1.0)
    confusion: ConfusionCounts
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    fpr: float = Field(ge=0.0, le=1.0)


class EvalReport(BaseModel):
    """The whole evaluation of one scored artifact, ready to store or serve."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["eval@2"] = EVAL_SCHEMA_VERSION
    model_id: str = Field(min_length=1)
    threshold: float = Field(
        ge=0.0, le=1.0, description="Operating point the confusion matrix uses"
    )
    positives: int = Field(ge=0)
    negatives: int = Field(ge=0)
    confusion: ConfusionCounts
    score_histogram: tuple[ScoreHistogramBin, ...]
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    metrics: Metrics
    sweep: tuple[SweepPoint, ...]
    best_f1: SweepPoint

    @model_validator(mode="after")
    def histogram_matches_evaluation(self) -> EvalReport:
        """Keep the matrix and distribution tied to the same scored examples."""
        bins = self.score_histogram
        if len(bins) != DEFAULT_SCORE_HISTOGRAM_BINS:
            raise ValueError(
                f"score histogram needs {DEFAULT_SCORE_HISTOGRAM_BINS} bins, got {len(bins)}"
            )
        if bins[0].lower != 0.0 or bins[-1].upper != 1.0:
            raise ValueError("score histogram must cover [0, 1]")
        if any(left.upper != right.lower for left, right in zip(bins, bins[1:], strict=False)):
            raise ValueError("score histogram bins must be contiguous and ordered")
        if any(
            item.lower != index / DEFAULT_SCORE_HISTOGRAM_BINS
            or item.upper != (index + 1) / DEFAULT_SCORE_HISTOGRAM_BINS
            for index, item in enumerate(bins)
        ):
            raise ValueError("score histogram bins must be fixed-width over [0, 1]")
        if sum(item.threat for item in bins) != self.positives:
            raise ValueError("score histogram threat count does not match positives")
        if sum(item.benign for item in bins) != self.negatives:
            raise ValueError("score histogram benign count does not match negatives")
        if self.confusion.tp + self.confusion.fn != self.positives:
            raise ValueError("confusion matrix positive count does not match positives")
        if self.confusion.tn + self.confusion.fp != self.negatives:
            raise ValueError("confusion matrix negative count does not match negatives")
        return self


@dataclass(frozen=True, slots=True)
class _Point:
    """Internal threshold result, before it becomes a validated model."""

    threshold: float
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def precision(self) -> float:
        """True positives over all predicted positives; 0.0 when nothing is predicted."""
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        """True positives over all actual positives; 0.0 when there are none."""
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall; 0.0 when either is zero."""
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0

    @property
    def fpr(self) -> float:
        """False positives over all actual negatives; 0.0 when there are none."""
        return self.fp / (self.fp + self.tn) if (self.fp + self.tn) else 0.0

    def to_model(self) -> SweepPoint:
        """Convert to the validated wire form."""
        return SweepPoint(
            threshold=self.threshold,
            confusion=ConfusionCounts(tp=self.tp, fp=self.fp, tn=self.tn, fn=self.fn),
            precision=self.precision,
            recall=self.recall,
            f1=self.f1,
            fpr=self.fpr,
        )


def _check_inputs(scores: Sequence[float], labels: Sequence[bool]) -> tuple[int, int]:
    """Validate a scored set and return its positive and negative counts.

    Raises:
        ValueError: if the sequences are empty or of different lengths.
    """
    if not scores:
        raise ValueError("cannot evaluate an empty set of scores")
    if len(scores) != len(labels):
        raise ValueError(f"got {len(scores)} scores but {len(labels)} labels")
    positives = sum(1 for label in labels if label)
    return positives, len(labels) - positives


def _score_histogram(
    scores: Sequence[float], labels: Sequence[bool]
) -> tuple[ScoreHistogramBin, ...]:
    """Count benign and threat scores in fixed-width intervals over [0, 1].

    The intervals are lower-inclusive and upper-exclusive, except the last one
    which includes 1.0. Scores outside the probability range are rejected rather
    than silently omitted from the distribution.
    """
    counts = [[0, 0] for _ in range(DEFAULT_SCORE_HISTOGRAM_BINS)]
    for score, label in zip(scores, labels, strict=True):
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError(
                f"score histogram requires finite probabilities in [0, 1], got {score}"
            )
        index = min(int(score * DEFAULT_SCORE_HISTOGRAM_BINS), DEFAULT_SCORE_HISTOGRAM_BINS - 1)
        counts[index][1 if label else 0] += 1

    return tuple(
        ScoreHistogramBin(
            lower=index / DEFAULT_SCORE_HISTOGRAM_BINS,
            upper=(index + 1) / DEFAULT_SCORE_HISTOGRAM_BINS,
            benign=count[0],
            threat=count[1],
        )
        for index, count in enumerate(counts)
    )


def confusion_at(
    scores: Sequence[float], labels: Sequence[bool], threshold: float
) -> ConfusionCounts:
    """Return the confusion matrix at one operating point.

    A score exactly equal to the threshold counts as positive, so the sweep is
    monotone and reproducible at the boundaries.
    """
    _check_inputs(scores, labels)
    tp = fp = tn = fn = 0
    for score, label in zip(scores, labels, strict=True):
        predicted = score >= threshold
        if predicted and label:
            tp += 1
        elif predicted:
            fp += 1
        elif label:
            fn += 1
        else:
            tn += 1
    return ConfusionCounts(tp=tp, fp=fp, tn=tn, fn=fn)


def roc_auc(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """Return the area under the ROC curve via the Mann-Whitney U statistic.

    Equal scores share an average rank, so the result does not depend on the
    order tied scores happen to arrive in.

    Raises:
        ValueError: if there are no positives or no negatives, where AUC is
            undefined rather than zero.
    """
    positives, negatives = _check_inputs(scores, labels)
    if positives == 0 or negatives == 0:
        raise ValueError(
            f"ROC-AUC needs both classes (positives={positives}, negatives={negatives})"
        )

    order = sorted(range(len(scores)), key=scores.__getitem__)
    ranks = [0.0] * len(scores)
    low = 0
    while low < len(order):
        high = low
        while high + 1 < len(order) and scores[order[high + 1]] == scores[order[low]]:
            high += 1
        average = (low + high) / 2 + 1  # ranks are 1-based
        for position in range(low, high + 1):
            ranks[order[position]] = average
        low = high + 1

    rank_sum = math.fsum(rank for rank, label in zip(ranks, labels, strict=True) if label)
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def average_precision(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """Return the area under the precision-recall curve (average precision).

    Equal scores are summed as one group, which is what makes the value stable
    under reordering.

    Raises:
        ValueError: if there are no positives, where PR-AUC is undefined.
    """
    positives, _ = _check_inputs(scores, labels)
    if positives == 0:
        raise ValueError("PR-AUC needs at least one positive example")

    groups: dict[float, list[int]] = {}
    for score, label in zip(scores, labels, strict=True):
        bucket = groups.setdefault(score, [0, 0])
        bucket[0] += 1 if label else 0
        bucket[1] += 1

    area = 0.0
    true_positives = 0
    seen = 0
    previous_recall = 0.0
    for score in sorted(groups, reverse=True):
        hits, count = groups[score]
        true_positives += hits
        seen += count
        recall = true_positives / positives
        area += (recall - previous_recall) * (true_positives / seen)
        previous_recall = recall
    return area


def threshold_sweep(
    scores: Sequence[float],
    labels: Sequence[bool],
    *,
    steps: int = DEFAULT_SWEEP_STEPS,
) -> tuple[SweepPoint, ...]:
    """Measure every metric at evenly spaced thresholds from 0.0 to 1.0 inclusive.

    Raises:
        ValueError: if fewer than two steps are requested, since a sweep of one
            point is not a sweep.
    """
    _check_inputs(scores, labels)
    if steps < 2:
        raise ValueError(f"a sweep needs at least 2 steps, got {steps}")

    points: list[SweepPoint] = []
    for index in range(steps):
        threshold = index / (steps - 1)
        counts = confusion_at(scores, labels, threshold)
        point = _Point(
            threshold=threshold,
            tp=counts.tp,
            fp=counts.fp,
            tn=counts.tn,
            fn=counts.fn,
        )
        points.append(point.to_model())
    return tuple(points)


def _best_f1(sweep: Sequence[SweepPoint]) -> SweepPoint:
    """Return the sweep point with the highest F1.

    Ties are broken toward the higher threshold, which is the conservative
    choice: at equal F1, fewer false positives is the better operating point.
    """
    return max(sweep, key=lambda point: (point.f1, point.threshold))


def evaluate(
    scores: Sequence[float],
    labels: Sequence[bool],
    *,
    model_id: str,
    threshold: float = 0.5,
    steps: int = DEFAULT_SWEEP_STEPS,
) -> EvalReport:
    """Evaluate one scored artifact end to end.

    Raises:
        ValueError: if the inputs are unusable, or if either class is missing so
            the rank-based metrics are undefined.
    """
    positives, negatives = _check_inputs(scores, labels)
    histogram = _score_histogram(scores, labels)
    counts = confusion_at(scores, labels, threshold)
    operating = _Point(threshold=threshold, tp=counts.tp, fp=counts.fp, tn=counts.tn, fn=counts.fn)
    sweep = threshold_sweep(scores, labels, steps=steps)

    return EvalReport(
        model_id=model_id,
        threshold=threshold,
        positives=positives,
        negatives=negatives,
        confusion=counts,
        score_histogram=histogram,
        precision=operating.precision,
        recall=operating.recall,
        f1=operating.f1,
        metrics=Metrics(
            roc_auc=roc_auc(scores, labels),
            pr_auc=average_precision(scores, labels),
            accuracy=(counts.tp + counts.tn) / len(labels),
        ),
        sweep=sweep,
        best_f1=_best_f1(sweep),
    )
