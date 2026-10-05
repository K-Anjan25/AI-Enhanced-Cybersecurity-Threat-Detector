"""Late fusion of the flow and log scores (T-205).

*Late* means each model scores independently and only the two scalars are
combined. The alternative — concatenating the encoders' representations and
training one head — usually scores better and is rejected here on purpose: a
single head cannot say which modality produced an alert, and an alert that cannot
be attributed to its evidence cannot be explained (T-206) or argued with.

Two rules matter more than the arithmetic.

**The composite is monotonic in each input.** Holding one modality fixed, more
suspicion from the other must never lower the combined score. This is asserted by
sweeping the whole range in the tests, not left to inspection: a fusion rule that
is not monotonic produces alerts that vanish when evidence strengthens, which is
the failure mode nobody debugs because it looks like a threshold problem.

**Missing evidence is flagged, never imputed.** When only one modality arrives —
log collection down, a flow probe offline — the score is penalised and
``partial_evidence`` is set. Treating a missing modality as a benign zero would
silently convert an outage into a clean bill of health, which is the most
dangerous thing a detector can do.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FusionConfig:
    """How the two scores combine.

    Attributes:
        flow_weight: weight on the flow score when both modalities are present.
        log_weight: weight on the log score when both are present.
        partial_penalty: fraction *removed* from a single-modality score. A score
            computed from one modality is strictly less trustworthy than one
            computed from two, and the penalty is what makes that visible in the
            number rather than only in a flag.
    """

    flow_weight: float = 0.6
    log_weight: float = 0.4
    partial_penalty: float = 0.25

    def __post_init__(self) -> None:
        """Reject weights that cannot describe a convex combination."""
        for name, value in (
            ("flow_weight", self.flow_weight),
            ("log_weight", self.log_weight),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")
        total = self.flow_weight + self.log_weight
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"flow_weight and log_weight must sum to 1, got {total}")
        if not 0.0 <= self.partial_penalty < 1.0:
            raise ValueError(f"partial_penalty must be in [0, 1), got {self.partial_penalty}")


@dataclass(frozen=True, slots=True)
class FusedScore:
    """One fused decision.

    Attributes:
        score: the composite in ``[0, 1]``.
        partial_evidence: whether only one modality contributed. Callers must
            surface this; presenting a partial score as full evidence is the bug
            this field exists to prevent.
        contributing: which modalities produced a score, for display and audit.
        flow_score: the flow model's score, or ``None`` if it did not run.
        log_score: the log model's score, or ``None`` if it did not run.
    """

    score: float
    partial_evidence: bool
    contributing: tuple[str, ...]
    flow_score: float | None
    log_score: float | None


def _check(name: str, value: float) -> None:
    """Reject a score outside [0, 1] rather than clamping it.

    Clamping hides a broken model: a score of 1.7 and a score of 1.0 would become
    indistinguishable, and the calibration in T-207 would fit a quantile to
    numbers that were never probabilities.
    """
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")


def fuse(
    flow_score: float | None,
    log_score: float | None,
    config: FusionConfig | None = None,
) -> FusedScore:
    """Combine the two modality scores.

    Args:
        flow_score: FlowNet's anomaly score, or ``None`` if the flow model did not
            produce one.
        log_score: LogNet's anomaly score, or ``None`` likewise.
        config: weights and penalty.

    Returns:
        The composite, with ``partial_evidence`` set whenever a modality is
        missing.

    Raises:
        ValueError: if a score is out of range, or if neither modality produced
            one — there is nothing to fuse, and inventing a zero would report a
            detector outage as a quiet network.
    """
    if flow_score is None and log_score is None:
        raise ValueError(
            "neither modality produced a score; refusing to invent one, because a "
            "silent zero would report an outage as a clean network"
        )
    if flow_score is not None:
        _check("flow_score", flow_score)
    if log_score is not None:
        _check("log_score", log_score)

    c = config or FusionConfig()

    if flow_score is not None and log_score is not None:
        # A convex combination, which is what makes the result monotonic in each
        # input: both coefficients are non-negative and fixed.
        score = c.flow_weight * flow_score + c.log_weight * log_score
        return FusedScore(
            score=score,
            partial_evidence=False,
            contributing=("flow", "log"),
            flow_score=flow_score,
            log_score=log_score,
        )

    # Exactly one modality. Penalised, and flagged: the penalty alone is not
    # enough, because a penalised 0.9 still looks like a confident score.
    if flow_score is not None:
        score = (1.0 - c.partial_penalty) * flow_score
        contributing: tuple[str, ...] = ("flow",)
    else:
        assert log_score is not None  # noqa: S101 - the None/None case raised above
        score = (1.0 - c.partial_penalty) * log_score
        contributing = ("log",)

    return FusedScore(
        score=score,
        partial_evidence=True,
        contributing=contributing,
        flow_score=flow_score,
        log_score=log_score,
    )
