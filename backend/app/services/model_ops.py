"""Model ops: which versions exist, what they scored, and how one replaces another.

This module holds the API-side model of a registry: the versions a deployment
serves, the recorded metrics of each, and the two transitions that change what is
serving -- **promotion** and **rollback**. It is deliberately free of FastAPI, and
of the HTTP client that would call the model service (R-15).

**The registry in ``ml-service`` is the authority; this is the contract.** The
backend does not import ``aegis_ml`` (it is not a dependency of this service), and
no client to the model service exists yet, so the rules R-68 needs are restated
here at the edge and the stand-in implements them. That duplication is named
rather than hidden: a deployment wires :class:`ModelOpsService` to the model
service, and the refusals below are what stop a *request* from carrying an id the
registry would refuse anyway -- a floating reference, an artifact with no
manifest, or a retired version being promoted.

**Promotion is one call and it retires the incumbent.** ``promote`` moves a version
to ``active`` and retires whatever was active for its kind, in one operation, for
the same reason T-212's registry does: two calls leave a window with either two
active versions or none. Promoting the version that is already active changes
nothing and reports ``changed=False``, so an audit trail can record changes rather
than requests (D-041).

**Rollback is not a promotion.** ``models.model_status`` has no path back from
``retired``, and that is deliberate: the set of versions that have ever served
traffic must stay append-only, so R-68's prohibition on reuse holds. A rollback is
the *reversal of a promotion* -- the caller names the **kind**, and the service
finds the version the current one displaced from its own history. Naming the kind
rather than a version is what makes it one call and un-fakeable: an operator
cannot roll back to a version that never served, and each promotion can be rolled
back once (the schema's ``model_versions_history.rolled_back_at`` is that column).

**A number here always comes from a recorded run.** R-74 makes an unsourced metric
an honesty defect, so :class:`MetricPoint` cannot be built from a value alone: it
names the artifact and the field the value was read from, and
:class:`ModelMetrics` refuses a value outside ``[0, 1]`` -- every metric FR-31
names is a proportion, so one outside that range is a fabrication or a units bug,
and either way it must not reach a dashboard as a measurement.

**FR-32's drift numbers are not here.** PSI per feature is computed and published
by ``ml-service`` (T-211) as ``aegis_drift_psi{feature}``, and the drift screen
that reads it is T-409's. This module serves the held-out metrics FR-31 asks for,
with the split named on every set so a reader can see which numbers they are.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

__all__ = [
    "FORBIDDEN_MODEL_IDS",
    "ConfusionMatrix",
    "EvaluationDetails",
    "FloatingModelId",
    "ImmutableArtifact",
    "MetricPoint",
    "MissingManifest",
    "ModelMetrics",
    "ModelOpsError",
    "ModelOpsService",
    "ModelTransition",
    "ModelVersion",
    "NothingToRollBack",
    "RefusedTransition",
    "ScoreHistogram",
    "ScoreHistogramBin",
    "TransitionOutcome",
    "UnknownModel",
]

ModelKindName = Literal["flow", "log"]
ModelStatusName = Literal["staging", "active", "retired"]

#: Ids refused wherever a model is addressed, mirroring the registry's R-68 rule.
#: Case-insensitive, and checked *before* anything looks the id up, so ``latest``
#: is never reported as "not found" -- the remedy differs: one is a typo, the other
#: is a pattern this system forbids.
FORBIDDEN_MODEL_IDS: frozenset[str] = frozenset({"latest", "stable", "current", "newest"})

#: A content address, as R-68 defines it: 64 lowercase hex characters.
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: The metric names FR-31 requires on a held-out temporal split. Named here so the
#: service, the schema and the tests cannot drift apart on spelling.
REQUIRED_METRICS: tuple[str, ...] = ("precision", "recall", "f1", "roc_auc", "pr_auc")


class ModelOpsError(RuntimeError):
    """Base class for every refusal this service can make."""


class FloatingModelId(ModelOpsError):
    """Raised for an id R-68 forbids, such as ``latest``."""


class UnknownModel(ModelOpsError):
    """Raised when no version of this deployment is registered under the id."""


class ImmutableArtifact(ModelOpsError):
    """Raised when a registered id is registered again against other content."""


class RefusedTransition(ModelOpsError):
    """Raised for a status change the lifecycle does not allow."""


class MissingManifest(ModelOpsError):
    """Raised when a version without a training manifest is promoted (R-63)."""


class NothingToRollBack(ModelOpsError):
    """Raised when the kind has no promotion left to reverse."""


def check_model_id(model_id: str) -> None:
    """Refuse a floating id before anything else looks at it.

    Raises:
        FloatingModelId: naming the forbidden set and the alternative.
    """
    if model_id.strip().lower() in FORBIDDEN_MODEL_IDS:
        allowed = ", ".join(sorted(FORBIDDEN_MODEL_IDS))
        msg = (
            f"{model_id!r} is not a resolvable model id. R-68 forbids floating "
            f"references: ask for a specific version, or for the active model of a "
            f"kind. Forbidden: {allowed}"
        )
        raise FloatingModelId(msg)


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """One metric value and the recorded run it was read from (R-74).

    There is no way to build this from a number alone, which is the point: a
    plausible value typed in from memory, or copied from the previous release, is
    exactly what R-74 exists to prevent. Rendering a card shows the value *and*
    where it came from.
    """

    value: float
    artifact: str
    field: str

    def __post_init__(self) -> None:
        """Refuse a value that cannot be a measurement, or one with no source.

        Raises:
            ValueError: if the value is not a finite proportion in ``[0, 1]``, or
                if the artifact or field is blank.
        """
        if not self.artifact.strip():
            msg = (
                "a metric with no artifact cannot be checked; R-74 requires every "
                "number to trace to a recorded run"
            )
            raise ValueError(msg)
        if not self.field.strip():
            msg = (
                f"metric from {self.artifact!r} names no field; R-74 requires the "
                "location of the value"
            )
            raise ValueError(msg)
        if not 0.0 <= self.value <= 1.0:
            msg = (
                f"metric {self.field!r} of {self.artifact!r} is {self.value!r}; FR-31's "
                "metrics are proportions, so a value outside [0, 1] is a units bug or "
                "a fabrication rather than a measurement"
            )
            raise ValueError(msg)

    def as_dict(self) -> dict[str, object]:
        """The wire shape: the value beside its provenance, never the value alone."""
        return {"value": self.value, "artifact": self.artifact, "field": self.field}


@dataclass(frozen=True, slots=True)
class ConfusionMatrix:
    """A recorded binary confusion matrix and the exact run field it came from."""

    threshold: float
    tp: int
    fp: int
    tn: int
    fn: int
    artifact: str
    field: str

    def __post_init__(self) -> None:
        """Refuse unmeasured counts, invalid thresholds, or missing provenance."""
        _validate_counts(("tp", self.tp), ("fp", self.fp), ("tn", self.tn), ("fn", self.fn))
        if not math.isfinite(self.threshold) or not 0.0 <= self.threshold <= 1.0:
            raise ValueError("confusion threshold must be a finite value in [0, 1]")
        _validate_evaluation_source(self.artifact, self.field)
        if self.tp + self.fp + self.tn + self.fn == 0:
            raise ValueError("a confusion matrix must contain recorded examples")


@dataclass(frozen=True, slots=True)
class ScoreHistogramBin:
    """One lower-inclusive score interval and its benign/threat counts."""

    lower: float
    upper: float
    benign: int
    threat: int

    def __post_init__(self) -> None:
        """Reject empty intervals and counts that could not come from an eval run."""
        if (
            not math.isfinite(self.lower)
            or not math.isfinite(self.upper)
            or not 0.0 <= self.lower < self.upper <= 1.0
        ):
            raise ValueError("score histogram intervals must be finite and inside [0, 1]")
        _validate_counts(("benign", self.benign), ("threat", self.threat))


@dataclass(frozen=True, slots=True)
class ScoreHistogram:
    """The complete, provenance-bearing score distribution for one evaluation."""

    bins: tuple[ScoreHistogramBin, ...]
    artifact: str
    field: str

    def __post_init__(self) -> None:
        """Require an ordered, gap-free histogram covering the probability range."""
        _validate_evaluation_source(self.artifact, self.field)
        if len(self.bins) != 10:
            raise ValueError(f"eval@2 score histogram needs 10 bins, got {len(self.bins)}")
        if self.bins[0].lower != 0.0 or self.bins[-1].upper != 1.0:
            raise ValueError("score histogram must cover [0, 1]")
        if any(
            left.upper != right.lower for left, right in zip(self.bins, self.bins[1:], strict=False)
        ):
            raise ValueError("score histogram bins must be contiguous and ordered")
        if any(
            item.lower != index / 10 or item.upper != (index + 1) / 10
            for index, item in enumerate(self.bins)
        ):
            raise ValueError("score histogram bins must be fixed-width over [0, 1]")
        if self.benign_count + self.threat_count == 0:
            raise ValueError("score histogram must contain recorded examples")

    @property
    def benign_count(self) -> int:
        """Number of benign examples represented by the histogram."""
        return sum(item.benign for item in self.bins)

    @property
    def threat_count(self) -> int:
        """Number of threat examples represented by the histogram."""
        return sum(item.threat for item in self.bins)


def _validate_counts(*counts: tuple[str, int]) -> None:
    """Reject negative, non-integer, or boolean counts at the in-memory boundary."""
    for name, count in counts:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"evaluation count {name!r} must be a non-negative integer")


def _validate_evaluation_source(artifact: str, field: str) -> None:
    """Require source artifact and field names for every evaluation visual."""
    if not isinstance(artifact, str) or not artifact.strip():
        raise ValueError("evaluation evidence must name its recorded artifact")
    if not isinstance(field, str) or not field.strip():
        raise ValueError("evaluation evidence must name its artifact field")


@dataclass(frozen=True, slots=True)
class EvaluationDetails:
    """The confusion matrix and histogram read from one recorded eval artifact."""

    confusion: ConfusionMatrix
    score_histogram: ScoreHistogram

    def __post_init__(self) -> None:
        """Keep both views on the same run and the same scored examples."""
        if self.confusion.artifact != self.score_histogram.artifact:
            raise ValueError("confusion matrix and score histogram must name the same artifact")
        if self.confusion.tp + self.confusion.fn != self.score_histogram.threat_count:
            raise ValueError("score histogram threat count does not match confusion matrix")
        if self.confusion.tn + self.confusion.fp != self.score_histogram.benign_count:
            raise ValueError("score histogram benign count does not match confusion matrix")


@dataclass(frozen=True, slots=True)
class ModelMetrics:
    """The held-out evaluation metrics for one version (FR-31).

    Attributes:
        points: metric name to :class:`MetricPoint`. Every name in
            :data:`REQUIRED_METRICS` must be present; FR-31 names five, and a card
            missing one would render a gap where a number belongs.
        split: what these numbers were measured on. Required, because "ROC-AUC
            0.91" without it is not a claim anyone can check (R-74).
        evaluated_at: when the evaluation run happened. Rendered beside the value
            so a stale number is visibly stale.
        evaluation: optional confusion matrix and score histogram read from the
            same recorded ``eval@2`` artifact. ``None`` is an honest state for
            older reports that did not contain these fields.
    """

    points: dict[str, MetricPoint]
    split: str
    evaluated_at: datetime
    evaluation: EvaluationDetails | None = None

    @classmethod
    def from_eval_report(
        cls,
        report: Mapping[str, object],
        *,
        model_id: str,
        artifact: str,
        split: str,
        evaluated_at: datetime,
    ) -> ModelMetrics:
        """Adapt a recorded ``eval@2`` JSON report into the backend read model.

        This is the ingestion seam between a training run log and the in-memory
        model registry. It accepts the report's actual serialized fields, rejects
        a report for another model or schema, and stamps every scalar and visual
        with the same artifact path and source field. It never supplies defaults
        for absent measurements.
        """
        if report.get("schema_version") != "eval@2":
            schema = report.get("schema_version")
            raise ValueError(f"expected a recorded eval@2 report, got {schema!r}")
        if report.get("model_id") != model_id:
            raise ValueError(
                f"evaluation report model_id {report.get('model_id')!r} does not match {model_id!r}"
            )
        _validate_evaluation_source(artifact, "report")

        def mapping(value: object, name: str) -> Mapping[str, object]:
            if not isinstance(value, Mapping):
                raise ValueError(f"evaluation report field {name!r} must be an object")
            return value

        def integer(value: object, name: str) -> int:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"evaluation report field {name!r} must be a non-negative integer")
            return value

        def number(value: object, name: str) -> float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"evaluation report field {name!r} must be a number")
            result = float(value)
            if not math.isfinite(result):
                raise ValueError(f"evaluation report field {name!r} must be finite")
            return result

        report_metrics = mapping(report.get("metrics"), "metrics")
        field_paths = {
            "precision": (report, "precision", "precision"),
            "recall": (report, "recall", "recall"),
            "f1": (report, "f1", "f1"),
            "roc_auc": (report_metrics, "roc_auc", "metrics.roc_auc"),
            "pr_auc": (report_metrics, "pr_auc", "metrics.pr_auc"),
        }
        points = {
            name: MetricPoint(
                value=number(source.get(source_key), field_path),
                artifact=artifact,
                field=field_path,
            )
            for name, (source, source_key, field_path) in field_paths.items()
        }

        raw_confusion = mapping(report.get("confusion"), "confusion")
        confusion = ConfusionMatrix(
            threshold=number(report.get("threshold"), "threshold"),
            tp=integer(raw_confusion.get("tp"), "confusion.tp"),
            fp=integer(raw_confusion.get("fp"), "confusion.fp"),
            tn=integer(raw_confusion.get("tn"), "confusion.tn"),
            fn=integer(raw_confusion.get("fn"), "confusion.fn"),
            artifact=artifact,
            field="confusion",
        )
        raw_bins = report.get("score_histogram")
        if not isinstance(raw_bins, (list, tuple)):
            raise ValueError("evaluation report field 'score_histogram' must be an array")
        bins: list[ScoreHistogramBin] = []
        for index, raw_bin in enumerate(raw_bins):
            raw = mapping(raw_bin, f"score_histogram[{index}]")
            bins.append(
                ScoreHistogramBin(
                    lower=number(raw.get("lower"), f"score_histogram[{index}].lower"),
                    upper=number(raw.get("upper"), f"score_histogram[{index}].upper"),
                    benign=integer(raw.get("benign"), f"score_histogram[{index}].benign"),
                    threat=integer(raw.get("threat"), f"score_histogram[{index}].threat"),
                )
            )
        histogram = ScoreHistogram(bins=tuple(bins), artifact=artifact, field="score_histogram")
        evaluation = EvaluationDetails(confusion=confusion, score_histogram=histogram)
        positives = integer(report.get("positives"), "positives")
        negatives = integer(report.get("negatives"), "negatives")
        if confusion.tp + confusion.fn != positives:
            raise ValueError("confusion matrix does not match report positives")
        if confusion.tn + confusion.fp != negatives:
            raise ValueError("confusion matrix does not match report negatives")
        if histogram.threat_count != positives or histogram.benign_count != negatives:
            raise ValueError("score histogram does not match report class counts")
        expected_precision = (
            confusion.tp / (confusion.tp + confusion.fp) if (confusion.tp + confusion.fp) else 0.0
        )
        expected_recall = (
            confusion.tp / (confusion.tp + confusion.fn) if (confusion.tp + confusion.fn) else 0.0
        )
        expected_f1 = (
            2 * expected_precision * expected_recall / (expected_precision + expected_recall)
            if expected_precision + expected_recall
            else 0.0
        )
        for name, expected in (
            ("precision", expected_precision),
            ("recall", expected_recall),
            ("f1", expected_f1),
        ):
            if not math.isclose(points[name].value, expected, rel_tol=1e-8, abs_tol=1e-8):
                raise ValueError(f"evaluation report {name} does not match its confusion matrix")

        return cls(
            points=points,
            split=split,
            evaluated_at=evaluated_at,
            evaluation=evaluation,
        )

    def __post_init__(self) -> None:
        """Refuse a set that is missing a metric FR-31 requires, or names no split.

        Raises:
            ValueError: naming the missing metrics or the absent split.
        """
        missing = [name for name in REQUIRED_METRICS if name not in self.points]
        if missing:
            msg = (
                f"metrics are missing FR-31's {missing}; a partial set read as a "
                "measurement is worse than a refusal"
            )
            raise ValueError(msg)
        if not self.split.strip():
            msg = (
                "metrics must name the split they were measured on; an unlabelled "
                "number is not checkable (R-74)"
            )
            raise ValueError(msg)
        extra = sorted(set(self.points) - set(REQUIRED_METRICS))
        if extra:
            msg = f"unknown metrics {extra}; FR-31 defines {list(REQUIRED_METRICS)}"
            raise ValueError(msg)
        if self.evaluation is not None:
            source = self.evaluation.confusion.artifact
            if any(point.artifact != source for point in self.points.values()):
                raise ValueError(
                    "scalar metrics and evaluation details must name the same artifact"
                )

    def get(self, name: str) -> MetricPoint:
        """The point for ``name``.

        Raises:
            KeyError: if the name is not one of FR-31's.
        """
        return self.points[name]


@dataclass(frozen=True, slots=True)
class ModelVersion:
    """One registered model version.

    Attributes:
        model_id: the immutable id R-68 requires. Never ``latest``.
        kind: flow or log; FR-30 requires at least two independently versioned
            models, and each kind is promoted and rolled back on its own.
        status: staging, active or retired, matching ``model_status``.
        artifact_uri: where the artifact lives. Recorded, not fetched.
        sha256: content address of the artifact bytes.
        manifest_present: whether a ``training_manifest.json`` ships with it
            (R-63). A version without one can be listed and staged; it cannot be
            promoted.
        metrics: the held-out evaluation numbers, with their provenance. ``None``
            for a staging version whose evaluation has not been recorded -- which
            is a fact, not a zero, and renders as an explicit gap.
        promoted_at: when this version last became active, if it ever has.
        promoted_by: who promoted it. The subject string a token carries; the
            numeric ``users.id`` mapping is D-038's seam.
        justification: why it was promoted. Held on the record because the audit
            trail is the widest-read table in the system and does not carry notes
            (D-041, T-309's precedent).
    """

    model_id: str
    kind: ModelKindName
    status: ModelStatusName
    artifact_uri: str
    sha256: str
    manifest_present: bool
    metrics: ModelMetrics | None = None
    promoted_at: datetime | None = None
    promoted_by: str | None = None
    justification: str = ""

    def __post_init__(self) -> None:
        """Refuse an id that identifies nothing, or a blank artifact location.

        Raises:
            FloatingModelId: for ``latest`` and its equivalents.
            ValueError: if the id or artifact URI is blank, or the content address
                is not a sha256. R-68 requires artifacts to be content-addressed,
                so a defaulted or malformed address would defeat the rule.
        """
        check_model_id(self.model_id)
        if not self.model_id.strip():
            msg = "a model version needs an id"
            raise ValueError(msg)
        if not _HEX64.match(self.sha256):
            msg = (
                f"model {self.model_id!r} has content address {self.sha256!r}, which is "
                "not a lowercase hex sha256; R-68 requires artifacts to be "
                "content-addressed"
            )
            raise ValueError(msg)
        if not self.artifact_uri.strip():
            msg = (
                f"model {self.model_id!r} names no artifact location; a version that "
                "points at nothing cannot be verified (R-68)"
            )
            raise ValueError(msg)

    @property
    def is_serving(self) -> bool:
        """Whether this version is the one producing published scores."""
        return self.status == "active"


@dataclass(frozen=True, slots=True)
class ModelTransition:
    """One recorded change to what is serving.

    A promotion is recorded whether or not it retired an incumbent, because the
    rollback path needs the history rather than a guess. Attributes:
        kind: which model lineage this belongs to.
        activated: the version that became active.
        retired: the version it displaced, or ``None`` for a first activation.
        actor: the authenticated subject that made the change.
        at: when it happened, UTC.
        rolled_back_at: when this transition was reversed, if it has been. Set at
            most once: a promotion can be undone once, and the schema's history
            table has one column for exactly that.
    """

    kind: ModelKindName
    activated: str
    retired: str | None
    actor: str
    at: datetime
    rolled_back_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TransitionOutcome:
    """What a promotion or rollback changed.

    Attributes:
        model_id: the version that is now active.
        retired: the version that stepped down, or ``None``.
        changed: whether anything actually moved. ``False`` means the request was
            a no-op (promoting the version already active, say) and the caller must
            not record it as a change (D-041).
        at: when the change happened. Carried on the outcome rather than read off
            the history entry, because a rollback's history entry is the *promotion*
            it reversed and its timestamp is the wrong one for the response.
        transition: the history entry, when one was affected.
    """

    model_id: str
    retired: str | None
    changed: bool
    at: datetime
    transition: ModelTransition | None = None


class ModelOpsService:
    """The versions this deployment knows about, and the transitions between them.

    In-memory and single-process: it is the API's authority until a client to the
    model service exists (D-030's pattern). Registration is explicit, so nothing
    is invented at startup -- in particular no metrics, because R-74 forbids a
    number that no run produced.
    """

    __slots__ = ("_history", "_versions")

    def __init__(self) -> None:
        """Start with nothing registered."""
        self._versions: dict[str, ModelVersion] = {}
        self._history: list[ModelTransition] = []

    # --- registration and reads ------------------------------------------------

    def register(self, version: ModelVersion) -> None:
        """Record a version.

        Re-registering an id with the same content address is a no-op, so an
        unchanged redeploy does not fail. Re-registering it against *different*
        bytes is refused: R-68 forbids overwriting an artifact, and a silent
        content change under a stable name is how a substitution would hide.

        A version registered as ``active`` records no history: this is the state a
        process starts in when the model service already has it loaded, not a
        decision anyone made through this API. Only :meth:`promote` and
        :meth:`rollback` append transitions, which is what makes the history a
        record of changes rather than of configuration.

        Raises:
            ImmutableArtifact: if the id is registered against other content.
            ValueError: if another version of the same kind is already active.
        """
        existing = self._versions.get(version.model_id)
        if existing is not None:
            if existing.sha256 != version.sha256:
                msg = (
                    f"model {version.model_id!r} is already registered against content "
                    f"{existing.sha256[:12]}… and cannot be registered against "
                    f"{version.sha256[:12]}…. R-68 forbids overwriting an artifact: "
                    "register the new bytes under a new model id."
                )
                raise ImmutableArtifact(msg)
            return
        if version.status == "active":
            incumbent = self.active(version.kind)
            if incumbent is not None:
                msg = (
                    f"model {incumbent.model_id!r} is already active for kind "
                    f"{version.kind!r}; promote the new version instead of registering "
                    "it as active"
                )
                raise ValueError(msg)
        self._versions[version.model_id] = version

    def record_evaluation(
        self,
        model_id: str,
        report: Mapping[str, object],
        *,
        artifact: str,
        split: str,
        evaluated_at: datetime,
    ) -> ModelVersion:
        """Attach one actual ``eval@2`` run to a registered model version.

        The first report is adapted and stored; an identical retry is idempotent.
        A different run cannot silently replace the evidence for an immutable
        model id. The caller must register a new model version for new bytes or
        evaluation results.

        Raises:
            FloatingModelId: for a floating id (R-68).
            UnknownModel: if the version is not registered.
            ImmutableArtifact: if different evaluation evidence is already attached.
            ValueError: if the report is malformed, for another model, or not eval@2.
        """
        version = self.get(model_id)
        metrics = ModelMetrics.from_eval_report(
            report,
            model_id=model_id,
            artifact=artifact,
            split=split,
            evaluated_at=evaluated_at,
        )
        if version.metrics is not None:
            if version.metrics == metrics:
                return version
            msg = (
                f"model {model_id!r} already has evaluation evidence and cannot be "
                "rewritten; register a new immutable model version instead"
            )
            raise ImmutableArtifact(msg)

        updated = _with_metrics(version, metrics)
        self._versions[model_id] = updated
        return updated

    def get(self, model_id: str) -> ModelVersion:
        """One version by id.

        Raises:
            FloatingModelId: for ``latest`` and its equivalents.
            UnknownModel: naming the id that is not registered.
        """
        check_model_id(model_id)
        try:
            return self._versions[model_id]
        except KeyError:
            registered = sorted(self._versions) or "none"
            msg = f"model {model_id!r} is not registered; registered: {registered}"
            raise UnknownModel(msg) from None

    def list(
        self,
        *,
        kind: ModelKindName | None = None,
        status: ModelStatusName | None = None,
    ) -> tuple[ModelVersion, ...]:
        """Registered versions, optionally filtered, ordered by kind then id.

        Ordering is part of the contract rather than an accident of insertion:
        a version table that reshuffles between two identical requests is a table
        nobody can read.
        """
        versions = [
            version
            for version in self._versions.values()
            if (kind is None or version.kind == kind)
            and (status is None or version.status == status)
        ]
        return tuple(sorted(versions, key=lambda version: (version.kind, version.model_id)))

    def active(self, kind: ModelKindName) -> ModelVersion | None:
        """The active version of a kind, or ``None``. There is at most one."""
        for version in self._versions.values():
            if version.kind == kind and version.status == "active":
                return version
        return None

    def history(self, *, kind: ModelKindName | None = None) -> tuple[ModelTransition, ...]:
        """Recorded transitions, oldest first."""
        return tuple(entry for entry in self._history if kind is None or entry.kind == kind)

    # --- transitions -----------------------------------------------------------

    def promote(
        self,
        model_id: str,
        *,
        actor: str,
        justification: str,
        at: datetime | None = None,
    ) -> TransitionOutcome:
        """Make ``model_id`` the active version of its kind, in one call.

        Args:
            model_id: the version to promote. Must be registered, not retired, and
                ship a training manifest (R-63).
            actor: who asked. Recorded on the history entry; never a note.
            justification: why. Required and non-blank: design.md's promotion flow
                asks for it, and a promotion with no stated reason is a change
                nobody can review later.
            at: when; defaults to now, UTC.

        Returns:
            The outcome. Promoting the active version returns ``changed=False``.

        Raises:
            FloatingModelId: for a floating id (R-68).
            UnknownModel: if the id is not registered.
            RefusedTransition: if the version is retired, which is terminal for
                promotion -- roll back instead, or register the retrained artifact
                under a new id.
            MissingManifest: if the version has no training manifest (R-63).
            ValueError: if the justification is blank.
        """
        check_model_id(model_id)
        if not justification.strip():
            msg = (
                "a promotion needs a written justification; design.md requires it and "
                "the record is what review reads later"
            )
            raise ValueError(msg)
        version = self.get(model_id)
        if version.status == "active":
            return TransitionOutcome(
                model_id=model_id, retired=None, changed=False, at=at or datetime.now(UTC)
            )
        if version.status == "retired":
            msg = (
                f"model {model_id!r} is retired and cannot be promoted: R-68 keeps the "
                "set of versions that have served traffic append-only, so retirement is "
                "terminal. Roll back to the version it displaced, or register the "
                "retrained artifact under a new model id."
            )
            raise RefusedTransition(msg)
        if not version.manifest_present:
            msg = (
                f"model {model_id!r} ships no training_manifest.json, so R-63 refuses its "
                "promotion: an artifact with no recorded dataset, seeds and baseline "
                "cannot be trusted with production traffic."
            )
            raise MissingManifest(msg)

        when = at or datetime.now(UTC)
        incumbent = self.active(version.kind)
        retired: str | None = None
        if incumbent is not None:
            retired = incumbent.model_id
            self._versions[retired] = _with_status(incumbent, "retired")
        promoted = _with_status(
            version, "active", promoted_at=when, promoted_by=actor, justification=justification
        )
        self._versions[model_id] = promoted
        transition = ModelTransition(
            kind=version.kind, activated=model_id, retired=retired, actor=actor, at=when
        )
        self._history.append(transition)
        return TransitionOutcome(
            model_id=model_id, retired=retired, changed=True, at=when, transition=transition
        )

    def rollback(
        self, kind: ModelKindName, *, actor: str, reason: str, at: datetime | None = None
    ) -> TransitionOutcome:
        """Undo the most recent un-reversed promotion of ``kind``, in one call.

        The version that the current one displaced is re-activated and the current
        one is retired. This is the *only* path back from ``retired``, and it is
        not a promotion: it does not make a deployment decision, it reverses one,
        and each recorded transition can be reversed once (the schema's
        ``rolled_back_at``).

        The reversal is recorded by marking the promotion it reverses, so a second
        rollback moves to the promotion before that rather than bouncing the same
        two versions back and forth.

        Args:
            kind: which lineage to roll back -- ``flow`` or ``log``. The caller
                names the lineage rather than a version so a rollback cannot
                resurrect a version that never served.
            actor: who asked.
            reason: why. Required, as for a promotion.
            at: when; defaults to now, UTC.

        Returns:
            The outcome, naming both versions that moved.

        Raises:
            NothingToRollBack: if the kind has no active version, or its activation
                displaced nothing (there is no version older than the first).
            ValueError: if the reason is blank.
        """
        if not reason.strip():
            msg = (
                "a rollback needs a reason; an emergency change with no stated cause "
                "cannot be reviewed"
            )
            raise ValueError(msg)
        current = self.active(kind)
        if current is None:
            msg = f"no version of kind {kind!r} is active, so there is nothing to roll back"
            raise NothingToRollBack(msg)
        pending = self._last_unreversed(kind)
        if pending is None or pending.retired is None:
            msg = (
                f"the active {kind!r} model {current.model_id!r} was the first version of its "
                "kind to serve traffic, so it displaced nothing to roll back to"
            )
            raise NothingToRollBack(msg)

        when = at or datetime.now(UTC)
        previous = self.get(pending.retired)
        self._versions[current.model_id] = _with_status(current, "retired")
        self._versions[previous.model_id] = _with_status(
            previous, "active", promoted_at=when, promoted_by=actor, justification=reason
        )
        # The reversal is recorded on the promotion it reverses -- the schema's
        # own ``rolled_back_at`` column -- rather than as a second transition, so
        # "which decisions were undone" is one fact in one place. A promotion
        # rolled back once is never reversed again; a further rollback moves to the
        # next promotion back.
        marked = _replace_rolled_back(pending, when)
        self._history[self._history.index(pending)] = marked
        return TransitionOutcome(
            model_id=previous.model_id,
            retired=current.model_id,
            changed=True,
            at=when,
            transition=marked,
        )

    def _last_unreversed(self, kind: ModelKindName) -> ModelTransition | None:
        """The newest transition of ``kind`` that no rollback has reversed yet."""
        for entry in reversed(self._history):
            if entry.kind == kind and entry.rolled_back_at is None:
                return entry
        return None


def _with_metrics(version: ModelVersion, metrics: ModelMetrics) -> ModelVersion:
    """A copy with the one evaluation artifact registered for its version."""
    return ModelVersion(
        model_id=version.model_id,
        kind=version.kind,
        status=version.status,
        artifact_uri=version.artifact_uri,
        sha256=version.sha256,
        manifest_present=version.manifest_present,
        metrics=metrics,
        promoted_at=version.promoted_at,
        promoted_by=version.promoted_by,
        justification=version.justification,
    )


def _with_status(
    version: ModelVersion,
    status: ModelStatusName,
    *,
    promoted_at: datetime | None = None,
    promoted_by: str | None = None,
    justification: str | None = None,
) -> ModelVersion:
    """A copy of ``version`` with a new status and optionally new provenance."""
    return ModelVersion(
        model_id=version.model_id,
        kind=version.kind,
        status=status,
        artifact_uri=version.artifact_uri,
        sha256=version.sha256,
        manifest_present=version.manifest_present,
        metrics=version.metrics,
        promoted_at=version.promoted_at if promoted_at is None else promoted_at,
        promoted_by=version.promoted_by if promoted_by is None else promoted_by,
        justification=version.justification if justification is None else justification,
    )


def _replace_rolled_back(entry: ModelTransition, when: datetime) -> ModelTransition:
    """A copy of a transition marked as reversed at ``when``."""
    return ModelTransition(
        kind=entry.kind,
        activated=entry.activated,
        retired=entry.retired,
        actor=entry.actor,
        at=entry.at,
        rolled_back_at=when,
    )


#: The two kinds FR-30 names, in a stable order, so the schema layer, the routes
#: and the tests all read one source rather than three copies of ``("flow", "log")``.
KINDS: tuple[ModelKindName, ...] = ("flow", "log")
