"""Wire contracts for the model ops endpoints (T-315, FR-30…FR-33).

The shape that matters here is R-74's: a metric is never a bare number on the
wire. :class:`MetricPointOut` carries the value *and* the recorded run it was read
from, because a dashboard that renders only the number invites it to be quoted
without its provenance, and a number nobody can check is a claim, not a
measurement.

The listing deliberately does **not** carry the metrics of every version. A
version table shows id, kind, status and who promoted it; the numbers are one
request per version, on the endpoint FR-31 names, so a long history does not make
the list heavier than the screen reading it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MAX_REASON_LENGTH",
    "ConfusionMatrixOut",
    "EvaluationDetailsOut",
    "MetricPointOut",
    "ModelListOut",
    "ModelMetricsOut",
    "ModelOut",
    "ModelTransitionOut",
    "PromotionRequest",
    "RollbackRequest",
    "ScoreHistogramBinOut",
    "ScoreHistogramOut",
]

#: A note for the change record, not a document store. It is held on the version
#: and shown in the response; it never enters the audit trail, which is the
#: widest-read table in the system (D-041, R-58).
MAX_REASON_LENGTH = 500


class MetricPointOut(BaseModel):
    """A metric value beside the run it came from (R-74)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float
    artifact: str = Field(description="Path or id of the recorded run the value was read from.")
    field: str = Field(description="Location of the value inside that artifact.")


class ConfusionMatrixOut(BaseModel):
    """Recorded TP/FP/TN/FN counts, threshold and exact artifact provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    threshold: float = Field(ge=0.0, le=1.0)
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    tn: int = Field(ge=0)
    fn: int = Field(ge=0)
    artifact: str = Field(description="Recorded evaluation run containing this matrix.")
    field: str = Field(description="Field path inside the recorded evaluation run.")


class ScoreHistogramBinOut(BaseModel):
    """One lower-inclusive score interval and the observed class counts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(gt=0.0, le=1.0)
    benign: int = Field(ge=0)
    threat: int = Field(ge=0)


class ScoreHistogramOut(BaseModel):
    """The recorded score distribution and its artifact provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bins: list[ScoreHistogramBinOut]
    artifact: str = Field(description="Recorded evaluation run containing this histogram.")
    field: str = Field(description="Field path inside the recorded evaluation run.")


class EvaluationDetailsOut(BaseModel):
    """The confusion matrix and score distribution from one evaluation artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    confusion: ConfusionMatrixOut
    score_histogram: ScoreHistogramOut


class ModelMetricsOut(BaseModel):
    """FR-31's metrics for one version, on a named split.

    ``metrics`` always holds the five names FR-31 defines -- precision, recall, f1,
    roc_auc and pr_auc -- because the service refuses a partial set. A mapping
    rather than five fields: the names come from the evaluation harness's own
    vocabulary, and a reader iterating them renders every metric without a change
    to this schema. ``evaluation`` is present only when the recorded report is
    ``eval@2`` and carries both visuals with independent artifact/field provenance;
    older reports remain readable with it set to null.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    split: str = Field(
        description=("The split these numbers were measured on, e.g. 'temporal:2025-Q4'.")
    )
    evaluated_at: datetime
    metrics: dict[str, MetricPointOut]
    evaluation: EvaluationDetailsOut | None = None


class ModelOut(BaseModel):
    """One registered model version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    kind: str
    status: str
    artifact_uri: str
    sha256: str
    manifest_present: bool = Field(
        description=(
            "Whether a training_manifest.json ships with it. False means R-63 "
            "refuses its promotion."
        )
    )
    promoted_at: datetime | None = None
    promoted_by: str | None = None
    justification: str = ""


class ModelListOut(BaseModel):
    """The registered versions, in the order the version table renders them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[ModelOut]
    count: int


class PromotionRequest(BaseModel):
    """A request to make a version active.

    ``justification`` is required: design.md's promotion flow asks for one, and a
    promotion with no stated reason is a change nobody can review later.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    justification: str = Field(min_length=1, max_length=MAX_REASON_LENGTH)


class RollbackRequest(BaseModel):
    """A request to reverse the most recent promotion of a kind."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1, max_length=MAX_REASON_LENGTH)


class ModelTransitionOut(BaseModel):
    """What a promotion or rollback did.

    ``retired`` is present so a caller can see the whole change in one response
    rather than inferring it from a second read -- which matters when the version
    that stepped down is exactly what a rollback will need.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    kind: str
    status: str
    retired: str | None
    changed: bool
    at: datetime
    actor: str
