r"""Hyperparameter search on the validation split only (T-215, R-71).

R-71 forbids tuning on the test set, and the reason is arithmetic rather than
moral. Search over ``k`` configurations and the best one on the test split is the
maximum of ``k`` noisy estimates; that maximum is biased upward by construction,
and the bias grows with ``k``. Tuning on test does not just overfit the model, it
overfits the *number* that gets written into the release note — so the reported
metric is optimistic even though the model itself is honest.

**The test split cannot reach this search, because the search has no parameter for
it.** :func:`search` accepts a training fold and a validation fold and nothing
else. The alternative is a discipline note telling callers not to pass test data,
which holds exactly as long as nobody is in a hurry. A function that cannot be
handed the test split cannot tune on it, and the omission is checked by a test
rather than left to review.

R-71's second half — the test split is touched once per release and the result
recorded — is a separate step by design. :func:`final_test_evaluation` exists so
that the single permitted evaluation has its own name and its own record, rather
than being one more call to a scoring function that also serves tuning.

Every trial is logged with the full :class:`TrainingConfig` that produced it, not
just the knobs that varied. Two configs that differ only in a field nobody
thought to log are indistinguishable afterwards, and an unexplained difference
between runs is the failure the config model exists to prevent.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from aegis_ml.training.pipeline import TrainingConfig

#: Metrics a search may select on. Selecting on a metric that is not computed
#: here would silently fall back to something else.
SEARCH_METRICS: frozenset[str] = frozenset({"roc_auc", "pr_auc", "f1", "recall", "precision"})

#: Default selection metric. ROC-AUC is threshold-independent, so it does not
#: reward a configuration for landing on a fortunate cut point.
DEFAULT_METRIC = "roc_auc"

#: A batch of windows: one element per window, each a sequence of timesteps, each
#: timestep a feature vector. Named because ``Sequence[Sequence[Sequence[float]]]``
#: repeated at every signature is unreadable, and mis-nesting it silently produces
#: a flat-row API that fails deep inside ``train`` instead of at the call site.
Windows = Sequence[Sequence[Sequence[float]]]


class SearchError(ValueError):
    """Raised when a search cannot be run honestly."""


@dataclass(frozen=True, slots=True)
class Trial:
    """One configuration and what it scored.

    Attributes:
        config: the complete configuration, not just the varied knobs.
        score: the selection metric on the validation split.
        final_loss: last training loss, so an unconverged run is visible.
    """

    config: TrainingConfig
    score: float
    final_loss: float

    def as_json(self) -> dict[str, object]:
        """Serialisable form, carrying the whole config."""
        return {
            "score": self.score,
            "final_loss": self.final_loss,
            "config": self.config.model_dump(),
        }


@dataclass(frozen=True, slots=True)
class SearchReport:
    """Everything a search did, so the chosen config can be defended later.

    Attributes:
        metric: the selection metric.
        grid: the values tried per knob.
        trials: every trial, in the order run.
        best: the winning trial.
        train_windows: size of the training fold.
        valid_windows: size of the validation fold.
    """

    metric: str
    grid: Mapping[str, tuple[object, ...]]
    trials: tuple[Trial, ...]
    best: Trial
    train_windows: int
    valid_windows: int

    def as_json(self) -> dict[str, object]:
        """Serialisable form. There is no test-set field, because none was used."""
        return {
            "task": "T-215",
            "rule": "R-71",
            "selection_metric": self.metric,
            "grid": {key: list(values) for key, values in self.grid.items()},
            "trial_count": len(self.trials),
            "best_score": self.best.score,
            "best_config": self.best.config.model_dump(),
            "train_windows": self.train_windows,
            "valid_windows": self.valid_windows,
            "test_split_used": False,
            "trials": [trial.as_json() for trial in self.trials],
        }


def grid_configs(
    base: TrainingConfig, grid_values: Mapping[str, Sequence[object]]
) -> list[TrainingConfig]:
    """Expand a grid into configurations, in a deterministic order.

    The product is taken in the order the keys were given, so two runs of the same
    grid try the same configurations in the same order. Randomised search would
    need its own seed recorded to be reproducible, and an unreproducible search
    cannot be audited.

    Raises:
        SearchError: if the grid is empty, names an unknown knob, or produces no
            configurations.
    """
    if not grid_values:
        raise SearchError("the grid is empty; there is nothing to search")
    known = set(TrainingConfig.model_fields)
    unknown = sorted(set(grid_values) - known)
    if unknown:
        raise SearchError(
            f"the grid names {unknown}, which are not TrainingConfig fields. A knob "
            "that the config model does not know about cannot be recorded, and a "
            "search over unrecorded knobs is not reproducible."
        )
    empty = sorted(key for key, values in grid_values.items() if not values)
    if empty:
        raise SearchError(f"the grid has no values for {empty}")

    combinations: list[dict[str, object]] = [{}]
    for key, values in grid_values.items():
        combinations = [{**partial, key: value} for partial in combinations for value in values]

    configs: list[TrainingConfig] = []
    for combination in combinations:
        try:
            configs.append(TrainingConfig(**{**base.model_dump(), **combination}))
        except Exception as error:  # noqa: BLE001 - pydantic raises many types
            raise SearchError(
                f"grid combination {combination} is not a valid TrainingConfig: {error}"
            ) from error
    if not configs:
        raise SearchError("the grid expanded to no configurations")
    return configs


def search(
    train_seq: Windows,
    train_y: Sequence[bool],
    valid_seq: Windows,
    valid_y: Sequence[bool],
    *,
    grid_values: Mapping[str, Sequence[object]],
    metric: str = DEFAULT_METRIC,
    base: TrainingConfig | None = None,
    on_trial: Callable[[Trial, int, int], None] | None = None,
) -> SearchReport:
    """Train every configuration and select on the validation split.

    There is deliberately no test parameter. R-71 permits the test split to be
    touched once per release, in :func:`final_test_evaluation`, and a search that
    could be handed it would make that limit unenforceable.

    Args:
        train_seq: training windows.
        train_y: training labels.
        valid_seq: validation windows — the only fold scored here.
        valid_y: validation labels.
        grid_values: knob to values to try.
        metric: which validation metric to select on.
        base: the configuration the grid varies.
        on_trial: called after each trial, for progress logging.

    Returns:
        A :class:`SearchReport` covering every trial.

    Raises:
        SearchError: if the metric is unknown, a fold is empty, or the grid is
            unusable.
    """
    if metric not in SEARCH_METRICS:
        raise SearchError(
            f"{metric!r} is not a selection metric this search computes; "
            f"choose from {sorted(SEARCH_METRICS)}"
        )
    if not train_seq or not valid_seq:
        raise SearchError("both the training and validation folds must be non-empty")
    if not train_y or not valid_y:
        raise SearchError("both folds need labels")

    import torch  # noqa: PLC0415

    from aegis_ml.training.evaluation import evaluate  # noqa: PLC0415
    from aegis_ml.training.pipeline import train  # noqa: PLC0415

    base_config = base if base is not None else TrainingConfig()
    configs = grid_configs(base_config, grid_values)
    trials: list[Trial] = []

    for index, config in enumerate(configs, start=1):
        model, losses = train(config, train_seq, train_y)
        model.eval()
        with torch.no_grad():
            tensor = torch.tensor(valid_seq, dtype=torch.float32)
            scores = torch.sigmoid(model(tensor).anomaly_logits).tolist()
        report = evaluate(
            [float(value) for value in scores],
            [bool(label) for label in valid_y],
            model_id=config.model_id,
        )
        if metric == "f1":
            score = float(report.best_f1.f1)
        elif metric in ("roc_auc", "pr_auc"):
            score = float(getattr(report.metrics, metric))
        else:
            score = float(getattr(report.best_f1, metric))

        trial = Trial(config=config, score=score, final_loss=float(losses[-1]))
        trials.append(trial)
        if on_trial is not None:
            on_trial(trial, index, len(configs))

    best = max(trials, key=lambda trial: trial.score)
    return SearchReport(
        metric=metric,
        grid={key: tuple(values) for key, values in grid_values.items()},
        trials=tuple(trials),
        best=best,
        train_windows=len(train_seq),
        valid_windows=len(valid_seq),
    )


def final_test_evaluation(
    config: TrainingConfig,
    train_seq: Windows,
    train_y: Sequence[bool],
    test_seq: Windows,
    test_y: Sequence[bool],
) -> dict[str, object]:
    """The one permitted look at the test split, R-71's second half.

    Separate from :func:`search` on purpose: giving the single evaluation its own
    name means a caller cannot reach it by accident while tuning, and the returned
    record says which configuration it belongs to so the result can be tied to a
    release.

    The configuration is expected to be the search's winner, retrained on the
    training fold. Nothing here checks that, because the check would need the
    search report and coupling the two would make this harder to use for the
    legitimate case of evaluating a configuration chosen some other way.

    Raises:
        SearchError: if a fold is empty.
    """
    if not train_seq or not test_seq:
        raise SearchError("both the training and test folds must be non-empty")

    import torch  # noqa: PLC0415

    from aegis_ml.training.evaluation import evaluate  # noqa: PLC0415
    from aegis_ml.training.pipeline import train  # noqa: PLC0415

    model, losses = train(config, train_seq, train_y)
    model.eval()
    with torch.no_grad():
        tensor = torch.tensor(test_seq, dtype=torch.float32)
        scores = torch.sigmoid(model(tensor).anomaly_logits).tolist()
    report = evaluate(
        [float(value) for value in scores],
        [bool(label) for label in test_y],
        model_id=config.model_id,
    )
    return {
        "rule": "R-71",
        "purpose": "single per-release evaluation of the test split",
        "config": config.model_dump(),
        "final_loss": float(losses[-1]),
        "test_windows": len(test_seq),
        "report": report.model_dump(),
    }
